"""登录态依赖 `require_auth` 真实化测试（01_05）：网关身份 / 本地令牌 / 会话标记 / 租户接线 / 失败分支。

直接构造请求并显式传入校验器与会话存储替身，覆盖 `require_auth` 全分支（不经服务应用框架）。
"""

from collections.abc import Mapping
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from starlette.requests import Request

from bms_core.api.base import AuthContext, require_auth
from bms_core.core.concurrent import ConcurrentStableDict
from bms_core.core.context import get_current_user_id, set_current_client_ip
from bms_core.core.exceptions import AuthError, SessionAuthError, TenantNotFoundError
from bms_core.db.tenant import DEMO_TENANT, TenantContext
from bms_core.edge.base import EdgeIdentity
from bms_core.oauth.verify import BaseTokenVerifier, VerifiedToken
from bms_core.session.memory import MemorySessionStore

pytestmark = pytest.mark.kiwi_id(2196)

_TOK = "bearer-test"

_DEMO_ID = "1001"
_ACME_ID = "2002"


class _FakeTenantSource:
    """最小租户源替身（本地令牌路径按 id 解析；补全 `TenantLookup` 三形态）。"""

    def __init__(self, tenants: dict[str, TenantContext] | None = None) -> None:
        self._tenants = tenants or {}

    async def by_code(self, code: str) -> TenantContext:
        """按编码取租户。"""
        for tenant in self._tenants.values():
            if tenant.code == code:
                return tenant
        raise TenantNotFoundError(f"未知租户：{code}")

    async def by_domain(self, domain: str) -> TenantContext:
        """按子域名取租户。"""
        for tenant in self._tenants.values():
            if tenant.domain == domain:
                return tenant
        raise TenantNotFoundError(f"未知租户域名：{domain}")

    async def by_id(self, tenant_id: str) -> TenantContext:
        """按租户主键（雪花 id 字符串）取租户。"""
        for tenant in self._tenants.values():
            if tenant.tenant_id is not None and str(tenant.tenant_id) == tenant_id:
                return tenant
        raise TenantNotFoundError(f"未知租户主键：{tenant_id}")


def _demo_tenant() -> TenantContext:
    """演示租户上下文（带雪花主键）。"""
    return TenantContext(code="demo", db_key="tenant_demo", name="演示租户", tenant_id=int(_DEMO_ID))


def _acme_tenant() -> TenantContext:
    """示例租户上下文（带雪花主键）。"""
    return TenantContext(code="acme", db_key="tenant_acme", name="示例租户", tenant_id=int(_ACME_ID))


def _source() -> _FakeTenantSource:
    """同时含演示 / 示例租户的源替身。"""
    return _FakeTenantSource({"demo": _demo_tenant(), "acme": _acme_tenant()})


class _StubVerifier(BaseTokenVerifier):
    """占位校验器：按注入结果返回声明或抛错。"""

    plugin_name = "stub-require-auth"

    def __init__(self, *, result: VerifiedToken | None = None, error: Exception | None = None) -> None:
        self._result = result
        self._error = error

    async def verify(self, token: str, *, audience: str) -> VerifiedToken:
        """返回注入结果 / 抛注入异常。

        Args:
            token: 令牌串（忽略）。
            audience: 期望受众（忽略）。

        Returns:
            VerifiedToken: 注入的声明。

        Raises:
            Exception: 注入的异常。
        """
        del token, audience
        if self._error is not None:
            raise self._error
        assert self._result is not None
        return self._result


def _verified(
    *,
    subject: str = "1001",
    tenant_id: str | None = _DEMO_ID,
    session_id: str = "s1",
    scopes: tuple[str, ...] = ("a",),
) -> VerifiedToken:
    """构造校验通过的令牌声明。

    Args:
        subject: 主体。
        tenant_id: 租户主键（雪花 id 字符串）。
        session_id: 会话 id。
        scopes: 授权范围。

    Returns:
        VerifiedToken: 令牌声明。
    """
    return VerifiedToken(subject=subject, scopes=scopes, tenant_id=tenant_id, token_id=session_id)


def _request(
    *,
    headers: dict[str, str] | None = None,
    state: Mapping[str, object] | None = None,
    device_check: bool = False,
    tenant_source: object | None = None,
) -> Request:
    """构造最小请求（含应用配置与会话替身所需状态）。

    Args:
        headers: 请求头。
        state: 请求态（`edge_identity` / `tenant`）。
        device_check: `[session].device_check` 取值。
        tenant_source: 租户源替身（装配到 `app.state.tenant_source`，供令牌租户 id 解析）。

    Returns:
        Request: Starlette 请求对象。
    """
    app = FastAPI()
    app.state.settings = SimpleNamespace(session=SimpleNamespace(device_check=device_check))
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


async def _store_with(session_id: str, *, tenant_id: str | None = None) -> MemorySessionStore:
    """构造已写入指定会话标记的内存会话存储。

    Args:
        session_id: 会话 id。
        tenant_id: 租户主键（内存实现忽略，仅语义标注）。

    Returns:
        MemorySessionStore: 会话存储。
    """
    store = MemorySessionStore()
    await store.save(session_id, ConcurrentStableDict({"user_id": 1001, "tenant": tenant_id}), tenant=tenant_id)
    return store


async def test_gateway_identity_builds_context() -> None:
    """网关路径：可信边缘身份组装 `AuthContext`、命中会话标记、写 `current_user_id`。"""
    store = await _store_with("s1")
    state = {
        "edge_identity": EdgeIdentity(subject="1001", tenant_code="demo", session_id="s1", scopes=("a",)),
        "tenant": _demo_tenant(),
    }
    context = await require_auth(_request(state=state), verifier=_StubVerifier(), store=store)
    assert context == AuthContext(
        subject="1001",
        user_id=1001,
        tenant_id=_DEMO_ID,
        tenant_code="demo",
        session_id="s1",
        scopes=("a",),
        source="gateway",
    )
    assert get_current_user_id() == 1001


async def test_gateway_identity_without_subject_uses_user_id() -> None:
    """网关路径：仅有内部用户 id（无主体）时主体回落为 id 字符串、租户取请求态。"""
    store = await _store_with("s2")
    state = {
        "edge_identity": EdgeIdentity(user_id=7, session_id="s2"),
        "tenant": _demo_tenant(),
    }
    context = await require_auth(_request(state=state), verifier=_StubVerifier(), store=store)
    assert context.subject == "7"
    assert context.user_id == 7
    assert context.tenant_code == "demo"
    assert context.tenant_id == _DEMO_ID


async def test_gateway_identity_service_only_rejected() -> None:
    """网关路径：纯服务身份（无用户主体 / id）→ 20001 / 401。"""
    state = {"edge_identity": EdgeIdentity(service_identity="svc-a")}
    with pytest.raises(AuthError) as excinfo:
        await require_auth(_request(state=state), verifier=_StubVerifier(), store=MemorySessionStore())
    assert excinfo.value.code == 20001
    assert excinfo.value.http_status == 401


@pytest.mark.kiwi_id(2217)
async def test_local_token_builds_context_and_adopts_tenant() -> None:
    """本地路径：Bearer 用户令牌组装身份；请求态无租户时经租户源按令牌 id 兜底写请求态。"""
    store = await _store_with("s3")
    request = _request(headers={"Authorization": f"Bearer {_TOK}"}, tenant_source=_source())
    context = await require_auth(request, verifier=_StubVerifier(result=_verified(session_id="s3")), store=store)
    assert context.source == "token"
    assert context.user_id == 1001
    assert context.tenant_id == _DEMO_ID
    assert context.tenant_code == "demo"
    assert request.scope["state"]["tenant"].code == "demo"


async def test_missing_and_invalid_token_rejected() -> None:
    """无令牌 / 校验失败 → 20001 / 401。"""
    with pytest.raises(AuthError) as missing:
        await require_auth(_request(), verifier=_StubVerifier(), store=MemorySessionStore())
    assert missing.value.code == 20001
    with pytest.raises(AuthError):
        await require_auth(
            _request(headers={"Authorization": f"Bearer {_TOK}"}),
            verifier=_StubVerifier(error=AuthError("bad")),
            store=MemorySessionStore(),
        )


async def test_local_token_without_tenant_source_rejected() -> None:
    """本地路径令牌带租户 id 但租户源未装配 → 20001 / 401（不再凭编码兜底）。"""
    request = _request(headers={"Authorization": f"Bearer {_TOK}"})
    with pytest.raises(AuthError) as excinfo:
        await require_auth(
            request, verifier=_StubVerifier(result=_verified(session_id="s3")), store=await _store_with("s3")
        )
    assert excinfo.value.code == 20001


async def test_non_numeric_subject_has_no_user_id() -> None:
    """非数字主体（外部 IdP 形态）→ `user_id` 为 None，主体保留。"""
    store = await _store_with("s4")
    context = await require_auth(
        _request(headers={"Authorization": f"Bearer {_TOK}"}, tenant_source=_source()),
        verifier=_StubVerifier(result=_verified(subject="u-42", session_id="s4")),
        store=store,
    )
    assert context.subject == "u-42"
    assert context.user_id is None


async def test_session_marker_missing_returns_20012() -> None:
    """会话标记不存在（已踢出 / 登出）→ `20012` / 401。"""
    request = _request(headers={"Authorization": f"Bearer {_TOK}"}, tenant_source=_source())
    with pytest.raises(SessionAuthError) as excinfo:
        await require_auth(
            request, verifier=_StubVerifier(result=_verified(session_id="gone")), store=MemorySessionStore()
        )
    assert excinfo.value.code == 20012
    assert excinfo.value.http_status == 401


async def test_session_id_missing_rejected() -> None:
    """令牌缺少会话标识 → 20001 / 401。"""
    with pytest.raises(AuthError):
        await require_auth(
            _request(headers={"Authorization": f"Bearer {_TOK}"}, tenant_source=_source()),
            verifier=_StubVerifier(result=_verified(session_id="")),
            store=MemorySessionStore(),
        )


async def test_device_check_mismatch_rejected() -> None:
    """`device_check=true`：设备 / IP 不一致 → 20012 / 401；一致放行。"""
    store = MemorySessionStore()
    await store.save("s5", ConcurrentStableDict({"user_id": 1, "ip": "10.0.0.1"}), tenant=_DEMO_ID)
    mismatch = _request(headers={"Authorization": f"Bearer {_TOK}"}, device_check=True, tenant_source=_source())
    set_current_client_ip("10.0.0.9")
    with pytest.raises(SessionAuthError) as excinfo:
        await require_auth(mismatch, verifier=_StubVerifier(result=_verified(session_id="s5")), store=store)
    assert excinfo.value.code == 20012

    match = _request(headers={"Authorization": f"Bearer {_TOK}"}, device_check=True, tenant_source=_source())
    set_current_client_ip("10.0.0.1")
    context = await require_auth(match, verifier=_StubVerifier(result=_verified(session_id="s5")), store=store)
    assert context.session_id == "s5"


async def test_cross_tenant_explicit_mismatch_rejected() -> None:
    """显式租户来源（X-Tenant-ID）解析 id 与令牌 id 不一致 → 跨租户拒绝（20001 / 401）。"""
    store = await _store_with("s6", tenant_id=_ACME_ID)
    request = _request(
        headers={"Authorization": f"Bearer {_TOK}", "X-Tenant-ID": "acme"},
        state={"tenant": _acme_tenant()},
    )
    with pytest.raises(AuthError) as excinfo:
        await require_auth(
            request, verifier=_StubVerifier(result=_verified(tenant_id=_DEMO_ID, session_id="s6")), store=store
        )
    assert excinfo.value.code == 20001


async def test_token_tenant_overrides_fallback() -> None:
    """无显式来源（回落演示租户）时以令牌租户 id 经租户源解析为准并写请求态。"""
    store = await _store_with("s7", tenant_id=_ACME_ID)
    request = _request(
        headers={"Authorization": f"Bearer {_TOK}"},
        state={"tenant": DEMO_TENANT},
        tenant_source=_source(),
    )
    context = await require_auth(
        request, verifier=_StubVerifier(result=_verified(tenant_id=_ACME_ID, session_id="s7")), store=store
    )
    assert context.tenant_id == _ACME_ID
    assert context.tenant_code == "acme"
    assert request.scope["state"]["tenant"].code == "acme"
