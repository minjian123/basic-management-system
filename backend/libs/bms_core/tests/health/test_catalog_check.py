"""服务目录健康项测试（Kiwi 2177 / 2183）：`catalog` 非必需项只标记降级、不参与整体就绪判定。

覆盖 06_01 启动接库校验降级口径的可观测侧：

- `CatalogHealthCheck.required is False`：快照可达 → 该项 `ok=True`；
- 快照不可达（契约 503）→ 该项 `ok=False` 且 `error` 为异常类名，但**整体 `report.ok` 仍为 True**；
- 对照：必需项失败仍使整体不就绪（非必需标记不削弱必需项口径）；
- `/readyz` 聚合后按 `catalog` 项刷新 `bms_catalog_degraded`（失败 1 / 成功 0；08_02 告警联动归口）。
"""

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from bms_core.api import health
from bms_core.api.deps import get_health_check_registry
from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.exceptions import ServiceUnavailableError
from bms_core.health.base import BaseHealthCheck, HealthCheckResult
from bms_core.health.checks import CatalogHealthCheck
from bms_core.health.registry import HealthCheckRegistry
from bms_core.metrics.base import MetricLabels
from bms_core.metrics.null import NullMetrics
from bms_core.metrics.prometheus import PrometheusMetrics
from bms_core.services.module_registry import SERVICE_CATALOG


class _OkCheck(BaseHealthCheck):
    """测试用必需项（恒通过）。"""

    @property
    def key(self) -> str:
        """检查项键。"""
        return "database"

    def describe(self) -> str:
        """元信息描述。"""
        return "恒通过必需项"

    async def check(self) -> HealthCheckResult:
        """恒通过。"""
        return HealthCheckResult(name=self.key, ok=True)


class _DownCheck(BaseHealthCheck):
    """测试用必需项（恒失败）。"""

    @property
    def key(self) -> str:
        """检查项键。"""
        return "redis"

    def describe(self) -> str:
        """元信息描述。"""
        return "恒失败必需项"

    async def check(self) -> HealthCheckResult:
        """恒失败（异常由聚合层收敛为异常类名）。"""
        raise ConnectionError("redis 不可达")


def _stub_snapshot(monkeypatch: pytest.MonkeyPatch, *, error: Exception | None = None) -> None:
    """以桩替换服务目录快照取数（模拟本地权威 / 契约两种结果）。

    Args:
        monkeypatch: pytest monkeypatch 夹具。
        error: 非空表示抛出该异常（模拟契约不可达）。
    """

    async def _load(app: object) -> ConcurrentStableList[object]:
        if error is not None:
            raise error
        return ConcurrentStableList(SERVICE_CATALOG)

    monkeypatch.setattr("bms_core.catalog.loader.load_catalog_snapshot", _load)


def test_catalog_check_is_optional_and_ok() -> None:
    """`catalog` 为非必需项；快照可达时该项与整体均就绪。"""
    check = CatalogHealthCheck(FastAPI())
    assert check.key == "catalog"
    assert check.required is False
    assert "非必需项" in check.describe()


async def test_catalog_check_failure_keeps_overall_ready(monkeypatch: pytest.MonkeyPatch) -> None:
    """快照不可达：`catalog` 项标记降级（ok=False + 异常类名），整体仍就绪（不产生 503）。"""
    _stub_snapshot(monkeypatch, error=ServiceUnavailableError("服务目录快照契约调用失败（503）"))
    registry = HealthCheckRegistry()
    registry.register(_OkCheck())
    registry.register(CatalogHealthCheck(FastAPI()))

    report = await registry.aggregate()
    assert report.ok is True
    assert [item.name for item in report.checks] == ["database", "catalog"]
    assert report.checks[1].ok is False
    assert report.checks[1].error == "ServiceUnavailableError"


async def test_catalog_check_ok_when_snapshot_reachable(monkeypatch: pytest.MonkeyPatch) -> None:
    """快照可达：`catalog` 项 ok=True（与启动校验同源取数）。"""
    _stub_snapshot(monkeypatch)
    registry = HealthCheckRegistry()
    registry.register(CatalogHealthCheck(FastAPI()))

    report = await registry.aggregate()
    assert report.ok is True
    assert report.checks[0].ok is True
    assert report.checks[0].error is None


async def test_required_check_failure_still_not_ready(monkeypatch: pytest.MonkeyPatch) -> None:
    """对照：必需项失败仍使整体不就绪（非必需标记不削弱必需项口径）。"""
    _stub_snapshot(monkeypatch, error=ServiceUnavailableError("契约不可达"))
    registry = HealthCheckRegistry()
    registry.register(_DownCheck())
    registry.register(CatalogHealthCheck(FastAPI()))

    report = await registry.aggregate()
    assert report.ok is False
    assert report.checks[0].ok is False
    assert report.checks[0].error == "ConnectionError"


async def _probe_readyz(monkeypatch: pytest.MonkeyPatch, *, error: Exception | None) -> str:
    """经 `/readyz` 聚合一次，返回指标渲染文本（catalog 项按 `error` 控制成败）。

    Args:
        monkeypatch: pytest monkeypatch 夹具。
        error: 非空表示快照不可达（catalog 项失败）。

    Returns:
        str: `PrometheusMetrics.render()` 的文本。
    """
    _stub_snapshot(monkeypatch, error=error)
    metrics = PrometheusMetrics("test")
    app = FastAPI()
    app.state.metrics = metrics
    app.state.startup_complete = True
    app.state.draining = False
    app.include_router(health.router)
    registry = HealthCheckRegistry()
    registry.register(CatalogHealthCheck(app))
    app.dependency_overrides[get_health_check_registry] = lambda: registry

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/readyz")
    assert response.status_code == 200  # catalog 非必需项：失败不产生 503
    rendered = metrics.render()
    assert rendered is not None
    return rendered[0].decode()


@pytest.mark.kiwi_id(2183)
async def test_readyz_records_catalog_degraded(monkeypatch: pytest.MonkeyPatch) -> None:
    """快照不可达：`/readyz` 聚合后记 `bms_catalog_degraded` 1（降级可见）。"""
    text = await _probe_readyz(monkeypatch, error=ServiceUnavailableError("服务目录快照契约调用失败（503）"))
    assert 'bms_catalog_degraded{service="test"} 1.0' in text
    assert 'bms_dependency_up{dependency="catalog",service="test"} 0.0' in text


@pytest.mark.kiwi_id(2183)
async def test_readyz_records_catalog_reachable(monkeypatch: pytest.MonkeyPatch) -> None:
    """快照可达：`/readyz` 聚合后记 `bms_catalog_degraded` 0（恢复归零）。"""
    text = await _probe_readyz(monkeypatch, error=None)
    assert 'bms_catalog_degraded{service="test"} 0.0' in text
    assert 'bms_dependency_up{dependency="catalog",service="test"} 1.0' in text


class _BrokenMetrics(NullMetrics):
    """指标器替身：写入即抛错（探针不受影响的降级分支）。"""

    plugin_name = "broken"

    async def gauge(self, name: str, *, value: float, labels: MetricLabels | None = None) -> None:
        """恒定抛错。"""
        del name, value, labels
        raise RuntimeError("metrics down")


async def _probe_readyz_without_metrics(monkeypatch: pytest.MonkeyPatch, *, metrics: object) -> int:
    """以给定 `app.state.metrics` 形态经 `/readyz` 聚合一次，返回状态码。

    Args:
        monkeypatch: pytest monkeypatch 夹具。
        metrics: 放入 `app.state.metrics` 的对象（可缺省 / 非 `BaseMetrics`）。

    Returns:
        int: `/readyz` 状态码。
    """
    _stub_snapshot(monkeypatch, error=None)
    app = FastAPI()
    if metrics is not None:
        app.state.metrics = metrics
    app.state.startup_complete = True
    app.state.draining = False
    app.include_router(health.router)
    registry = HealthCheckRegistry()
    registry.register(CatalogHealthCheck(app))
    app.dependency_overrides[get_health_check_registry] = lambda: registry

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/readyz")
    return response.status_code


@pytest.mark.kiwi_id(2183)
async def test_readyz_without_metrics_still_serves(monkeypatch: pytest.MonkeyPatch) -> None:
    """未装配指标器（`app.state.metrics` 缺省 / 非契约实例）：探针照常返回，不因缺指标失败。"""
    assert await _probe_readyz_without_metrics(monkeypatch, metrics=None) == 200
    assert await _probe_readyz_without_metrics(monkeypatch, metrics=object()) == 200


@pytest.mark.kiwi_id(2183)
async def test_readyz_swallows_metric_write_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """指标写入抛错：探针静默忽略（就绪判定不受指标侧故障影响）。"""
    assert await _probe_readyz_without_metrics(monkeypatch, metrics=_BrokenMetrics()) == 200


async def _readyz_status(*, startup_complete: bool, draining: bool) -> int:
    """以给定启动 / 停机标记经 `/readyz` 探针一次，返回状态码。

    Args:
        startup_complete: 启动完成态。
        draining: 停机摘流标记。

    Returns:
        int: `/readyz` 状态码。
    """
    app = FastAPI()
    app.state.startup_complete = startup_complete
    app.state.draining = draining
    app.include_router(health.router)
    registry = HealthCheckRegistry()
    registry.register(_OkCheck())
    app.dependency_overrides[get_health_check_registry] = lambda: registry

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/readyz")
    return response.status_code


@pytest.mark.kiwi_id(2183)
async def test_readyz_unavailable_when_not_started_or_draining() -> None:
    """启动未完成 / 停机摘流中：`/readyz` 直接 503（不聚合检查项）。"""
    assert await _readyz_status(startup_complete=False, draining=False) == 503
    assert await _readyz_status(startup_complete=True, draining=True) == 503
    assert await _readyz_status(startup_complete=True, draining=False) == 200


@pytest.mark.kiwi_id(2183)
async def test_readyz_records_non_catalog_dependency_only(monkeypatch: pytest.MonkeyPatch) -> None:
    """非 `catalog` 检查项：只记 `bms_dependency_up`，不写 `bms_catalog_degraded`。"""
    _stub_snapshot(monkeypatch, error=None)
    metrics = PrometheusMetrics("test")
    app = FastAPI()
    app.state.metrics = metrics
    app.state.startup_complete = True
    app.state.draining = False
    app.include_router(health.router)
    registry = HealthCheckRegistry()
    registry.register(_OkCheck())
    app.dependency_overrides[get_health_check_registry] = lambda: registry

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/readyz")
    assert response.status_code == 200
    rendered = metrics.render()
    assert rendered is not None
    text = rendered[0].decode()
    assert 'bms_dependency_up{dependency="database",service="test"} 1.0' in text
    assert "bms_catalog_degraded" not in text
