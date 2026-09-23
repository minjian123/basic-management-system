"""边缘信任能力域测试（Kiwi 2166）：契约 / 占位 / 标记实现 / 工厂 / 授权下沉依赖。"""

from types import SimpleNamespace
from typing import Annotated, cast

import pytest
from fastapi import Depends
from httpx import ASGITransport, AsyncClient
from starlette.requests import Request
from starlette.types import Scope
from support_app import ApplicationFactory, lifespan

from bms_core.api.deps import get_edge_trust
from bms_core.core.assembly import MarkerEdgeTrustFactory
from bms_core.core.config import Settings
from bms_core.core.exceptions import AuthError
from bms_core.edge.base import BaseEdgeTrust, EdgeIdentity, require_edge_identity
from bms_core.edge.headers import (
    GATEWAY_IDENTITY_HEADER,
    GATEWAY_IDENTITY_VALUE,
    SERVICE_IDENTITY_HEADER,
    TENANT_ID_HEADER,
    USER_ID_HEADER,
    USER_SCOPES_HEADER,
    USER_SUBJECT_HEADER,
)
from bms_core.edge.marker import MarkerEdgeTrust
from bms_core.edge.null import NullEdgeTrust
from bms_core.edge.service_jwt import ServiceJwtEdgeTrust

pytestmark = pytest.mark.kiwi_id(2166)


def _factory(options: dict[str, object] | None = None) -> MarkerEdgeTrustFactory:
    """构造标记实现工厂（注入最小 settings 替身）。"""
    settings = cast("Settings", SimpleNamespace(edge=SimpleNamespace(options=options or {})))
    return MarkerEdgeTrustFactory(settings)


def test_null_edge_trust_is_always_untrusted() -> None:
    """占位实现恒定不信任、不引入假身份。"""
    decision = NullEdgeTrust().evaluate({USER_ID_HEADER: "42"})
    assert decision.trusted is False
    assert decision.identity is None


def test_marker_edge_trust_trusts_matching_marker() -> None:
    """标记命中即信任，并按身份头解析身份。"""
    headers = {
        GATEWAY_IDENTITY_HEADER: GATEWAY_IDENTITY_VALUE,
        USER_ID_HEADER: "42",
        TENANT_ID_HEADER: "acme",
        USER_SCOPES_HEADER: "user:read, user:write,, ",
        SERVICE_IDENTITY_HEADER: "svc-a",
    }
    decision = MarkerEdgeTrust(expected=GATEWAY_IDENTITY_VALUE).evaluate(headers)
    assert decision.trusted is True
    assert decision.identity == EdgeIdentity(
        user_id=42, tenant_code="acme", scopes=("user:read", "user:write"), service_identity="svc-a"
    )


def test_marker_edge_trust_rejects_missing_or_wrong_marker() -> None:
    """标记缺失 / 不符即不信任。"""
    guard = MarkerEdgeTrust(expected="bms-edge")
    assert guard.evaluate({}).trusted is False
    assert guard.evaluate({GATEWAY_IDENTITY_HEADER: "other"}).trusted is False


def test_edge_identity_parses_headers_case_insensitively() -> None:
    """头名大小写不敏感；非法 user_id 记 None，其余身份照常解析。"""
    identity = EdgeIdentity.from_headers(
        {
            USER_ID_HEADER.lower(): "not-a-number",
            USER_SUBJECT_HEADER.upper(): "u-123",
            TENANT_ID_HEADER.upper(): "acme",
        }
    )
    assert identity.user_id is None
    assert identity.subject == "u-123"
    assert identity.tenant_code == "acme"
    assert identity.scopes == ()


def test_edge_identity_subject_defaults_none_when_missing() -> None:
    """缺失主体头时 `subject` 为 None（加法扩展不破坏既有解析）。"""
    identity = EdgeIdentity.from_headers({USER_ID_HEADER: "7"})
    assert identity.user_id == 7
    assert identity.subject is None


def test_marker_factory_uses_option_and_default_value() -> None:
    """工厂期望值：`[edge].options.gateway_identity` 优先，缺省取基座常量。"""
    default_guard = _factory().create()
    assert default_guard.evaluate({GATEWAY_IDENTITY_HEADER: GATEWAY_IDENTITY_VALUE}).trusted is True

    custom_guard = _factory({"gateway_identity": "custom-edge"}).create()
    assert custom_guard.evaluate({GATEWAY_IDENTITY_HEADER: "custom-edge"}).trusted is True
    assert custom_guard.evaluate({GATEWAY_IDENTITY_HEADER: GATEWAY_IDENTITY_VALUE}).trusted is False


def test_require_edge_identity_reads_state_and_raises_without() -> None:
    """授权下沉依赖：有可信身份即返回；缺失抛 AuthError（20001 / 401）。"""
    scope: Scope = {"type": "http", "headers": [], "state": {"edge_identity": None}}
    with pytest.raises(AuthError) as excinfo:
        require_edge_identity(Request(scope))
    assert excinfo.value.code == 20001
    assert excinfo.value.http_status == 401

    scope["state"]["edge_identity"] = EdgeIdentity(user_id=7)
    assert require_edge_identity(Request(scope)).user_id == 7


async def test_default_provider_resolves_service_jwt_and_dependency() -> None:
    """应用装配：默认 provider 解析到 ServiceJwtEdgeTrust；路由经 get_edge_trust 取到实例。"""
    app = ApplicationFactory().create(None)
    async with lifespan(app):
        assert isinstance(app.state.edge, ServiceJwtEdgeTrust)
        assert app.state.plugin_providers["edge"] == "service_jwt"

        @app.get("/edge-probe")
        async def edge_probe(  # pyright: ignore[reportUnusedFunction]
            trust: Annotated[BaseEdgeTrust, Depends(get_edge_trust)],
        ) -> dict[str, object]:
            return {"key": trust.key, "type": type(trust).__name__}

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/edge-probe")

        assert resp.status_code == 200
        assert resp.json() == {"key": "edge", "type": "ServiceJwtEdgeTrust"}
