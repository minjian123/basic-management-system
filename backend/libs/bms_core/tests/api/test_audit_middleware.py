"""操作审计中间件护栏（06_01）：记录范围 / 参数脱敏与限长 / 动作回落 / 失败不阻塞。"""

import json
from types import SimpleNamespace
from typing import Any, cast

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from starlette.datastructures import Headers
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse
from starlette.types import Scope

from bms_core.api import audit_middleware as middleware_module
from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.config import AuditLogSettings, get_settings
from bms_core.db.tenant import TenantContext
from bms_core.events.base import EventEnvelope

pytestmark = pytest.mark.kiwi_id(2407)

_EVENTS: list[EventEnvelope] = []  # bare-collections:allow（测试断言容器）


class _FakeEmitter:
    """记录型发射器替身。"""

    def __init__(self, **kwargs: object) -> None:
        del kwargs

    async def emit(self, event: EventEnvelope) -> bool:
        """记录事件并返回成功。"""
        _EVENTS.append(event)
        return True


def _settings(**overrides: Any) -> AuditLogSettings:
    """构造审计日志参数（默认值与基线一致，可按用例覆盖）。"""
    base: dict[str, Any] = {  # bare-collections:allow（测试参数构造）
        "enabled": True,
        "record_methods": ConcurrentStableList(["POST", "PUT", "PATCH", "DELETE"]),
        "exclude_paths": ConcurrentStableList(["/api/v1/auth/login"]),
        "max_param_bytes": 8192,
        "query_default_days": 30,
        "max_query_days": 366,
        "precreate_months_ahead": 1,
        "chain_verify_months": 2,
    }
    base.update(overrides)
    return AuditLogSettings.model_validate(base)


def _app(settings: AuditLogSettings) -> FastAPI:
    """构造带审计中间件的测试应用。"""
    app = FastAPI()

    @app.post("/api/v1/things")
    async def create_thing(request: Request) -> JSONResponse:  # pyright: ignore[reportUnusedFunction]
        request.state.audit_action = "thing:create"
        body = await request.body()
        return JSONResponse({"length": len(body)})

    @app.post("/api/v1/plain")
    async def plain_thing(request: Request) -> JSONResponse:  # pyright: ignore[reportUnusedFunction]
        body = await request.body()
        return JSONResponse({"length": len(body)})

    @app.get("/api/v1/things")
    async def list_things() -> JSONResponse:  # pyright: ignore[reportUnusedFunction]
        return JSONResponse({"ok": True})

    @app.get("/api/v1/things/read")
    async def read_thing(request: Request) -> JSONResponse:  # pyright: ignore[reportUnusedFunction]
        request.state.audit_read = True
        return JSONResponse({"ok": True})

    @app.post("/api/v1/edge")
    async def edge(request: Request) -> JSONResponse:  # pyright: ignore[reportUnusedFunction]
        request.state.audit_action = "edge:create"
        request.scope["state"]["edge_identity"] = SimpleNamespace(user_id=5)
        request.scope["state"]["tenant"] = TenantContext(
            code="demo", db_key="tenant_demo", name="演示租户", tenant_id=1001
        )
        return JSONResponse({"ok": True})

    @app.post("/api/v1/tenant-fallback")
    async def tenant_fallback(request: Request) -> JSONResponse:  # pyright: ignore[reportUnusedFunction]
        request.state.audit_action = "tenant:create"
        request.scope["state"]["tenant_id"] = "2002"
        return JSONResponse({"ok": True})

    @app.post("/api/v1/auth/login")
    async def login() -> JSONResponse:  # pyright: ignore[reportUnusedFunction]
        return JSONResponse({"ok": True})

    @app.post("/api/v1/boom")
    async def boom() -> PlainTextResponse:  # pyright: ignore[reportUnusedFunction]
        raise RuntimeError("kaput")

    app.add_middleware(
        middleware_module.OperationAuditMiddleware,
        settings=settings,
        app_settings=get_settings(),
    )
    app.state.engine_registry = object()
    app.state.session_factory = object()
    return app


@pytest.fixture(autouse=True)
def _patch_emitter(monkeypatch: pytest.MonkeyPatch) -> None:
    """替换发射器（不落库）并清空记录。"""
    _EVENTS.clear()
    monkeypatch.setattr(middleware_module, "AuditEventEmitter", _FakeEmitter)


async def _post(
    app: FastAPI,
    path: str,
    *,
    json_body: object | None = None,
    content: bytes | None = None,
    headers: dict[str, str] | None = None,  # bare-collections:allow（HTTP 头映射）
):
    """发请求（异常不外抛，便于断言 500）。"""
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        if content is not None:
            return await client.post(path, content=content, headers=headers or {})
        return await client.post(path, json=json_body, headers=headers or {})


async def test_post_captures_masked_params_and_action() -> None:
    """写请求：参数脱敏、权限码动作、状态与耗时入事件；请求体原样回放下游。"""
    app = _app(_settings())
    body = {"username": "alice", "password": "secret", "nested": {"token": "t"}}
    response = await _post(app, "/api/v1/things?tenant=demo&access_token=x", json_body=body)
    assert response.status_code == 200
    assert response.json()["length"] == len(json.dumps(body, separators=(",", ":")))
    assert len(_EVENTS) == 1
    payload = _EVENTS[0].payload
    assert payload["action"] == "thing:create"
    assert payload["module"] == "thing"
    assert payload["status"] == 200
    assert payload["query"] == '{"access_token":"***","tenant":"demo"}'
    assert payload["params"] == '{"nested":{"token":"***"},"password":"***","username":"alice"}'
    assert int(str(payload["cost_time"])) >= 0


async def test_read_requires_explicit_declaration() -> None:
    """读方法默认不记；端点声明 `audit_read` 后才记；动作回落 `{模块}:query`。"""
    app = _app(_settings())
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        assert (await client.get("/api/v1/things")).status_code == 200
        assert _EVENTS == []
        assert (await client.get("/api/v1/things/read")).status_code == 200
    assert len(_EVENTS) == 1
    assert _EVENTS[0].payload["action"] == "things:query"
    assert _EVENTS[0].payload["module"] == "things"


async def test_excluded_and_disabled_do_not_emit() -> None:
    """排除路径 / 关闭开关：不产生事件。"""
    app = _app(_settings())
    assert (await _post(app, "/api/v1/auth/login", json_body={"a": 1})).status_code == 200
    assert _EVENTS == []

    disabled = _app(_settings(enabled=False))
    assert (await _post(disabled, "/api/v1/things", json_body={"a": 1})).status_code == 200
    assert _EVENTS == []


async def test_body_limit_and_non_json_skip_params() -> None:
    """超限 / 非 JSON：不解析请求体（params 为空），但请求体仍回放下游。"""
    app = _app(_settings(max_param_bytes=8))
    response = await _post(app, "/api/v1/things", json_body={"password": "secret"})
    assert response.json()["length"] > 8
    assert _EVENTS[-1].payload.get("params") is None

    multipart = await _post(
        app,
        "/api/v1/things",
        content=b'--x\r\nContent-Disposition: form-data; name="a"\r\n\r\n1\r\n--x--\r\n',
        headers={"Content-Type": "multipart/form-data; boundary=x"},
    )
    assert multipart.status_code == 200
    assert _EVENTS[-1].payload.get("params") is None


async def test_form_body_is_masked() -> None:
    """表单请求体：解析后脱敏。"""
    app = _app(_settings())
    await _post(
        app,
        "/api/v1/things",
        content=b"username=alice&password=secret",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert _EVENTS[-1].payload["params"] == '{"password":"***","username":"alice"}'


async def test_unhandled_exception_records_error_msg() -> None:
    """未捕获异常：记录异常摘要并原样抛给上层（响应 500）。"""
    app = _app(_settings())
    response = await _post(app, "/api/v1/boom")
    assert response.status_code == 500
    assert str(_EVENTS[-1].payload["error_msg"]).startswith("RuntimeError: kaput")
    assert _EVENTS[-1].payload["status"] == 500


async def test_fallback_module_from_path() -> None:
    """无权限码端点：模块回落路径首段、动作回落方法动词。"""
    app = _app(_settings())
    await _post(app, "/api/v1/plain", json_body={"a": 1})
    payload = _EVENTS[-1].payload
    assert payload["module"] == "plain"
    assert payload["action"] == "plain:create"


async def test_emitter_reused_and_prefix_excluded() -> None:
    """发射器懒建后复用；排除路径按前缀命中（含子路径）。"""
    app = _app(_settings())
    await _post(app, "/api/v1/things", json_body={"a": 1})
    await _post(app, "/api/v1/things", json_body={"b": 2})
    assert len(_EVENTS) == 2
    await _post(app, "/api/v1/auth/login/extra", json_body={"a": 1})
    assert len(_EVENTS) == 2


async def test_edge_identity_and_tenant_state() -> None:
    """请求态可信身份 / 租户上下文：用户 ID 与租户主键入事件。"""
    app = _app(_settings())
    await _post(app, "/api/v1/edge", json_body={"a": 1})
    payload = _EVENTS[-1].payload
    assert payload["user_id"] == "5"
    assert payload["tenant_id"] == "1001"

    await _post(app, "/api/v1/tenant-fallback", json_body={"a": 1})
    assert _EVENTS[-1].payload["tenant_id"] == "2002"


async def test_invalid_json_and_http_error_status() -> None:
    """非法 JSON 不落参数；无异常但 4xx/5xx 记 `HTTP {status}`。"""
    app = _app(_settings())
    await _post(app, "/api/v1/things", content=b"{bad", headers={"Content-Type": "application/json"})
    assert _EVENTS[-1].payload.get("params") is None

    response = await _post(app, "/api/v1/unknown", json_body={"a": 1})
    assert response.status_code == 404
    assert _EVENTS[-1].payload["error_msg"] == "HTTP 404"


async def test_forwarded_ip_and_excluded_probe() -> None:
    """来源 IP 取 `X-Forwarded-For` 首值；探针路径不记。"""
    app = _app(_settings())
    await _post(app, "/api/v1/things", json_body={"a": 1}, headers={"X-Forwarded-For": "1.2.3.4, 5.6.7.8"})
    assert _EVENTS[-1].payload["ip"] == "1.2.3.4"

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        assert (await client.get("/healthz")).status_code == 404
    assert len(_EVENTS) == 1


async def test_empty_json_body_and_chunked_overflow() -> None:
    """空 JSON 体不落参数；无 Content-Length 的分块体超限即停止缓冲。"""
    app = _app(_settings(max_param_bytes=8))
    await _post(app, "/api/v1/things", content=b"", headers={"Content-Type": "application/json"})
    assert _EVENTS[-1].payload.get("params") is None

    async def _chunks():
        yield b'{"a":'
        yield b'"0123456789"}'

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/api/v1/things", content=_chunks(), headers={"Content-Type": "application/json"})
    assert response.status_code == 200
    assert response.json()["length"] > 8
    assert _EVENTS[-1].payload.get("params") is None


def test_helper_branches() -> None:
    """辅助函数分支：动作无冒号回落、Content-Length 非法按 0、空查询串 / 非 JSON 体。"""
    scope = cast("Scope", {"method": "POST", "path": "/api/v1/things"})
    module, action = middleware_module._module_of(scope, "user")  # pyright: ignore[reportPrivateUsage]
    assert (module, action) == ("user", "user:create")
    assert middleware_module._module_of(scope, ":create") == (  # pyright: ignore[reportPrivateUsage]
        "things",
        "things:create",
    )
    assert (
        middleware_module.OperationAuditMiddleware._content_length(  # pyright: ignore[reportPrivateUsage]
            Headers({"content-length": "abc"})
        )
        == 0
    )
    assert (
        middleware_module.OperationAuditMiddleware._content_length(  # pyright: ignore[reportPrivateUsage]
            Headers({"content-length": "12"})
        )
        == 12
    )
    assert middleware_module._mask_query("&") is None  # pyright: ignore[reportPrivateUsage]
    assert middleware_module._mask_body("text/plain", b"x") is None  # pyright: ignore[reportPrivateUsage]
    assert middleware_module._mask_body("application/json", b"") is None  # pyright: ignore[reportPrivateUsage]
