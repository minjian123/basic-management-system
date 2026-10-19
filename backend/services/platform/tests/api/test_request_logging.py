"""请求日志与链路关联测试（Kiwi 63）：访问日志 / 排除路径 / 慢请求 / 异常 / trace 关联。"""

import json

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from starlette.types import Message, Receive, Scope, Send

from bms_core.api.middleware import RequestLoggingMiddleware, TraceIdMiddleware
from bms_core.application import service_lifespan as lifespan
from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.config import LogSettings, Settings, get_settings
from bms_core.core.context import get_current_request_id, get_current_trace_id
from bms_core.core.logging import configure_logging
from bms_core.tracing.base import TRACE_ID_HEADER
from bms_platform.main import ApplicationFactory


def _json_settings(*, slow_ms: int = 60000) -> Settings:
    """构造 JSON 渲染配置（其余取基线文件）。

    非慢请求用例把阈值设得远高于任何请求耗时：并行执行（`-n auto`）下 CPU 争抢会让单次请求耗时
    上到数百毫秒甚至过秒，阈值取缺省 1000ms 时同一请求会随机落到 `slow_request` 分支，
    导致「访问日志 = request」断言偶发失败（2026-10-19 CI 实测）。
    """
    return Settings(log=LogSettings(level="INFO", format="json", slow_request_ms=slow_ms))


def _build_app(*, slow_ms: int = 60000) -> FastAPI:
    """构造最小应用：链路 + 请求日志中间件 + 回显接口。"""
    app = FastAPI()
    app.add_middleware(TraceIdMiddleware)
    app.add_middleware(RequestLoggingMiddleware, slow_request_ms=slow_ms)

    @app.get("/whoami")
    async def whoami() -> dict[str, object]:  # pyright: ignore[reportUnusedFunction]  # bare-collections:allow（FastAPI 端点返回注解）
        return {"trace_id": get_current_trace_id(), "request_id": get_current_request_id()}

    return app


def _records(capsys: pytest.CaptureFixture[str]) -> ConcurrentStableList[ConcurrentStableDict[str, object]]:
    """读取 stdout 并按 JSON 行解析，**只保留本服务的日志事件**（跳过非 JSON 行与外部噪声）。

    外部线程也会以 JSON 形态写入 stdout——前序 DB 用例遗留的 aiosqlite 连接在后台收尾时
    会打 `executing <function Connection.stop...>`（structlog 把消息放在 `event` 键）；
    若不加筛选，`records[0]` 会被噪声顶掉（2026-10-13 实测的顺序敏感偶发失败）。

    Args:
        capsys: pytest 标准输出捕获夹具。

    Returns:
        ConcurrentStableList[ConcurrentStableDict[str, object]]: 本服务日志事件记录（按输出顺序）。
    """
    events = ("request", "slow_request", "uncaught_exception")
    records: ConcurrentStableList[ConcurrentStableDict[str, object]] = ConcurrentStableList()
    for line in capsys.readouterr().out.splitlines():
        text = line.strip()
        if not text.startswith("{"):
            continue
        record = ConcurrentStableDict(json.loads(text))
        if record.get("event") in events:
            records.add(record)
    return records


@pytest.mark.kiwi_id(63)
async def test_request_log_and_request_id_fallback(capsys: pytest.CaptureFixture[str]) -> None:
    """业务路由产生 INFO 访问行；无入站头时 trace_id 取 request_id 兜底。"""
    configure_logging(_json_settings())
    async with AsyncClient(transport=ASGITransport(app=_build_app()), base_url="http://test") as client:
        resp = await client.get("/whoami")

    assert resp.status_code == 200
    record = _records(capsys)[0]
    assert record["event"] == "request"
    assert record["method"] == "GET"
    assert record["path"] == "/whoami"
    assert record["status"] == 200
    assert isinstance(record["duration_ms"], (int, float))
    body = resp.json()
    assert record["request_id"] == body["request_id"]
    assert record["trace_id"] == body["trace_id"]
    assert record["request_id"] == record["trace_id"]
    assert len(str(record["request_id"])) == 32
    assert resp.headers[TRACE_ID_HEADER] == record["trace_id"]


@pytest.mark.kiwi_id(63)
async def test_inbound_trace_id_echoed(capsys: pytest.CaptureFixture[str]) -> None:
    """入站 X-Trace-Id 原样沿用：响应头回写、日志 trace_id 一致、request_id 独立。"""
    configure_logging(_json_settings())
    async with AsyncClient(transport=ASGITransport(app=_build_app()), base_url="http://test") as client:
        resp = await client.get("/whoami", headers={TRACE_ID_HEADER: "abc"})

    assert resp.headers[TRACE_ID_HEADER] == "abc"
    record = _records(capsys)[0]
    assert record["trace_id"] == "abc"
    assert record["request_id"] != "abc"
    assert len(str(record["request_id"])) == 32


@pytest.mark.kiwi_id(63)
async def test_excluded_paths_not_logged(capsys: pytest.CaptureFixture[str]) -> None:
    """探针与文档路径不产生访问日志（任何级别）。"""
    app = ApplicationFactory().create(None)
    async with lifespan(app):
        configure_logging(_json_settings())
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            for path in ("/healthz", "/readyz", "/docs", "/openapi.json"):
                await client.get(path)

        records = _records(capsys)
        assert [record for record in records if record["event"] in {"request", "slow_request"}] == []


@pytest.mark.kiwi_id(63)
async def test_client_ip_prefers_forwarded_for(capsys: pytest.CaptureFixture[str]) -> None:
    """来源 IP 取 `X-Forwarded-For` 首值（兼容 nginx 反代）。"""
    configure_logging(_json_settings())
    async with AsyncClient(transport=ASGITransport(app=_build_app()), base_url="http://test") as client:
        await client.get("/whoami", headers={"X-Forwarded-For": "1.2.3.4, 5.6.7.8"})

    record = _records(capsys)[0]
    assert record["client_ip"] == "1.2.3.4"


@pytest.mark.kiwi_id(63)
async def test_non_http_scope_passthrough() -> None:
    """非 HTTP 作用域（lifespan 等）直通，不进请求上下文、不记访问日志。"""
    sent: ConcurrentStableList[str] = ConcurrentStableList()

    async def downstream(scope: Scope, receive: Receive, send: Send) -> None:
        del scope, receive
        await send({"type": "lifespan.startup.complete"})

    async def receive() -> Message:
        return {"type": "lifespan.startup"}

    async def send(message: Message) -> None:
        sent.add(str(message["type"]))

    await RequestLoggingMiddleware(downstream)({"type": "lifespan"}, receive, send)
    assert sent == ["lifespan.startup.complete"]
    assert get_current_request_id() is None


@pytest.mark.kiwi_id(63)
async def test_slow_request_warning(capsys: pytest.CaptureFixture[str]) -> None:
    """超阈值请求整行升 WARNING（event=slow_request）。"""
    configure_logging(_json_settings(slow_ms=0))
    async with AsyncClient(transport=ASGITransport(app=_build_app(slow_ms=0)), base_url="http://test") as client:
        await client.get("/whoami")

    record = _records(capsys)[0]
    assert record["event"] == "slow_request"
    assert record["level"] == "warning"


@pytest.mark.kiwi_id(63)
async def test_uncaught_exception_logged_with_context(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """未捕获异常：响应 500 不回显堆栈；ERROR 行含堆栈与上下文；X-Request-Id 与日志同值。

    装配期中间件按 `[log].slow_request_ms` 取阈值，这里显式放宽（并行负载下请求可能过秒，
    否则访问行会随机落到 `slow_request` 分支）。
    """
    monkeypatch.setenv("BMS_LOG__SLOW_REQUEST_MS", "60000")
    get_settings.cache_clear()
    app = ApplicationFactory().create(None)
    async with lifespan(app):
        configure_logging(_json_settings(slow_ms=60000))

        @app.get("/boom")
        async def boom() -> None:  # pyright: ignore[reportUnusedFunction]
            raise RuntimeError("boom")

        async with AsyncClient(
            transport=ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test"
        ) as client:
            resp = await client.get("/boom")

        assert resp.status_code == 500
        assert "RuntimeError" not in resp.text
        assert "Traceback" not in resp.text
        records = _records(capsys)
        events = [record.get("event") for record in records]
        error = next((record for record in records if record["event"] == "uncaught_exception"), None)
        assert error is not None, f"未捕获异常事件缺失（已捕获事件：{events}）"
        access = next((record for record in records if record["event"] == "request"), None)
        assert access is not None, f"访问日志事件缺失（已捕获事件：{events}）"
        assert error["level"] == "error"
        assert "RuntimeError: boom" in str(error["exception"])
        assert error["trace_id"] == resp.headers[TRACE_ID_HEADER]
        assert resp.headers["X-Request-Id"] == error["request_id"]
        assert access["status"] == 500
