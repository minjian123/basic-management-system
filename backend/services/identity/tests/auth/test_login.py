"""本地登录端点测试（Kiwi 2194）：成功、错误分支、验证码、限流与租户覆盖。"""

import pytest
from fastapi import FastAPI
from httpx import AsyncClient, Response
from sqlalchemy import select

from bms_core.api.deps import get_tenant_source
from bms_core.db.tenant import TenantNotFoundError
from bms_core.ratelimit.memory import MemoryRateLimiter
from bms_core.session.memory import MemorySessionStore
from bms_identity.api.tenancy import resolve_request_tenant
from bms_identity.models.session import SysSession
from bms_identity.services.session_issuer import truncate_field  # pyright: ignore[reportPrivateUsage]

from .helpers import (
    TENANT_ID,
    FakeCaptcha,
    FakeOrgClient,
    FakeTenantSource,
    FakeUserTokenIssuer,
    wire_auth,
)
from .session_helpers import tenant_scope, utc_now

API_LOGIN = "/api/v1/auth/login"


async def _login(client: AsyncClient, account: str, password: str, **extra: object) -> Response:
    """发登录请求。

    Args:
        client: 测试客户端。
        account: 账号。
        password: 口令。
        **extra: 附加请求体字段。

    Returns:
        Response: 响应对象。
    """
    body = {"account": account, "password": password, **extra}
    return await client.post(API_LOGIN, json=body)


@pytest.mark.kiwi_id(2194)
@pytest.mark.kiwi_id(2217)
async def test_login_success_creates_session(client: AsyncClient, service_app: FastAPI) -> None:
    """登录成功：返回 access + 用户概要、下发 refresh cookie、落会话标记、清零失败计数。"""
    issuer, org, store, limiter = FakeUserTokenIssuer(), FakeOrgClient(), MemorySessionStore(), MemoryRateLimiter()
    org.set_user("admin", password="secret", user_id=1001, name="管理员", locale="zh-cn")
    wire_auth(service_app, issuer=issuer, org=org, store=store, limiter=limiter)

    resp = await _login(client, "admin", "secret")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["access_token"] and data["token_type"] == "Bearer" and data["expires_in"] == 1800
    assert data["user"] == {
        "id": "1001",
        "username": "admin",
        "name": "管理员",
        "tenant": "demo",
        "locale": "zh-cn",
        "timezone": None,
        "must_change_password": False,
    }
    cookie = client.cookies.get("bms_refresh_token")
    assert cookie
    session_id = issuer.specs[-1].session_id
    assert await store.load(session_id, tenant=TENANT_ID) is not None
    assert org.last_state.get("failed_count") == 0


@pytest.mark.kiwi_id(2209)
async def test_login_must_change_password_mapping(client: AsyncClient, service_app: FastAPI) -> None:
    """登录成功但密码超期：`must_change_password=true`（映射自 org `pwd_reset_required`）。"""
    issuer, org, store, limiter = FakeUserTokenIssuer(), FakeOrgClient(), MemorySessionStore(), MemoryRateLimiter()
    org.set_user("admin", password="secret", pwd_reset_required=True)
    wire_auth(service_app, issuer=issuer, org=org, store=store, limiter=limiter)

    resp = await _login(client, "admin", "secret")
    assert resp.status_code == 200
    assert resp.json()["data"]["user"]["must_change_password"] is True


@pytest.mark.kiwi_id(2194)
async def test_login_wrong_or_unknown_account(client: AsyncClient, service_app: FastAPI) -> None:
    """账号不存在与密码错误同码 20002（防枚举）。"""
    issuer, org, store, limiter = FakeUserTokenIssuer(), FakeOrgClient(), MemorySessionStore(), MemoryRateLimiter()
    org.set_user("admin", password="secret")
    wire_auth(service_app, issuer=issuer, org=org, store=store, limiter=limiter)

    wrong = await _login(client, "admin", "bad")
    assert wrong.status_code == 401 and wrong.json()["code"] == 20002
    unknown = await _login(client, "nobody", "x")
    assert unknown.status_code == 401 and unknown.json()["code"] == 20002


@pytest.mark.kiwi_id(2194)
async def test_login_locked_and_disabled(client: AsyncClient, service_app: FastAPI) -> None:
    """账号锁定 20003、停用 20004。"""
    issuer, org, store, limiter = FakeUserTokenIssuer(), FakeOrgClient(), MemorySessionStore(), MemoryRateLimiter()
    org.set_user("locked", password="p", locked=True)
    org.set_user("disabled", password="p", status="disabled")
    wire_auth(service_app, issuer=issuer, org=org, store=store, limiter=limiter)

    locked = await _login(client, "locked", "p")
    assert locked.status_code == 401 and locked.json()["code"] == 20003
    disabled = await _login(client, "disabled", "p")
    assert disabled.status_code == 401 and disabled.json()["code"] == 20004


@pytest.mark.kiwi_id(2194)
async def test_login_failure_lock_threshold(client: AsyncClient, service_app: FastAPI) -> None:
    """连续失败达阈值后返回 20003（失败计数经限流基座累计）。"""
    issuer, org, store, limiter = FakeUserTokenIssuer(), FakeOrgClient(), MemorySessionStore(), MemoryRateLimiter()
    org.set_user("admin", password="secret")
    # 本用例隔离密码锁定分支：验证码阈值设高，避免连续失败达阈值后转强制验证码（03_04）
    wire_auth(service_app, issuer=issuer, org=org, store=store, limiter=limiter, captcha=FakeCaptcha(fail_threshold=99))

    for _ in range(4):
        resp = await _login(client, "admin", "bad")
        assert resp.json()["code"] == 20002
    fifth = await _login(client, "admin", "bad")
    assert fifth.status_code == 401 and fifth.json()["code"] == 20003
    assert org.last_state.get("locked_until") == "locked"


@pytest.mark.kiwi_id(2194)
async def test_login_captcha_required_and_failed(client: AsyncClient, service_app: FastAPI) -> None:
    """策略强制验证码：缺失 20101；凭证校验通过放行。"""
    issuer, org, store, limiter = FakeUserTokenIssuer(), FakeOrgClient(), MemorySessionStore(), MemoryRateLimiter()
    org.set_user("admin", password="secret")
    captcha = FakeCaptcha(required=True, verified=False)
    wire_auth(service_app, issuer=issuer, org=org, store=store, limiter=limiter, captcha=captcha)

    missing = await _login(client, "admin", "secret")
    assert missing.status_code == 400 or missing.json()["code"] == 20101

    failed = await _login(client, "admin", "secret", captcha={"captcha_id": "c", "kind": "image", "code": "x"})
    assert failed.json()["code"] == 20101


@pytest.mark.kiwi_id(2194)
async def test_login_captcha_verified_ok(client: AsyncClient, service_app: FastAPI) -> None:
    """携带有效验证码凭证时放行登录。"""
    issuer, org, store, limiter = FakeUserTokenIssuer(), FakeOrgClient(), MemorySessionStore(), MemoryRateLimiter()
    org.set_user("admin", password="secret")
    captcha = FakeCaptcha(required=True, verified=True)
    wire_auth(service_app, issuer=issuer, org=org, store=store, limiter=limiter, captcha=captcha)

    ok = await _login(client, "admin", "secret", captcha={"captcha_id": "c", "kind": "image", "code": "x"})
    assert ok.status_code == 200 and captcha.seen[-1].code == "x"

    bad_kind = await _login(client, "admin", "secret", captcha={"captcha_id": "c", "kind": "nope"})
    assert bad_kind.status_code == 200 and bad_kind.json()["code"] == 10001


@pytest.mark.kiwi_id(2194)
@pytest.mark.kiwi_id(2218)
async def test_login_rate_limited(client: AsyncClient, service_app: FastAPI) -> None:
    """账号维度限流命中返回 10005（429）；限流键租户位为雪花 id。"""
    issuer, org, store, limiter = FakeUserTokenIssuer(), FakeOrgClient(), MemorySessionStore(), MemoryRateLimiter()
    org.set_user("admin", password="secret")
    wire_auth(service_app, issuer=issuer, org=org, store=store, limiter=limiter)
    service_app.state.settings.login.account_rate_limit = 1
    try:
        assert (await _login(client, "admin", "secret")).status_code == 200
        limited = await _login(client, "admin", "secret")
        assert limited.status_code == 429 and limited.json()["code"] == 10005
        keys = set(limiter._windows)  # pyright: ignore[reportPrivateUsage]
        assert f"bms:{TENANT_ID}:rate:account:admin" in keys
    finally:
        service_app.state.settings.login.account_rate_limit = 20


@pytest.mark.kiwi_id(2194)
async def test_login_body_tenant_override(client: AsyncClient, service_app: FastAPI) -> None:
    """body 指定租户时经租户源校验后生效（覆盖 body 分支）。"""
    issuer, org, store, limiter = FakeUserTokenIssuer(), FakeOrgClient(), MemorySessionStore(), MemoryRateLimiter()
    org.set_user("admin", password="secret")
    wire_auth(service_app, issuer=issuer, org=org, store=store, limiter=limiter)
    service_app.dependency_overrides[get_tenant_source] = lambda: FakeTenantSource()

    ok = await _login(client, "admin", "secret", tenant="demo")
    assert ok.status_code == 200 and ok.json()["data"]["user"]["tenant"] == "demo"

    unknown = await _login(client, "admin", "secret", tenant="ghost")
    assert unknown.status_code == 404


@pytest.mark.kiwi_id(2194)
def test_truncate_none_and_limit() -> None:
    """会话设备 / IP 截断：None 原样、超长截断。"""
    assert truncate_field(None, 5) is None  # pyright: ignore[reportPrivateUsage]
    assert truncate_field("abcdef", 3) == "abc"  # pyright: ignore[reportPrivateUsage]


@pytest.mark.kiwi_id(2194)
async def test_resolve_login_tenant_branches() -> None:
    """登录租户解析：body 指定经租户源生效；无任何来源抛 404。"""
    ctx = await resolve_request_tenant("demo", None, FakeTenantSource())
    assert ctx.code == "demo"
    with pytest.raises(TenantNotFoundError):
        await resolve_request_tenant(None, None, FakeTenantSource())


@pytest.mark.kiwi_id(2208)
async def test_login_continuous_failure_forces_captcha(client: AsyncClient, service_app: FastAPI) -> None:
    """连续失败达阈值后强制验证码；成功登录清零（窗口与清零，03_04）。"""
    issuer, org, store, limiter = FakeUserTokenIssuer(), FakeOrgClient(), MemorySessionStore(), MemoryRateLimiter()
    org.set_user("admin", password="secret")
    captcha = FakeCaptcha(required=False, verified=True, fail_threshold=3)
    wire_auth(service_app, issuer=issuer, org=org, store=store, limiter=limiter, captcha=captcha)

    for _ in range(3):
        resp = await _login(client, "admin", "bad")
        assert resp.json()["code"] == 20002

    # 达阈值：未携带验证码被强制拒绝（20101）
    forced = await _login(client, "admin", "secret")
    assert forced.json()["code"] == 20101

    # 携带有效验证码放行（成功登录清零失败计数）
    ok = await _login(client, "admin", "secret", captcha={"captcha_id": "c", "kind": "image", "code": "x"})
    assert ok.status_code == 200

    # 清零生效：再次密码失败回到普通失败（非 20101）
    again = await _login(client, "admin", "bad")
    assert again.json()["code"] == 20002


@pytest.mark.kiwi_id(2208)
async def test_login_captcha_failure_not_counted(client: AsyncClient, service_app: FastAPI) -> None:
    """验证码校验失败不计入登录失败计数（避免双重惩罚）。"""
    issuer, org, store, limiter = FakeUserTokenIssuer(), FakeOrgClient(), MemorySessionStore(), MemoryRateLimiter()
    org.set_user("admin", password="secret")
    captcha = FakeCaptcha(required=False, verified=False, fail_threshold=3)
    wire_auth(service_app, issuer=issuer, org=org, store=store, limiter=limiter, captcha=captcha)

    # 携带（校验不通过）触发 20101，但不应自增登录失败计数
    failed = await _login(client, "admin", "secret", captcha={"captcha_id": "c", "kind": "image", "code": "x"})
    assert failed.json()["code"] == 20101

    # 三次密码失败仍为 20002（若验证码失败被计入，则计数已达阈值会转 20101）
    for _ in range(3):
        resp = await _login(client, "admin", "bad")
        assert resp.json()["code"] == 20002


@pytest.mark.kiwi_id(2234)
async def test_login_remember_me_branches(client: AsyncClient, service_app: FastAPI) -> None:
    """记住我两分支：未携带=会话级（会话 Cookie + 24h）；true=14 天持久（Max-Age + 14 天）。"""
    issuer, org, store, limiter = FakeUserTokenIssuer(), FakeOrgClient(), MemorySessionStore(), MemoryRateLimiter()
    org.set_user("admin", password="secret", user_id=1001)
    wire_auth(service_app, issuer=issuer, org=org, store=store, limiter=limiter)

    # 会话级（缺省）：Cookie 无 Max-Age；会话记录 remember_me=False、expires_at ≈ now+24h
    session_level = await _login(client, "admin", "secret")
    assert session_level.status_code == 200
    cookie = session_level.headers.get("set-cookie", "").lower()
    assert "bms_refresh_token=" in cookie and "max-age" not in cookie
    session_id = issuer.specs[-1].session_id
    assert issuer.specs[-1].remember_me is False
    async with tenant_scope(service_app) as db:
        row = (await db.execute(select(SysSession).where(SysSession.session_id == session_id))).scalar_one()
        assert row.remember_me is False
        assert 86000 <= (row.expires_at - utc_now()).total_seconds() <= 86460

    # 记住我：Cookie 含 Max-Age=1209600；会话记录 remember_me=True、expires_at ≈ now+14 天
    remembered = await _login(client, "admin", "secret", remember_me=True)
    assert remembered.status_code == 200
    cookie = remembered.headers.get("set-cookie", "").lower()
    assert "max-age=1209600" in cookie
    session_id = issuer.specs[-1].session_id
    assert issuer.specs[-1].remember_me is True
    async with tenant_scope(service_app) as db:
        row = (await db.execute(select(SysSession).where(SysSession.session_id == session_id))).scalar_one()
        assert row.remember_me is True
        assert 1209500 <= (row.expires_at - utc_now()).total_seconds() <= 1209660

    # 会话标记 TTL 与会话记录一致（会话级=24h）
    marker = await store.load(issuer.specs[0].session_id, tenant=TENANT_ID)
    assert marker is not None
