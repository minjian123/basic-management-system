"""会话管理测试共用夹具：登录建会话 + 直连租户库播种 + 依赖替身装配（Kiwi 2195）。

单库叠加口径（04-6-2）：`sys_session` 落**共享租户库**，全 worker 共用。本模块因此提供
`uid()` / `sid()` 两个命名空间派生助手——会话行的用户主键与会话主键一律按用例派生，
查询与断言（列表 `user_id` 筛选、仓储 `count_active(user_id=…)`）只认本用例的行；
**不再整表清空**（`auth/conftest.py` 已取消逐例 `delete(SysSession)`，它会在并行下删掉
他人用例正在断言的会话）。

账号（`FakePlatformClient.set_user("admin", …)`）保持固定：它是**每用例一份的内存替身键**，
不落任何库表；落库的只有 `user_id`，故派生点是 `user_id`。
"""

from __future__ import annotations

from contextlib import AbstractAsyncContextManager
from datetime import UTC, datetime, timedelta

from fastapi import FastAPI
from httpx import AsyncClient, Response

from bms_core.core.concurrent import ConcurrentStableDict
from bms_core.db.session import DbSession, session_scope
from bms_core.db.tenant import DEMO_TENANT
from bms_core.models.identity.session import SysSession
from bms_core.ratelimit.memory import MemoryRateLimiter
from bms_core.session.memory import MemorySessionStore
from bms_core.testing.namespace import Namespace
from tests_support.auth import TEST_SESSION_ID

from .helpers import (
    TENANT_ID,
    FakePlatformClient,
    FakeUserTokenIssuer,
    RecordingRealtimePublisher,
    wire_auth,
    wire_publisher,
)

API_LOGIN = "/api/v1/auth/login"
API_SESSIONS = "/api/v1/sessions"
TENANT_HEADERS: ConcurrentStableDict[str, str] = ConcurrentStableDict({"X-Tenant-ID": DEMO_TENANT.code})


def utc_now() -> datetime:
    """当前 UTC 时间（naive）。

    Returns:
        datetime: UTC 时间。
    """
    return datetime.now(UTC).replace(tzinfo=None)


def uid(ns: Namespace, slot: int = 0) -> int:
    """本用例的用户主键（会话行按它划命名空间，叠加下不与他人行相撞）。

    Args:
        ns: 用例命名空间。
        slot: 同用例内的用户序号（同一用例需要多个用户时区分）。

    Returns:
        int: 用户主键（雪花量级，落 `sys_session.user_id`）。
    """
    return int(ns.prefix[2:], 16) * 100 + slot


def sid(ns: Namespace, slot: int = 0) -> str:
    """本用例的会话主键（= 会话 id，十进制字符串；`id` 与 `session_id` 同值）。

    Args:
        ns: 用例命名空间。
        slot: 同用例内的会话序号。

    Returns:
        str: 会话 id（可 `int()`，且与他人会话不撞主键）。
    """
    return str(int(ns.prefix[2:], 16) * 100 + slot)


async def wire_login(
    app: FastAPI,
    *,
    ns: Namespace,
    user_id: int | None = None,
    max_active: int | None = None,
    publisher: RecordingRealtimePublisher | None = None,
) -> tuple[FakeUserTokenIssuer, MemorySessionStore, RecordingRealtimePublisher]:
    """装配登录链路替身（签发者 / 会话存储 / 限流 / 广播记录）。

    会话存储为进程内替身；预置一枚「默认测试令牌」的会话标记，使受保护路由在 01_05 真实登录态
    依赖下仍可由测试客户端默认令牌通过（不干扰登录产生的真实会话与计数）。

    Args:
        app: 应用实例。
        ns: 用例命名空间（缺省用户主键由它派生）。
        user_id: 演示用户 ID（缺省 `uid(ns)`；须与断言口径一致）。
        max_active: 活跃会话上限（None 不改配置）。
        publisher: 广播记录替身（None 新建）。

    Returns:
        tuple: (签发者替身, 会话存储替身, 广播记录替身)。
    """
    subject = uid(ns) if user_id is None else user_id
    issuer, platform_client, store, limiter = (
        FakeUserTokenIssuer(),
        FakePlatformClient(),
        MemorySessionStore(),
        MemoryRateLimiter(),
    )
    platform_client.set_user("admin", password="secret", user_id=subject, name="管理员")
    await store.save(
        TEST_SESSION_ID,
        ConcurrentStableDict({"user_id": subject, "tenant": TENANT_ID}),
        tenant=TENANT_ID,
    )
    wire_auth(app, issuer=issuer, platform_client=platform_client, store=store, limiter=limiter)
    recorder = publisher or RecordingRealtimePublisher()
    wire_publisher(app, recorder)
    if max_active is not None:
        app.state.settings.session.max_active = max_active
    return issuer, store, recorder


async def login(
    client: AsyncClient, *, headers: ConcurrentStableDict[str, str] | None = None, **extra: object
) -> Response:
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
    user_id: int,
    expires_at: datetime | None = None,
    revoked_at: datetime | None = None,
    device: str | None = None,
    ip: str | None = None,
    login_at: datetime | None = None,
    refresh_token_hash: str = "hash",
    remember_me: bool | None = None,
) -> None:
    """直连租户库播种一条会话记录（覆盖过期 / 已撤销等分支）。

    `session_id` / `user_id` 必须来自本用例命名空间（`sid()` / `uid()`）：共享租户库上固定值
    会与他人用例撞主键或串行断言。

    Args:
        app: 应用实例。
        session_id: 会话 id（十进制字符串，须可转 int；取 `sid(ns, n)`）。
        user_id: 用户 ID（取 `uid(ns, n)`）。
        expires_at: 过期时间（None 取 14 天后）。
        revoked_at: 撤销时间（None 表示有效）。
        device: 设备标识。
        ip: 登录 IP。
        login_at: 登录时间（None 取当前）。
        refresh_token_hash: refresh 哈希（轮换比对用；缺省占位 `hash`）。
        remember_me: 是否记住我（None=历史行）。
    """
    now = utc_now()
    async with tenant_scope(app) as session:
        session.add(
            SysSession(
                id=int(session_id),
                session_id=session_id,
                user_id=user_id,
                refresh_token_hash=refresh_token_hash,
                device=device,
                ip=ip,
                login_at=login_at or now,
                expires_at=expires_at or (now + timedelta(days=14)),
                remember_me=remember_me,
                revoked_at=revoked_at,
            )
        )
        await session.commit()
