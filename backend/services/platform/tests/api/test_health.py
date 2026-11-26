"""健康检查路由：`/healthz` 存活 + `/readyz` 就绪契约与启动完成态（Kiwi 2 / 64 / 65）。

重写口径（13_11）：

- 就绪探针的注册表经**依赖覆盖**注入（`monkeypatch.setitem(app.dependency_overrides, ...)`），
  不再重建进程级插件注册表、不再替换 `bms_core.application.get_settings`；
- 启动完成态 / 停机摘流直接改装配态 `app.state`（`monkeypatch`，用例结束自动还原）；
- 「未接入服务运行时」的最小应用是纯 `FastAPI` + 探针路由，不触碰插件装配，可自建。
"""

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from bms_core.api import health
from bms_core.api.deps import get_health_check_registry
from bms_core.core.service import ServiceIdentity, ServiceRuntime
from bms_core.health.base import BaseHealthCheck, HealthCheckResult
from bms_core.health.registry import HealthCheckRegistry
from bms_platform import SERVICE_NAME, __version__

_Identity = {"service": SERVICE_NAME, "version": __version__}


class _PassingCheck(BaseHealthCheck):
    """测试用通过检查项。"""

    def __init__(self, name: str) -> None:
        self._name = name

    @property
    def key(self) -> str:
        return self._name

    def describe(self) -> str:
        return f"通过检查项 {self._name}"

    async def check(self) -> HealthCheckResult:
        return HealthCheckResult(name=self._name, ok=True)


class _FailingCheck(BaseHealthCheck):
    """测试用不可达检查项：抛出的异常信息含敏感串（验证响应不泄露）。"""

    def __init__(self, name: str = "redis") -> None:
        self._name = name

    @property
    def key(self) -> str:
        return self._name

    def describe(self) -> str:
        return f"不可达检查项 {self._name}"

    async def check(self) -> HealthCheckResult:
        raise ConnectionError("redis://bms:secret@127.0.0.1:6379/0 连接失败")


def _registry(*checks: BaseHealthCheck) -> HealthCheckRegistry:
    """构造测试用注册表（按传入顺序注册检查项）。

    Args:
        *checks: 检查项。

    Returns:
        HealthCheckRegistry: 注册表实例。
    """
    registry = HealthCheckRegistry()
    for check in checks:
        registry.register(check)
    return registry


def _inject_registry(app: FastAPI, monkeypatch: pytest.MonkeyPatch, fake: HealthCheckRegistry) -> None:
    """把测试注册表注入就绪探针的依赖（`monkeypatch` 退出自动卸载）。

    Args:
        app: 装配态应用实例。
        monkeypatch: 补丁夹具。
        fake: 测试注册表。
    """
    monkeypatch.setitem(app.dependency_overrides, get_health_check_registry, lambda: fake)


def _minimal_app(*, drained: bool = False) -> FastAPI:
    """构造只挂探针路由的最小应用（不触插件装配）。

    为什么不用装配态应用：`startup_complete` / `draining` 是装配器写入 `app.state` 的运行时标记，
    用例反射改它属 P5 禁止项。这里改用装配器自身接口——`ServiceRuntime` 构造时落身份与
    `draining=False`、不设 `startup_complete`（等价「lifespan 未启动」）；摘流分支调
    `start_drain()`（幂等置 `draining=True` 且清 `startup_complete`）。

    Args:
        drained: 是否立即进入停机摘流态。

    Returns:
        FastAPI: 最小应用。
    """
    app = FastAPI()
    app.include_router(health.router)
    runtime = ServiceRuntime(app, ServiceIdentity(name=SERVICE_NAME, version=__version__))
    if drained:
        runtime.start_drain()
    return app


@pytest.mark.kiwi_id(2)
async def test_healthz_returns_ok(client: AsyncClient) -> None:
    """GET /healthz 返回 {"status":"ok"} 与服务身份（不依赖启动完成态）。"""
    resp = await client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", **_Identity}


@pytest.mark.kiwi_id(2)
async def test_healthz_without_identity_omits_fields() -> None:
    """未接入服务运行时的最小应用：`/healthz` 不附加服务身份字段。"""
    app = FastAPI()
    app.include_router(health.router)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as anonymous:
        resp = await anonymous.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


@pytest.mark.kiwi_id(64)
async def test_readyz_all_ok(client: AsyncClient, service_app: FastAPI, monkeypatch: pytest.MonkeyPatch) -> None:
    """全部检查项就绪：200 + status ok + 服务身份 + checks 动态键结构（注册顺序）。"""
    _inject_registry(service_app, monkeypatch, _registry(_PassingCheck("redis"), _PassingCheck("database")))

    resp = await client.get("/readyz")

    assert resp.status_code == 200
    body = resp.json()
    assert body == {
        "status": "ok",
        "checks": {"redis": {"ok": True, "error": None}, "database": {"ok": True, "error": None}},
        **_Identity,
    }
    assert list(body["checks"]) == ["redis", "database"]


@pytest.mark.kiwi_id(64)
async def test_readyz_failure_returns_503_without_leak(
    client: AsyncClient, service_app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    """检查项不可达：503 + status down + error 为异常类名且不泄露敏感串。"""
    _inject_registry(service_app, monkeypatch, _registry(_PassingCheck("database"), _FailingCheck("redis")))

    resp = await client.get("/readyz")

    assert resp.status_code == 503
    body = resp.json()
    assert body["status"] == "down"
    assert body["checks"]["redis"] == {"ok": False, "error": "ConnectionError"}
    assert body["checks"]["database"] == {"ok": True, "error": None}
    assert body["service"] == SERVICE_NAME
    assert "secret" not in resp.text
    assert "redis://" not in resp.text
    assert "127.0.0.1" not in resp.text


@pytest.mark.kiwi_id(64)
async def test_readyz_omits_unregistered_checks(
    client: AsyncClient, service_app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    """未注册检查项（如阶段八前的 minio）从 checks 省略，不做「未接入即失败」判定。"""
    _inject_registry(service_app, monkeypatch, _registry(_PassingCheck("redis")))

    resp = await client.get("/readyz")

    assert resp.status_code == 200
    checks = resp.json()["checks"]
    assert list(checks) == ["redis"]
    assert "minio" not in checks


@pytest.mark.kiwi_id(65)
async def test_readyz_startup_incomplete_returns_503(monkeypatch: pytest.MonkeyPatch) -> None:
    """lifespan 未启动（startup_complete=False）：503 + 空 checks，不执行依赖探测。"""
    app = _minimal_app()
    monkeypatch.setitem(app.dependency_overrides, get_health_check_registry, lambda: _registry(_FailingCheck("redis")))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as anon:
        resp = await anon.get("/readyz")

    assert resp.status_code == 503
    assert resp.json() == {"status": "down", "checks": {}, **_Identity}


@pytest.mark.kiwi_id(65)
async def test_readyz_after_lifespan_startup_returns_200(
    client: AsyncClient, service_app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    """lifespan 启动完成后（startup_complete=True）就绪检查正常聚合。"""
    _inject_registry(service_app, monkeypatch, _registry(_PassingCheck("redis")))

    resp = await client.get("/readyz")

    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


@pytest.mark.kiwi_id(65)
async def test_readyz_draining_returns_503(monkeypatch: pytest.MonkeyPatch) -> None:
    """停机摘流中（draining=True）：503 + 空 checks（与启动未完成同形）。"""
    app = _minimal_app(drained=True)
    monkeypatch.setitem(app.dependency_overrides, get_health_check_registry, lambda: _registry(_PassingCheck("redis")))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as anon:
        resp = await anon.get("/readyz")

    assert resp.status_code == 503
    assert resp.json() == {"status": "down", "checks": {}, **_Identity}
