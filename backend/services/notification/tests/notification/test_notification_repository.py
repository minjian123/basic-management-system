"""通知域仓储：分页 / 筛选 / 未读 / 批量已读 / 越权（Kiwi 2517）。"""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.testing.transaction import write_session
from bms_notification.domains.notification.repositories.notification import NotificationRepository
from notification._support import DEMO_TENANT, add_notification, earlier, reset_user, use_user

pytestmark = pytest.mark.kiwi_id(2517)


async def test_page_filters_and_count(shared_tenant_engine: AsyncEngine) -> None:
    """按用户 / 类型 / 已读 / 关键字分页，未读数正确。"""
    async with write_session(shared_tenant_engine) as session:
        add_notification(session, user_id=1, title="审批待办", notification_type="approval")
        add_notification(session, user_id=1, title="系统提示", is_read=True, created_at=earlier(2))
        add_notification(session, user_id=2, title="他人通知")
        await session.flush()
        repository = NotificationRepository(session)

        rows, total = await repository.page_for_user(1, page=1, size=10)
        assert total == 2
        assert {row.title for row in rows} == {"审批待办", "系统提示"}

        rows, total = await repository.page_for_user(1, page=1, size=10, notification_type="approval")
        assert total == 1
        assert rows[0].title == "审批待办"

        rows, total = await repository.page_for_user(1, page=1, size=10, is_read=True)
        assert total == 1
        assert rows[0].title == "系统提示"

        rows, total = await repository.page_for_user(1, page=1, size=10, keyword="系统")
        assert total == 1

        assert await repository.unread_count(1) == 1
        assert await repository.unread_count(2) == 1


async def test_mark_read_and_all(shared_tenant_engine: AsyncEngine) -> None:
    """批量已读只作用于本人，全部已读归零。"""
    async with write_session(shared_tenant_engine) as session:
        first = add_notification(session, user_id=1, title="A")
        second = add_notification(session, user_id=1, title="B")
        other = add_notification(session, user_id=2, title="C")
        await session.flush()
        repository = NotificationRepository(session)
        await repository.mark_read(1, ConcurrentStableList())
        await repository.mark_read(1, ConcurrentStableList((int(first.id), int(other.id))))
        await session.refresh(first)
        await session.refresh(second)
        await session.refresh(other)
        assert first.is_read is True
        assert second.is_read is False
        assert other.is_read is False

        await repository.mark_all_read(1)
        await session.refresh(second)
        assert second.is_read is True
        assert await repository.unread_count(1) == 0


async def test_get_any_and_tenant_context(shared_tenant_engine: AsyncEngine) -> None:
    """按主键取记录不限定用户；演示租户上下文可用。"""
    async with write_session(shared_tenant_engine) as session:
        row = add_notification(session, user_id=9, title="X")
        await session.flush()
        repository = NotificationRepository(session)
        assert (await repository.get_any(int(row.id))) is row
        assert (await repository.get_any(123456)) is None
        assert DEMO_TENANT.code == "demo"


def test_context_helpers() -> None:
    """测试辅助上下文设置 / 复位。"""
    tokens = use_user(1)
    reset_user(tokens)
