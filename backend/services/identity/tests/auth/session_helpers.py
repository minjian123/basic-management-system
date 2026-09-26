"""会话管理测试共用夹具：登录建会话 + 直连租户库播种 + 依赖替身装配（Kiwi 2195）。"""

from __future__ import annotations

from contextlib import AbstractAsyncContextManager
from datetime import UTC, datetime, timedelta

from fastapi import FastAPI
from httpx import AsyncClient, Response

from bms_core.db.session import DbSession, session_scope
from bms_core.db.tenant import DEMO_TENANT
from bms_core.ratelimit.memory import MemoryRateLimiter
from bms_core.session.memory import MemorySessionStore
from bms_identity.models.session import SysSession

from .helpers import (
    FakeOrgClient,
    FakeUserTokenIssuer,
    RecordingRealtimePublisher,
    wire_auth,
    wire_publisher,
)

API_LOGIN = "/api/v1/auth/login"
API_SESSIONS = "/api/v1/sessions"
TENANT_HEADERS = {"X-Tenant-ID": DEMO_TENANT.tenant_code}


def utc_now() -> datetime:
    """当前 UTC 时间（naive）。

    Returns:
        datetime: UTC 时间。
    """
    return datetime.now(UTC).replace(tzinfo=None)


def wire_login(
    app: FastAPI,
    *,
    user_id: int = 1001,
    max_active: int | None = None,
    publisher: RecordingRealtimePublisher | None = None,
) -> tuple[FakeUserTokenIssuer, MemorySessionStore, RecordingRealtimePublisher]:
    """装配登录链路替身（签发者 / 会话存储 / 限流 / 广播记录）。

    Args:
        app: 应用实例。
        user_id: 演示用户 ID。
        max_active: 活跃会话上限（None 不改配置）。
        publisher: 广播记录替身（None 新建）。

    Returns:
        tuple: (签发者替身, 会话存储替身, 广播记录替身)。
    """
    issuer, org, store, limiter = FakeUserTokenIssuer(), FakeOrgClient(), MemorySessionStore(), MemoryRateLimiter()
    org.set_user("admin", password="secret", user_id=user_id, name="管理员")
    wire_auth(app, issuer=issuer, org=org, store=store, limiter=limiter)
    recorder = publisher or RecordingRealtimePublisher()
    wire_publisher(app, recorder)
    if max_active is not None:
        app.state.settings.session.max_active = max_active
    return issuer, store, recorder


async def login(client: AsyncClient, *, headers: dict[str, str] | None = None, **extra: object) -> Response:
    """发登录请求（默认账号 admin / secret）。

    Args:
        client: 测试客户端。
        headers: 附加请求头。
        **extra: 附加请求体字段。

    Returns:
        Response: 响应对象。
    """
    body = {"account": "admin", "password": "secret", **extra}
    return await client.post(API_LOGIN, json=body, headers=headers)


def tenant_scope(app: FastAPI) -> AbstractAsyncContextManager[DbSession]:
    """演示租户库会话上下文（直连播种用）。

    Args:
        app: 应用实例。

    Returns:
        AbstractAsyncContextManager[DbSession]: 会话上下文（未提交，需显式 commit）。
    """
    return session_scope(app.state.engine_registry, db_key=DEMO_TENANT.db_key, factory=app.state.session_factory)


async def seed_session(
    app: FastAPI,
    *,
    session_id: str,
    user_id: int = 1001,
    expires_at: datetime | None = None,
    revoked_at: datetime | None = None,
    device: str | None = None,
    ip: str | None = None,
    login_at: datetime | None = None,
) -> None:
    """直连租户库播种一条会话记录（覆盖过期 / 已撤销等分支）。

    Args:
        app: 应用实例。
        session_id: 会话 id（十进制字符串，须可转 int）。
        user_id: 用户 ID。
        expires_at: 过期时间（None 取 14 天后）。
        revoked_at: 撤销时间（None 表示有效）。
        device: 设备标识。
        ip: 登录 IP。
        login_at: 登录时间（None 取当前）。
    """
    now = utc_now()
    async with tenant_scope(app) as session:
        session.add(
            SysSession(
                id=int(session_id),
                session_id=session_id,
                user_id=user_id,
                refresh_token_hash="hash",
                device=device,
                ip=ip,
                login_at=login_at or now,
                expires_at=expires_at or (now + timedelta(days=14)),
                revoked_at=revoked_at,
            )
        )
        await session.commit()
