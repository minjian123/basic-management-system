"""找回密码端点测试（Kiwi 2210）：发起成功 / 防枚举 / 验证码 / 限流 / 重置与会话全失效。"""

import re

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import select

from bms_core.api.deps import get_rate_limiter
from bms_core.idp.state.memory import MemoryIdpStateStore
from bms_core.ratelimit.memory import MemoryRateLimiter
from bms_core.session.memory import MemorySessionStore
from bms_identity.models.session import SysSession
from tests_support.auth import issue_access_token

from .helpers import (
    TENANT_ID,
    FakeCaptcha,
    FakePlatformClient,
    FakeUserTokenIssuer,
    RecordingNotifier,
    RecordingRealtimePublisher,
    wire_auth,
    wire_password_reset,
    wire_publisher,
)
from .session_helpers import TENANT_HEADERS, login, seed_session, tenant_scope

API_FORGOT = "/api/v1/auth/forgot-password"
API_RESET = "/api/v1/auth/reset-password"
API_SESSIONS = "/api/v1/sessions"

CAPTCHA = {"captcha_id": "c", "kind": "image", "code": "x"}


async def _wire_reset(
    app: FastAPI,
    *,
    required: bool = True,
    verified: bool = True,
) -> tuple[
    FakeUserTokenIssuer,
    FakePlatformClient,
    MemorySessionStore,
    MemoryIdpStateStore,
    RecordingNotifier,
    FakeCaptcha,
    RecordingRealtimePublisher,
]:
    """装配找回密码链路替身（登录替身 + 流程状态 / 通知 / 验证码覆盖）。

    Args:
        app: 应用实例。
        required: 验证码场景是否强制。
        verified: 验证码凭证是否通过。

    Returns:
        tuple: (签发者, platform_client 替身, 会话存储, 流程状态存储, 通知记录, 验证码替身, 广播记录)。
    """
    issuer, platform_client, store, limiter = (
        FakeUserTokenIssuer(),
        FakePlatformClient(),
        MemorySessionStore(),
        MemoryRateLimiter(),
    )
    platform_client.set_user("admin", password="secret", user_id=1001, name="管理员", email="Admin@Example.com")
    wire_auth(app, issuer=issuer, platform_client=platform_client, store=store, limiter=limiter)
    states, notifier = MemoryIdpStateStore(), RecordingNotifier()
    captcha = FakeCaptcha(required=required, verified=verified, required_scene="reset_password")
    wire_password_reset(app, states=states, notifier=notifier, captcha=captcha)
    publisher = RecordingRealtimePublisher()
    wire_publisher(app, publisher)
    app.state.settings.password_reset.reset_url = "https://app.test/reset"
    return issuer, platform_client, store, states, notifier, captcha, publisher


def _token(notifier: RecordingNotifier) -> str:
    """从最近一条通知内容提取重置 token（链接形态）。

    Args:
        notifier: 通知记录替身。

    Returns:
        str: 重置令牌。
    """
    match = re.search(r"token=([A-Za-z0-9_-]+)&tenant=demo", notifier.messages[-1].content)
    assert match is not None, notifier.messages[-1].content
    return match.group(1)


@pytest.mark.kiwi_id(2210)
async def test_forgot_success_sends_link(client: AsyncClient, service_app: FastAPI) -> None:
    """发起成功：恒 `{sent: true}`、邮件通道送达登记邮箱、通知内容含一次性令牌链接。"""
    _issuer, _platform_client, _store, states, notifier, _captcha, _publisher = await _wire_reset(service_app)

    resp = await client.post(
        API_FORGOT, json={"identifier": "admin@example.com", "captcha": CAPTCHA}, headers=TENANT_HEADERS
    )
    assert resp.status_code == 200
    assert resp.json()["data"] == {"sent": True}
    assert len(notifier.messages) == 1
    message = notifier.messages[0]
    assert message.channel.value == "email"
    assert message.recipient == "Admin@Example.com"
    assert message.title == "BMS 密码重置"
    assert message.biz_type == "password_reset"

    token = _token(notifier)
    assert token in message.content
    payload = await states.consume(token, tenant=TENANT_ID, namespace="pwdreset")
    assert payload is not None and payload.get("user_id") == 1001 and payload.get("account") == "admin"


@pytest.mark.kiwi_id(2210)
async def test_forgot_anti_enumeration_constant_response(client: AsyncClient, service_app: FastAPI) -> None:
    """防枚举：不存在 / 停用 / 无联系方式一律同响应且不发送。"""
    _issuer, platform_client, _store, _states, notifier, _captcha, _publisher = await _wire_reset(service_app)
    platform_client.set_user("nocontact", password="x", user_id=2002)
    platform_client.set_user("banned", password="x", user_id=2003, status="disabled", email="banned@example.com")

    for identifier in ("ghost", "nocontact", "banned"):
        resp = await client.post(
            API_FORGOT, json={"identifier": identifier, "captcha": CAPTCHA}, headers=TENANT_HEADERS
        )
        assert resp.status_code == 200 and resp.json()["data"] == {"sent": True}
    assert notifier.messages == []


@pytest.mark.kiwi_id(2210)
async def test_forgot_captcha_enforced(client: AsyncClient, service_app: FastAPI) -> None:
    """验证码：策略强制未携带 / 凭证不通过 20101；形态非法 10001；失败不发送。"""
    _issuer, _platform_client, _store, _states, notifier, _captcha, _publisher = await _wire_reset(
        service_app, required=True, verified=False
    )

    missing = await client.post(API_FORGOT, json={"identifier": "admin"}, headers=TENANT_HEADERS)
    assert missing.status_code == 200 and missing.json()["code"] == 20101

    rejected = await client.post(API_FORGOT, json={"identifier": "admin", "captcha": CAPTCHA}, headers=TENANT_HEADERS)
    assert rejected.status_code == 200 and rejected.json()["code"] == 20101

    bad_kind = await client.post(
        API_FORGOT,
        json={"identifier": "admin", "captcha": {"captcha_id": "c", "kind": "nope", "code": "x"}},
        headers=TENANT_HEADERS,
    )
    assert bad_kind.status_code == 200 and bad_kind.json()["code"] == 10001
    assert notifier.messages == []


@pytest.mark.kiwi_id(2210)
async def test_forgot_account_rate_limited(client: AsyncClient, service_app: FastAPI) -> None:
    """账号维度限流：5 分钟内同标识第二次即 20006（429）。"""
    _ = await _wire_reset(service_app)

    first = await client.post(API_FORGOT, json={"identifier": "admin", "captcha": CAPTCHA}, headers=TENANT_HEADERS)
    assert first.status_code == 200 and first.json()["data"] == {"sent": True}

    second = await client.post(API_FORGOT, json={"identifier": "admin", "captcha": CAPTCHA}, headers=TENANT_HEADERS)
    assert second.status_code == 429 and second.json()["code"] == 20006


@pytest.mark.kiwi_id(2210)
@pytest.mark.kiwi_id(2218)
async def test_forgot_ip_rate_limited(client: AsyncClient, service_app: FastAPI) -> None:
    """IP 维度限流：同 IP 窗口内超上限即 20006（换标识不绕过）；限流键租户位为雪花 id。"""
    _ = await _wire_reset(service_app)
    service_app.state.settings.password_reset.ip_rate_limit = 1
    limiter = MemoryRateLimiter()
    service_app.dependency_overrides[get_rate_limiter] = lambda: limiter

    first = await client.post(API_FORGOT, json={"identifier": "admin", "captcha": CAPTCHA}, headers=TENANT_HEADERS)
    assert first.status_code == 200

    second = await client.post(
        API_FORGOT, json={"identifier": "someone-else", "captcha": CAPTCHA}, headers=TENANT_HEADERS
    )
    assert second.status_code == 429 and second.json()["code"] == 20006
    keys = set(limiter._windows)  # pyright: ignore[reportPrivateUsage]
    assert any(key.startswith(f"bms:{TENANT_ID}:rate:password-reset-ip:") for key in keys)


@pytest.mark.kiwi_id(2210)
async def test_reset_revokes_all_sessions_and_next_request_401(client: AsyncClient, service_app: FastAPI) -> None:
    """重置全链路：令牌一次性消费 → 改密 → 全部会话失效（黑名单 / 标记 / 广播）→ 原 access 下一请求 401。"""
    issuer, platform_client, store, _states, notifier, _captcha, publisher = await _wire_reset(service_app)
    assert (await login(client, headers=TENANT_HEADERS)).status_code == 200
    session_id = issuer.specs[-1].session_id
    await seed_session(service_app, session_id="2002", user_id=1001)

    forgot = await client.post(API_FORGOT, json={"identifier": "admin", "captcha": CAPTCHA}, headers=TENANT_HEADERS)
    assert forgot.status_code == 200
    token = _token(notifier)
    access = issue_access_token(session_id=session_id, tenant=TENANT_ID)

    reset = await client.post(API_RESET, json={"token": token, "new_password": "NewSecret1!"}, headers=TENANT_HEADERS)
    assert reset.status_code == 200 and reset.json()["data"] == {"reset": True}
    assert platform_client.users["admin"]["password"] == "NewSecret1!"

    async with tenant_scope(service_app) as session:
        rows = (
            (await session.execute(select(SysSession).where(SysSession.session_id.in_([session_id, "2002"]))))
            .scalars()
            .all()
        )
    assert len(rows) == 2 and all(row.revoked_at is not None for row in rows)
    assert await store.load(session_id, tenant=TENANT_ID) is None
    revoked_ids = {event.data.get("session_id") for event in publisher.events}
    assert {session_id, "2002"} <= revoked_ids
    assert all(event.event == "session.revoked" for event in publisher.events)

    after = await client.get(API_SESSIONS, headers={**TENANT_HEADERS, "Authorization": f"Bearer {access}"})
    assert after.status_code == 401 and after.json()["code"] == 20012
