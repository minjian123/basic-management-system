"""请求观测按业务域标注（07C `04_03`；Kiwi 编号归 `05_01` 统一登记）。

覆盖详细设计 §5 用例 9~10：访问日志带 `domain_key` / `unit_key`；请求指标带 `domain` / `unit` 标签；
归属不明的 API 请求记 `domain=unknown` 并单独告警（不丢样本）；配置不可读时标签回落 `unknown`。
"""

import json
from collections.abc import Iterator
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from bms_core.api.middleware import (
    RequestLoggingMiddleware,
    _request_domain,  # pyright: ignore[reportPrivateUsage]
    _request_unit,  # pyright: ignore[reportPrivateUsage]
)
from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableFrozenDict, ConcurrentStableList
from bms_core.core.config import LogSettings, Settings
from bms_core.core.logging import configure_logging
from bms_core.services.module_registry import register_domain_services, reset_domain_services
from tests_support.metrics import RecordingMetrics

_LOGGED_EVENTS = ("request", "slow_request", "request_domain_unknown")
"""本用例关心的访问日志事件（其余事件滤掉，避免噪声顶位）。"""


def _log_settings() -> Settings:
    """构造 JSON 渲染配置（其余取基线文件；中间件日志断言依赖 JSON 行形态）。

    Returns:
        Settings: 应用配置。
    """
    return Settings(log=LogSettings(level="INFO", format="json", slow_request_ms=60000))


def _app_state(*, unit: str = "grpops") -> SimpleNamespace:
    """构造中间件读取的最小应用状态（只用到 `[app].unit` / `[app].service`）。

    说明：`Settings(app=...)` 的入参会被子环境选择源覆盖（`settings_customise_sources` 的
    最高优先级源），故此处直接构造最小状态对象，避免牵连整个配置装配。

    Args:
        unit: 本实例部署单元标识。

    Returns:
        SimpleNamespace: 具备 `app.unit` / `app.service` 的状态对象。
    """
    return SimpleNamespace(app=SimpleNamespace(unit=unit, service="platform"))


def _build_app(settings: SimpleNamespace, metrics: RecordingMetrics | None = None) -> FastAPI:
    """构造最小应用：请求日志中间件 + 两个接口（已登记域 / 未登记域）。

    Args:
        settings: 应用状态（中间件按 `[app].unit` 打标）。
        metrics: 指标出口替身（None 表示不装配）。

    Returns:
        FastAPI: 测试应用。
    """
    app = FastAPI()
    app.state.settings = settings
    if metrics is not None:
        app.state.metrics = metrics
    app.add_middleware(RequestLoggingMiddleware, slow_request_ms=60000)

    @app.get("/api/v1/role/list")
    # bare-collections:allow（FastAPI 端点返回注解）
    async def role_list() -> dict[str, object]:  # pyright: ignore[reportUnusedFunction]
        return {"ok": True}

    @app.get("/api/v1/unregistered_domain/list")
    # bare-collections:allow（FastAPI 端点返回注解）
    async def unknown_domain() -> dict[str, object]:  # pyright: ignore[reportUnusedFunction]
        return {"ok": True}

    return app


def _records(capsys: pytest.CaptureFixture[str]) -> ConcurrentStableList[ConcurrentStableDict[str, object]]:
    """读出并过滤本用例关心的日志事件。

    Args:
        capsys: 标准输出捕获夹具。

    Returns:
        ConcurrentStableList[ConcurrentStableDict[str, object]]: 事件记录（按输出顺序）。
    """
    records: ConcurrentStableList[ConcurrentStableDict[str, object]] = ConcurrentStableList()
    for line in capsys.readouterr().out.splitlines():
        text = line.strip()
        if not text.startswith("{"):
            continue
        record = ConcurrentStableDict(json.loads(text))
        if record.get("event") in _LOGGED_EVENTS:
            records.add(record)
    return records


@pytest.fixture(autouse=True)
def _domains() -> Iterator[None]:
    """登记一个业务域供域段解析，用后复位。"""
    reset_domain_services()
    register_domain_services(ConcurrentStableFrozenDict({"role": "platform"}))
    yield
    reset_domain_services()


async def test_access_log_carries_domain_and_unit(capsys: pytest.CaptureFixture[str]) -> None:
    """访问日志带 `domain_key`（域段）与 `unit_key`（本实例单元）。"""
    configure_logging(_log_settings())
    async with AsyncClient(transport=ASGITransport(app=_build_app(_app_state())), base_url="http://test") as client:
        resp = await client.get("/api/v1/role/list")

    assert resp.status_code == 200
    record = _records(capsys)[0]
    assert record["event"] == "request"
    assert record["domain_key"] == "role"
    assert record["unit_key"] == "grpops"


async def test_metrics_carry_domain_and_unit_labels(capsys: pytest.CaptureFixture[str]) -> None:
    """请求指标带 `domain` / `unit` 标签（可按域聚合 / 过滤）。"""
    metrics = RecordingMetrics()
    configure_logging(_log_settings())
    async with AsyncClient(
        transport=ASGITransport(app=_build_app(_app_state(), metrics)), base_url="http://test"
    ) as client:
        await client.get("/api/v1/role/list")

    counters = [item for item in metrics.counters if item[0] == "bms_request_total"]
    assert counters, "请求计数应写入"
    labels = counters[0][2]
    assert labels is not None
    assert labels["domain"] == "role"
    assert labels["unit"] == "grpops"
    assert labels["status"] == "200"


async def test_unknown_domain_is_labelled_and_warned(capsys: pytest.CaptureFixture[str]) -> None:
    """未登记域段：样本记 `domain=unknown` 并单独告警（访问行照常记）。"""
    configure_logging(_log_settings())
    async with AsyncClient(transport=ASGITransport(app=_build_app(_app_state())), base_url="http://test") as client:
        await client.get("/api/v1/unregistered_domain/list")

    records = _records(capsys)
    events = [record["event"] for record in records]
    assert events == ["request", "request_domain_unknown"], "访问行 + 单独告警，不丢样本"
    assert all(record["domain_key"] == "unknown" for record in records)
    assert records[1]["path"] == "/api/v1/unregistered_domain/list"


def test_non_api_path_not_warned_but_labelled_unknown() -> None:
    """非 API 路径：标签为 `unknown`（探针等由排除清单另行处理），不产生域告警。"""
    scope = {"type": "http", "path": "/whoami", "app": SimpleNamespace(state=SimpleNamespace())}

    assert _request_domain(scope) == "unknown"


def test_unit_label_falls_back_when_settings_missing() -> None:
    """配置不可读（如裸应用）：单元标签回落服务标识或 `unknown`。"""
    assert _request_unit({"type": "http", "app": SimpleNamespace(state=SimpleNamespace())}) == "unknown"

    settings = SimpleNamespace(app=SimpleNamespace(unit="", service="identity"))
    scope = {"type": "http", "app": SimpleNamespace(state=SimpleNamespace(settings=settings))}
    assert _request_unit(scope) == "identity"


def test_domain_label_prefers_matched_route_template() -> None:
    """域标签取匹配路由的模板路径（避免原始路径与模板不一致时误判）。"""
    scope = {
        "type": "http",
        "path": "/api/v1/role/list",
        "route": SimpleNamespace(path="/api/v1/role/list"),
        "app": SimpleNamespace(state=SimpleNamespace()),
    }

    assert _request_domain(scope) == "role"
