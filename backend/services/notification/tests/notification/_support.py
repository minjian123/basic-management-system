"""通知域测试共用：回滚会话开合口 / 造数 / 用户上下文。"""

# pyright: reportPrivateUsage=false, reportUnknownLambdaType=false, reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false, reportUnknownParameterType=false, reportDeprecated=false, reportUntypedFunctionDecorator=false, reportCallIssue=false
from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import cast

from sqlalchemy.ext.asyncio import AsyncSession

from bms_core.core.context import (
    reset_current_user_id,
    reset_tenant_context,
    set_current_user_id,
    set_tenant_context,
)
from bms_core.db.session import DbSession
from bms_core.db.tenant import TenantContext
from bms_notification.domains.notification.models.notification import SysNotification

DEMO_TENANT = TenantContext(code="demo", db_key="tenant_demo", name="演示租户", tenant_id=1001)


@asynccontextmanager
async def session_opener(session: AsyncSession) -> AsyncIterator[DbSession]:
    """把回滚会话包装成中心 / 消费者所需开合口。

    Args:
        session: 回滚会话。

    Yields:
        DbSession: 同一会话。
    """
    yield cast("DbSession", session)


def use_user(user_id: int) -> tuple[object, object]:
    """设置租户与用户上下文。

    Args:
        user_id: 当前用户主键。

    Returns:
        tuple[object, object]: （租户令牌, 用户令牌），供 `reset_user` 复位。
    """
    return set_tenant_context(DEMO_TENANT), set_current_user_id(user_id)


def reset_user(tokens: tuple[object, object]) -> None:
    """复位上下文。

    Args:
        tokens: `use_user` 返回的令牌。
    """
    reset_tenant_context(tokens[0])  # pyright: ignore[reportArgumentType]
    reset_current_user_id(tokens[1])  # pyright: ignore[reportArgumentType]


def add_notification(
    session: AsyncSession,
    *,
    user_id: int,
    title: str,
    notification_type: str = "system",
    content: str = "",
    is_read: bool = False,
    biz_type: str | None = None,
    biz_id: str | None = None,
    created_at: datetime | None = None,
) -> SysNotification:
    """造一条通知（未 flush）。

    Args:
        session: 回滚会话。
        user_id: 收件用户。
        title: 标题。
        notification_type: 类型。
        content: 正文。
        is_read: 已读。
        biz_type: 业务类型。
        biz_id: 业务标识。
        created_at: 创建时间（默认当前 UTC）。

    Returns:
        SysNotification: 通知行。
    """
    row = SysNotification(
        user_id=user_id,
        title=title,
        content=content,
        type=notification_type,
        biz_type=biz_type,
        biz_id=biz_id,
        is_read=is_read,
    )
    if created_at is not None:
        row.created_at = created_at
    session.add(row)
    return row


def utc_now() -> datetime:
    """当前 UTC naive 时间。

    Returns:
        datetime: 当前时刻。
    """
    return datetime.now(UTC).replace(tzinfo=None)


def earlier(minutes: int = 1) -> datetime:
    """当前时间前若干分钟。

    Args:
        minutes: 分钟数。

    Returns:
        datetime: 时间点。
    """
    return utc_now() - timedelta(minutes=minutes)
