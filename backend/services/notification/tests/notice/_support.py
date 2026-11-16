"""公告域测试共用：造数 / 选项集替身 / 发件箱替身 / 应读人数替身。"""

# pyright: reportPrivateUsage=false, reportUnknownLambdaType=false, reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false, reportUnknownParameterType=false, reportDeprecated=false, reportUntypedFunctionDecorator=false, reportCallIssue=false
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import cast

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.context import (
    reset_current_tenant_id,
    reset_current_user_id,
    reset_tenant_context,
    set_current_tenant_id,
    set_current_user_id,
    set_tenant_context,
)
from bms_core.db.tenant import TenantContext
from bms_core.events.base import EventEnvelope
from bms_notification.domains.notification.models.notice import SysNotice, SysNoticeRead
from bms_notification.domains.notification.notice_constants import (
    NOTICE_PRIORITY_DEFAULT,
    NOTICE_STATUS_PUBLISHED,
    NOTICE_TYPE_DEFAULT,
)

__all__ = [
    "DEMO_TENANT",
    "FakeAudience",
    "FakeOptionSets",
    "Outbox",
    "add_notice",
    "add_receipt",
    "reset_user",
    "set_updated_at",
    "use_user",
    "utc_now",
]

DEMO_TENANT = TenantContext(code="demo", db_key="tenant_demo", name="演示租户", tenant_id=1001)


def use_user(user_id: int) -> tuple[object, object, object]:
    """设置租户（完整上下文 + 主键）与用户上下文。

    Args:
        user_id: 当前用户主键。

    Returns:
        tuple[object, object, object]: （租户上下文令牌, 租户主键令牌, 用户令牌）。
    """
    return (
        set_tenant_context(DEMO_TENANT),
        set_current_tenant_id(str(DEMO_TENANT.tenant_id)),
        set_current_user_id(user_id),
    )


def reset_user(tokens: tuple[object, object, object]) -> None:
    """复位上下文。

    Args:
        tokens: `use_user` 返回的令牌。
    """
    reset_tenant_context(tokens[0])  # pyright: ignore[reportArgumentType]
    reset_current_tenant_id(tokens[1])  # pyright: ignore[reportArgumentType]
    reset_current_user_id(tokens[2])  # pyright: ignore[reportArgumentType]


class FakeOptionSets:
    """选项集替身：默认全部通过；可指定某选项集的非法值。"""

    def __init__(self, *, invalid: ConcurrentStableDict[str, ConcurrentStableList[str]] | None = None) -> None:
        self.invalid = invalid or ConcurrentStableDict()

    def validate(self, value: str, *, option_set_key: str) -> ConcurrentStableList[str]:
        """按选项集返回违规清单。

        Args:
            value: 选项值。
            option_set_key: 选项集标识。

        Returns:
            ConcurrentStableList[str]: 违规原因（空 = 通过）。
        """
        values = self.invalid.get(option_set_key)
        if value == "unknown" or (values and value in values):
            return ConcurrentStableList((f"取值不在选项集 {option_set_key} 内",))
        return ConcurrentStableList()


class Outbox:
    """发件箱替身：记录事件信封。"""

    def __init__(self) -> None:
        self.events: ConcurrentStableList[EventEnvelope] = ConcurrentStableList()

    async def enqueue(self, session: object, event: EventEnvelope) -> str:
        """记录事件。

        Args:
            session: 会话（未使用）。
            event: 事件信封。

        Returns:
            str: 事件主键占位。
        """
        del session
        self.events.add(event)
        return str(len(self.events))


class FakeAudience:
    """应读人数替身。"""

    def __init__(self, count: int = 0, *, error: Exception | None = None) -> None:
        self._count = count
        self._error = error

    async def count_enabled(self) -> int:
        """返回预设人数或抛出预设异常。

        Returns:
            int: 启用用户数。

        Raises:
            Exception: 预设异常。
        """
        if self._error is not None:
            raise self._error
        return self._count


def utc_now() -> datetime:
    """当前 UTC naive 时间。

    Returns:
        datetime: 当前时间。
    """
    return datetime.now(UTC).replace(tzinfo=None)


def add_notice(
    session: AsyncSession,
    *,
    title: str,
    content: str = "<p>正文</p>",
    status: str = NOTICE_STATUS_PUBLISHED,
    notice_type: str = NOTICE_TYPE_DEFAULT,
    priority: str = NOTICE_PRIORITY_DEFAULT,
    is_top: bool = False,
    publish_at: datetime | None = None,
    expire_at: datetime | None = None,
) -> SysNotice:
    """造一条公告（未 flush）。

    Args:
        session: 回滚会话。
        title: 标题。
        content: 正文。
        status: 状态。
        notice_type: 类型。
        priority: 优先级。
        is_top: 置顶。
        publish_at: 发布时间（默认一小时前）。
        expire_at: 过期时间。

    Returns:
        SysNotice: 公告行。
    """
    row = SysNotice(
        title=title,
        content=content,
        type=notice_type,
        priority=priority,
        is_top=is_top,
        publish_at=publish_at or (utc_now() - timedelta(hours=1)),
        expire_at=expire_at,
        status=status,
    )
    session.add(row)
    return row


def add_receipt(
    session: AsyncSession, *, notice_id: int, user_id: int, read_at: datetime | None = None
) -> SysNoticeRead:
    """造一条已读回执（未 flush）。

    Args:
        session: 回滚会话。
        notice_id: 公告主键。
        user_id: 用户主键。
        read_at: 阅读时间。

    Returns:
        SysNoticeRead: 回执行。
    """
    row = SysNoticeRead(notice_id=notice_id, user_id=user_id, read_at=read_at or utc_now())
    session.add(row)
    return row


async def set_updated_at(session: AsyncSession, notice_id: int, value: datetime) -> None:
    """直接改公告更新时间（排序测试用；绕过 ORM 审计钩子）。

    Args:
        session: 回滚会话。
        notice_id: 公告主键。
        value: 更新时间。
    """
    await session.execute(update(SysNotice).where(SysNotice.id == notice_id).values(updated_at=value))
    await session.flush()


def cast_option_sets(fake: FakeOptionSets) -> object:
    """把选项集替身转成服务构造参数（测试内部使用）。

    Args:
        fake: 替身。

    Returns:
        object: 服务构造参数。
    """
    return cast("object", fake)
