"""双模入站鉴权依赖 `require_auth_or_service` 测试（Kiwi 2301，缺陷 #111）。

覆盖四条：服务身份（东西向直连、无用户会话）放行且不查会话；网关代发 `sub=gateway` 票据**不算**
服务身份（回落登录态路径，无用户凭证即 401）；用户令牌 / 网关边缘身份走 `require_auth` 全装配
（含会话标记校验）；无凭证、验签失败、服务标识为空一律 401（fail-closed）。
"""

from collections.abc import Iterator
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from starlette.requests import Request

from bms_core.api.base import DEFAULT_GATEWAY_SERVICE_IDENTITY, AuthContext, require_auth_or_service
from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableFrozenList, ConcurrentStableList
from bms_core.core.context import current_user_id
from bms_core.core.exceptions import AuthError, SessionAuthError
from bms_core.db.tenant import TenantContext
from bms_core.edge.base import EdgeIdentity
from bms_core.oauth.token import TOKEN_AUDIENCE_API, TOKEN_AUDIENCE_SERVICE
from bms_core.oauth.verify import BaseTokenVerifier, VerifiedToken
from bms_core.session.memory import MemorySessionStore

pytestmark = pytest.mark.kiwi_id(2301)

_SVC_TOK = "svc-tok"
"""服务 JWT 令牌串（替身识别用）。"""

_USR_TOK = "usr-tok"
"""用户令牌串（替身识别用）。"""

_DEMO_ID = "1001"


class _FakeTenantSource:
    """最小租户源替身（本地令牌路径按主键解析）。"""

    async def by_id(self, tenant_id: str) -> TenantContext:
        """按租户主键取租户。

        Args:
            tenant_id: 租户主键。

        Returns:
            TenantContext: 演示租户。

        Raises:
            AssertionError: 主键不符（用例内不可能发生）。
        """
        assert tenant_id == _DEMO_ID
        return TenantContext(code="demo", db_key="tenant_demo", name="演示租户", tenant_id=int(_DEMO_ID))


class _DualVerifier(BaseTokenVerifier):
    """占位校验器：按受众与令牌串注入身份（同一票据不可能同时通过两类受众）。"""

    plugin_name = "stub-require-auth-or-service"

    def __init__(
        self,
        *,
        service: str = "identity",
        service_token: str = _SVC_TOK,
        service_tenant: str | None = None,
        service_scopes: ConcurrentStableFrozenList[str] = ConcurrentStableFrozenList(()),  # noqa: B008
        service_error: bool = False,
        user: VerifiedToken | None = None,
        user_token: str = _USR_TOK,
        user_error: bool = False,
    ) -> None:
        """初始化。

        Args:
            service: 服务受众下返回的签发方标识（空串模拟占位校验器语义）。
            service_token: 被识别为服务票据的令牌串。
            service_tenant: 服务票据租户位。
            service_scopes: 服务票据授权范围。
            service_error: 服务受众下强制抛 `AuthError`。
            user: 用户受众下返回的声明（None 表示抛 `AuthError`）。
            user_token: 被识别为用户票据的令牌串。
            user_error: 用户受众下强制抛 `AuthError`。
        """
        self._service = service
        self._service_token = service_token
        self._service_tenant = service_tenant
        self._service_scopes = service_scopes
        self._service_error = service_error
        self._user = user
        self._user_token = user_token
        self._user_error = user_error
        self.audiences: ConcurrentStableList[str] = ConcurrentStableList()

    async def verify(self, token: str, *, audience: str) -> VerifiedToken:
        """按受众与令牌串返回声明或抛错。

        Args:
            token: 令牌串。
            audience: 期望受众（记录以供断言）。

        Returns:
            VerifiedToken: 注入的身份声明。

        Raises:
            AuthError: 注入的失败分支 / 令牌与受众不匹配。
        """
        assert token
        self.audiences.add(audience)
        if audience == TOKEN_AUDIENCE_SERVICE:
            if self._service_error or token != self._service_token:
                raise AuthError("票据验签失败")
            return VerifiedToken(
                subject=self._service,
                service=self._service,
                token_type="service",
                tenant_id=self._service_tenant,
                scopes=self._service_scopes,
            )
        if self._user_error or self._user is None or token != self._user_token:
            raise AuthError("票据验签失败")
        return self._user


def _request(
    *,
    headers: ConcurrentStableDict[str, str] | None = None,
    state: ConcurrentStableDict[str, object] | None = None,
    gateway_identity: str | None = "gateway",
    tenant_source: object | None = None,
) -> Request:
    """构造最小请求（含应用配置与会话替身所需状态）。

    Args:
        headers: 请求头。
        state: 请求态（`edge_identity`）。
        gateway_identity: `[gateway].service_identity` 取值；None 表示未配置 `[gateway]` 段。
        tenant_source: 租户源替身（装配到 `app.state.tenant_source`）。

    Returns:
        Request: Starlette 请求对象。
    """
    app = FastAPI()
    app.state.settings = SimpleNamespace(
        session=SimpleNamespace(device_check=False),
        gateway=None if gateway_identity is None else SimpleNamespace(service_identity=gateway_identity),
    )
    if tenant_source is not None:
        app.state.tenant_source = tenant_source
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/x",
        "headers": [(k.lower().encode("latin-1"), v.encode("latin-1")) for k, v in (headers or {}).items()],
        "app": app,
        "state": dict(state) if state else {},
    }
    return Request(scope)


def _svc_request(
    *,
    state: ConcurrentStableDict[str, object] | None = None,
    gateway_identity: str | None = "gateway",
    authorization: str = f"Bearer {_SVC_TOK}",
) -> Request:
    """构造携带服务票据的请求。

    Args:
        state: 请求态。
        gateway_identity: `[gateway].service_identity` 取值。
        authorization: `Authorization` 头（缺省为服务票据）。

    Returns:
        Request: Starlette 请求对象。
    """
    return _request(
        headers=ConcurrentStableDict({"Authorization": authorization}),
        state=state,
        gateway_identity=gateway_identity,
    )


def _usr_request() -> Request:
    """构造携带用户令牌的请求（含租户源替身）。

    Returns:
        Request: Starlette 请求对象。
    """
    return _request(
        headers=ConcurrentStableDict({"Authorization": f"Bearer {_USR_TOK}"}),
        tenant_source=_FakeTenantSource(),
    )


def _demo_tenant() -> TenantContext:
    """演示租户上下文（带雪花主键）。

    Returns:
        TenantContext: 演示租户。
    """
    return TenantContext(code="demo", db_key="tenant_demo", name="演示租户", tenant_id=int(_DEMO_ID))


def _user_verified(
    *,
    subject: str = "1001",
    tenant_id: str | None = _DEMO_ID,
    session_id: str = "s1",
    scopes: ConcurrentStableFrozenList[str] = ConcurrentStableFrozenList(("a",)),  # noqa: B008
) -> VerifiedToken:
    """构造校验通过的用户令牌声明。

    Args:
        subject: 主体。
        tenant_id: 租户主键（雪花 id 字符串）。
        session_id: 会话 id。
        scopes: 授权范围。

    Returns:
        VerifiedToken: 用户令牌声明。
    """
    return VerifiedToken(subject=subject, scopes=scopes, tenant_id=tenant_id, token_id=session_id)


@pytest.fixture(autouse=True)
def _reset_context() -> Iterator[None]:  # pyright: ignore[reportUnusedFunction]
    """用例前后复位用户上下文（服务分支不写上下文，断言需干净起点）。

    Yields:
        None: 用例运行期。
    """
    current_user_id.set(None)
    yield
    current_user_id.set(None)


async def _store_with(session_id: str) -> MemorySessionStore:
    """构造已写入指定会话标记的内存会话存储。

    Args:
        session_id: 会话 id。

    Returns:
        MemorySessionStore: 会话存储。
    """
    store = MemorySessionStore()
    await store.save(session_id, ConcurrentStableDict({"user_id": 1001, "tenant": _DEMO_ID}), tenant=_DEMO_ID)
    return store


async def test_service_identity_passes_without_session_check() -> None:
    """服务身份（非网关）：放行、`source="service"`，且不查会话标记（空存储亦通过）。"""
    verifier = _DualVerifier(service="identity")
    context = await require_auth_or_service(_svc_request(), verifier=verifier, store=MemorySessionStore())
    assert context == AuthContext(subject="identity", service_identity="identity", source="service")
    assert verifier.audiences == [TOKEN_AUDIENCE_SERVICE]
    assert current_user_id.get() is None


async def test_service_identity_keeps_token_tenant_and_scopes() -> None:
    """服务身份：令牌租户位与授权范围原样带入上下文（不写用户 / 租户请求上下文）。"""
    verifier = _DualVerifier(
        service="tenant", service_tenant=_DEMO_ID, service_scopes=ConcurrentStableFrozenList(("catalog",))
    )
    context = await require_auth_or_service(_svc_request(), verifier=verifier, store=MemorySessionStore())
    assert context.service_identity == "tenant"
    assert context.tenant_id == _DEMO_ID
    assert context.scopes == ("catalog",)
    assert context.session_id is None
    assert current_user_id.get() is None


async def test_gateway_ticket_excluded_falls_back_and_rejects() -> None:
    """网关代发 `sub=gateway` 票据不算服务身份：回落登录态路径 → 无用户凭证 401。"""
    verifier = _DualVerifier(service=DEFAULT_GATEWAY_SERVICE_IDENTITY)
    with pytest.raises(AuthError) as excinfo:
        await require_auth_or_service(_svc_request(), verifier=verifier, store=MemorySessionStore())
    assert excinfo.value.code == 20001
    assert excinfo.value.http_status == 401
    assert verifier.audiences == [TOKEN_AUDIENCE_SERVICE, TOKEN_AUDIENCE_API]


async def test_gateway_identity_configured_value_excluded() -> None:
    """`[gateway].service_identity` 配置值参与排除（配置为 `gw-x` 时 `gw-x` 票据回落登录态）。"""
    verifier = _DualVerifier(service="gw-x")
    with pytest.raises(AuthError):
        await require_auth_or_service(
            _svc_request(gateway_identity="gw-x"),
            verifier=verifier,
            store=MemorySessionStore(),
        )


async def test_gateway_identity_defaults_when_unconfigured() -> None:
    """未配置 `[gateway]` 段：缺省 `gateway` 标识同样被排除。"""
    verifier = _DualVerifier(service=DEFAULT_GATEWAY_SERVICE_IDENTITY)
    with pytest.raises(AuthError):
        await require_auth_or_service(
            _svc_request(gateway_identity=None),
            verifier=verifier,
            store=MemorySessionStore(),
        )


async def test_edge_service_identity_uses_service_branch() -> None:
    """边缘身份为**纯服务身份**（无用户主体、签发方非网关）：走服务分支，不查会话（空存储亦通过）。"""
    state = ConcurrentStableDict[str, object](
        {
            "edge_identity": EdgeIdentity(
                service_identity="identity", tenant_id=_DEMO_ID, scopes=ConcurrentStableFrozenList(("catalog",))
            )
        }
    )
    verifier = _DualVerifier(service="identity")
    context = await require_auth_or_service(_svc_request(state=state), verifier=verifier, store=MemorySessionStore())
    assert context == AuthContext(
        subject="identity",
        tenant_id=_DEMO_ID,
        scopes=ConcurrentStableFrozenList(("catalog",)),
        service_identity="identity",
        source="service",
    )
    assert verifier.audiences == []
    assert current_user_id.get() is None


async def test_edge_gateway_service_identity_falls_back() -> None:
    """边缘身份为网关身份（`sub=gateway`，无用户主体）：不算服务身份 → 登录态路径 401。"""
    state = ConcurrentStableDict[str, object](
        {"edge_identity": EdgeIdentity(service_identity=DEFAULT_GATEWAY_SERVICE_IDENTITY)}
    )
    verifier = _DualVerifier(service=DEFAULT_GATEWAY_SERVICE_IDENTITY)
    with pytest.raises(AuthError) as excinfo:
        await require_auth_or_service(_svc_request(state=state), verifier=verifier, store=MemorySessionStore())
    assert excinfo.value.code == 20001
    assert verifier.audiences == []


async def test_edge_blank_service_identity_falls_back() -> None:
    """边缘身份无用户主体且服务标识为空：不算服务身份 → 登录态路径 401。"""
    state = ConcurrentStableDict[str, object]({"edge_identity": EdgeIdentity()})
    with pytest.raises(AuthError):
        await require_auth_or_service(_svc_request(state=state), verifier=_DualVerifier(), store=MemorySessionStore())


async def test_edge_identity_uses_login_path() -> None:
    """边缘身份带用户主体：走登录态路径（即使同时携带服务票据头，不再探测服务身份）。"""
    store = await _store_with("s1")
    state = ConcurrentStableDict[str, object](
        {"edge_identity": EdgeIdentity(subject="1001", session_id="s1", tenant_code="demo")}
    )
    verifier = _DualVerifier(service="identity")
    context = await require_auth_or_service(_svc_request(state=state), verifier=verifier, store=store)
    assert context.source == "gateway"
    assert context.subject == "1001"
    assert verifier.audiences == []


async def test_edge_user_id_only_uses_login_path() -> None:
    """边缘身份仅有内部用户 id（无主体，无服务标识）：走登录态路径、主体回落 id 字符串。"""
    store = await _store_with("s2")
    state = ConcurrentStableDict[str, object](
        {"edge_identity": EdgeIdentity(user_id=1001, session_id="s2"), "tenant": _demo_tenant()}
    )
    context = await require_auth_or_service(_svc_request(state=state), verifier=_DualVerifier(), store=store)
    assert context.source == "gateway"
    assert context.subject == "1001"
    assert context.user_id == 1001


async def test_user_token_uses_login_path_with_session() -> None:
    """本地用户令牌：走登录态路径（租户接线 + 会话标记命中），服务受众探测失败后回落。"""
    store = await _store_with("s1")
    context = await require_auth_or_service(
        _usr_request(),
        verifier=_DualVerifier(user=_user_verified()),
        store=store,
    )
    assert context.source == "token"
    assert context.user_id == 1001
    assert context.tenant_code == "demo"
    assert context.session_id == "s1"
    assert current_user_id.get() == 1001


async def test_user_token_without_session_marker_rejected() -> None:
    """本地用户令牌但会话标记不存在（已踢出）→ 20012 / 401（登录态分支仍强校验）。"""
    with pytest.raises(SessionAuthError) as excinfo:
        await require_auth_or_service(
            _usr_request(),
            verifier=_DualVerifier(user=_user_verified()),
            store=MemorySessionStore(),
        )
    assert excinfo.value.code == 20012
    assert excinfo.value.http_status == 401


async def test_missing_credentials_rejected() -> None:
    """无凭证：401，且不进入任何校验（服务分支与登录态分支均不调用校验器）。"""
    verifier = _DualVerifier()
    with pytest.raises(AuthError) as excinfo:
        await require_auth_or_service(_request(), verifier=verifier, store=MemorySessionStore())
    assert excinfo.value.code == 20001
    assert verifier.audiences == []


async def test_non_bearer_header_rejected() -> None:
    """非 Bearer 授权头（如 Basic）：不作服务身份探测，直接 401。"""
    verifier = _DualVerifier()
    with pytest.raises(AuthError):
        await require_auth_or_service(
            _svc_request(authorization="Basic xyz"),
            verifier=verifier,
            store=MemorySessionStore(),
        )
    assert verifier.audiences == []


async def test_blank_service_identity_rejected() -> None:
    """服务受众校验通过但签发方标识为空（占位校验器语义）→ 不算服务身份，回落登录态后 401。"""
    verifier = _DualVerifier(service="")
    with pytest.raises(AuthError):
        await require_auth_or_service(_svc_request(), verifier=verifier, store=MemorySessionStore())
    assert verifier.audiences == [TOKEN_AUDIENCE_SERVICE, TOKEN_AUDIENCE_API]


async def test_invalid_service_ticket_falls_back_and_rejects() -> None:
    """服务受众验签失败：回落登录态路径，用户受众同样失败 → 401。"""
    verifier = _DualVerifier(service_error=True)
    with pytest.raises(AuthError):
        await require_auth_or_service(_svc_request(), verifier=verifier, store=MemorySessionStore())
    assert verifier.audiences == [TOKEN_AUDIENCE_SERVICE, TOKEN_AUDIENCE_API]
