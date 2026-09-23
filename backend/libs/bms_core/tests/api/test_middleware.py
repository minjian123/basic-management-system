"""入站中间件测试（Kiwi 44 链路 id / Kiwi 63 request_id 兜底；Kiwi 2166 边缘净化与信任边界）。"""

from types import SimpleNamespace

import pytest
from fastapi import FastAPI, Request
from httpx import ASGITransport, AsyncClient
from starlette.types import Message, Receive, Scope, Send

from bms_core.api.middleware import EdgeGuardMiddleware, TraceIdMiddleware
from bms_core.core.context import (
    get_current_trace_id,
    get_current_user_id,
    reset_current_request_id,
    reset_current_trace_id,
    set_current_request_id,
    set_current_trace_id,
)
from bms_core.edge.base import BaseEdgeTrust
from bms_core.edge.headers import (
    GATEWAY_IDENTITY_HEADER,
    GATEWAY_IDENTITY_VALUE,
    SERVICE_IDENTITY_HEADER,
    TENANT_ID_HEADER,
    USER_ID_HEADER,
    USER_SCOPES_HEADER,
)
from bms_core.edge.marker import MarkerEdgeTrust
from bms_core.edge.null import NullEdgeTrust
from bms_core.tracing.base import TRACE_ID_HEADER, TRACE_ID_LENGTH


def _build_app() -> FastAPI:
    """构造带链路 id 中间件的测试应用（接口回显当前链路 id）。"""
    app = FastAPI()
    app.add_middleware(TraceIdMiddleware)

    @app.get("/whoami")
    async def whoami() -> dict[str, object]:  # pyright: ignore[reportUnusedFunction]
        return {"trace_id": get_current_trace_id()}

    return app


@pytest.mark.kiwi_id(44)
async def test_generates_trace_id_and_propagates_context() -> None:
    """无入站头时生成链路 id：响应头回写 32 位 hex，且接口内上下文可见同一值。"""
    async with AsyncClient(transport=ASGITransport(app=_build_app()), base_url="http://test") as client:
        resp = await client.get("/whoami")

    generated = resp.headers[TRACE_ID_HEADER]
    assert len(generated) == TRACE_ID_LENGTH
    assert resp.json() == {"trace_id": generated}


@pytest.mark.kiwi_id(44)
async def test_echoes_inbound_trace_id() -> None:
    """带入站链路 id 时原样沿用并回写（跨实例透传口径）。"""
    inbound = "b" * TRACE_ID_LENGTH
    async with AsyncClient(transport=ASGITransport(app=_build_app()), base_url="http://test") as client:
        resp = await client.get("/whoami", headers={TRACE_ID_HEADER: inbound})

    assert resp.headers[TRACE_ID_HEADER] == inbound
    assert resp.json() == {"trace_id": inbound}


@pytest.mark.kiwi_id(44)
async def test_resets_and_restores_previous_context() -> None:
    """请求结束复位到中间件之前的值，且各请求链路 id 相互独立。"""
    app = _build_app()
    outer = "c" * TRACE_ID_LENGTH
    token = set_current_trace_id(outer)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            first = await client.get("/whoami")
            second = await client.get("/whoami")
        first_trace = first.headers[TRACE_ID_HEADER]
        second_trace = second.headers[TRACE_ID_HEADER]
    finally:
        reset_current_trace_id(token)

    assert first_trace != second_trace
    assert first_trace != outer
    assert get_current_trace_id() is None


@pytest.mark.kiwi_id(63)
async def test_falls_back_to_request_id() -> None:
    """上下文已有 request_id（请求日志中间件先设）时，trace_id 取其兜底。"""
    request_id = "r" * TRACE_ID_LENGTH
    token = set_current_request_id(request_id)
    try:
        async with AsyncClient(transport=ASGITransport(app=_build_app()), base_url="http://test") as client:
            resp = await client.get("/whoami")
    finally:
        reset_current_request_id(token)

    assert resp.headers[TRACE_ID_HEADER] == request_id
    assert resp.json() == {"trace_id": request_id}


@pytest.mark.kiwi_id(44)
async def test_non_http_scope_passthrough() -> None:
    """非 HTTP 作用域（lifespan 等）直通：下游照常执行、不进链路上下文。"""
    sent: list[str] = []

    async def downstream(scope: Scope, receive: Receive, send: Send) -> None:
        del scope, receive
        await send({"type": "lifespan.startup.complete"})

    async def receive() -> Message:
        return {"type": "lifespan.startup"}

    async def send(message: Message) -> None:
        sent.append(str(message["type"]))

    await TraceIdMiddleware(downstream)({"type": "lifespan"}, receive, send)
    assert sent == ["lifespan.startup.complete"]
    assert get_current_trace_id() is None


def _build_edge_app(
    *,
    trust: BaseEdgeTrust | None = None,
    enforce: bool = False,
    exempt: tuple[str, ...] = (),
    with_settings: bool = True,
) -> FastAPI:
    """构造带边缘守卫中间件的测试应用（回显身份头 / 上下文 / 信任标记）。"""
    app = FastAPI()
    if with_settings:
        app.state.settings = SimpleNamespace(
            edge=SimpleNamespace(provider="marker", require_gateway_identity=enforce, exempt_paths=list(exempt))
        )
        app.state.edge = trust or MarkerEdgeTrust(expected=GATEWAY_IDENTITY_VALUE)
    app.add_middleware(EdgeGuardMiddleware)

    @app.get("/whoami")
    async def whoami(request: Request) -> dict[str, object]:  # pyright: ignore[reportUnusedFunction]
        return {
            "user_id": get_current_user_id(),
            "tenant": request.headers.get(TENANT_ID_HEADER),
            "service": request.headers.get(SERVICE_IDENTITY_HEADER),
            "scopes": request.headers.get(USER_SCOPES_HEADER),
            "trusted": getattr(request.state, "edge_trusted", None),
            "identity_user": getattr(getattr(request.state, "edge_identity", None), "user_id", None),
        }

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:  # pyright: ignore[reportUnusedFunction]
        return {"ok": "true"}

    return app


@pytest.mark.kiwi_id(2166)
async def test_strips_forged_identity_headers() -> None:
    """无条件剥除客户端伪造身份头（未信任时下游不可见）。"""
    app = _build_edge_app()
    forged = {
        USER_ID_HEADER: "999",
        SERVICE_IDENTITY_HEADER: "forged",
        USER_SCOPES_HEADER: "admin",
        GATEWAY_IDENTITY_HEADER: "forged-marker",
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/whoami", headers=forged)

    body = resp.json()
    assert body["user_id"] is None
    assert body["service"] is None
    assert body["scopes"] is None
    assert body["identity_user"] is None
    assert body["trusted"] is False


@pytest.mark.kiwi_id(2166)
async def test_injects_trusted_identity_headers_and_context() -> None:
    """信任时回写规范身份头、置请求态与 `current_user_id` 上下文。"""
    app = _build_edge_app(trust=MarkerEdgeTrust(expected=GATEWAY_IDENTITY_VALUE))
    headers = {
        GATEWAY_IDENTITY_HEADER: GATEWAY_IDENTITY_VALUE,
        USER_ID_HEADER: "42",
        TENANT_ID_HEADER: "acme",
        USER_SCOPES_HEADER: "user:read,user:write",
        SERVICE_IDENTITY_HEADER: "svc-a",
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/whoami", headers=headers)

    body = resp.json()
    assert body["user_id"] == 42
    assert body["identity_user"] == 42
    assert body["tenant"] == "acme"
    assert body["service"] == "svc-a"
    assert body["scopes"] == "user:read,user:write"
    assert body["trusted"] is True


@pytest.mark.kiwi_id(2166)
async def test_bypass_rejected_when_enforced() -> None:
    """旁路防护开：非豁免路径缺可信身份就地 401（20001）；带标记放行。"""
    app = _build_edge_app(
        trust=MarkerEdgeTrust(expected=GATEWAY_IDENTITY_VALUE),
        enforce=True,
        exempt=("/healthz",),
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        rejected = await client.get("/whoami")
        allowed = await client.get("/whoami", headers={GATEWAY_IDENTITY_HEADER: GATEWAY_IDENTITY_VALUE})
        probe = await client.get("/healthz")

    assert rejected.status_code == 401
    assert rejected.json()["code"] == 20001
    assert allowed.status_code == 200
    assert probe.status_code == 200


@pytest.mark.kiwi_id(2166)
async def test_legacy_tenant_header_kept_when_not_enforced() -> None:
    """未启用信任模式：客户端自选租户头保持既有行为（不回归）。"""
    app = _build_edge_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/whoami", headers={TENANT_ID_HEADER: "client-tenant"})

    assert resp.json()["tenant"] == "client-tenant"
    assert resp.json()["trusted"] is False


@pytest.mark.kiwi_id(2166)
async def test_enforced_mode_strips_client_tenant_header() -> None:
    """信任模式（旁路开关开）下客户端租户头被剥离（豁免路径放行但不采信）。"""
    app = _build_edge_app(
        trust=MarkerEdgeTrust(expected=GATEWAY_IDENTITY_VALUE),
        enforce=True,
        exempt=("/whoami",),
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/whoami", headers={TENANT_ID_HEADER: "evil"})

    assert resp.status_code == 200
    assert resp.json()["tenant"] is None


@pytest.mark.kiwi_id(2166)
async def test_missing_settings_is_noop_but_still_strips() -> None:
    """未装配（settings / 信任插件缺失）：不拒绝、仍剥除伪造身份头、不崩溃。"""
    app = _build_edge_app(with_settings=False)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/whoami", headers={USER_ID_HEADER: "999", GATEWAY_IDENTITY_HEADER: "x"})

    assert resp.status_code == 200
    assert resp.json()["user_id"] is None


@pytest.mark.kiwi_id(2166)
async def test_edge_guard_non_http_passthrough() -> None:
    """非 HTTP 作用域直通（下游照常执行）。"""
    sent: list[str] = []

    async def downstream(scope: Scope, receive: Receive, send: Send) -> None:
        del scope, receive
        await send({"type": "lifespan.startup.complete"})

    async def receive() -> Message:
        return {"type": "lifespan.startup"}

    async def send(message: Message) -> None:
        sent.append(str(message["type"]))

    await EdgeGuardMiddleware(downstream)({"type": "lifespan"}, receive, send)
    assert sent == ["lifespan.startup.complete"]


@pytest.mark.kiwi_id(2166)
async def test_null_edge_trust_never_trusts() -> None:
    """占位信任实现下即使带标记也不信任（剥头 + 无身份）。"""
    app = _build_edge_app(trust=NullEdgeTrust())
    headers = {GATEWAY_IDENTITY_HEADER: GATEWAY_IDENTITY_VALUE, USER_ID_HEADER: "42"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/whoami", headers=headers)

    assert resp.json()["trusted"] is False
    assert resp.json()["user_id"] is None
