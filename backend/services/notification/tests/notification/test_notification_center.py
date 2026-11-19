"""通知中心真实实现：列表 / 查看即已读 / 未读 / 批量 / 删除 / 越权（Kiwi 2517）。"""

# pyright: reportPrivateUsage=false, reportUnknownLambdaType=false, reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false, reportUnknownParameterType=false, reportDeprecated=false, reportUntypedFunctionDecorator=false, reportCallIssue=false
from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import cast
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.exceptions import (
    NotificationBatchInvalidError,
    NotificationDeleteForbiddenError,
    NotificationForbiddenError,
    NotificationNotFoundError,
    ParamError,
)
from bms_core.db.session import DbSession
from bms_core.schemas.filters import BaseFilterQuery, FilterSpec
from bms_core.schemas.pagination import BasePageQuery
from bms_core.testing.transaction import write_session
from bms_notification.domains.notification.center import DatabaseNotificationCenter
from notification._support import add_notification, reset_user, session_opener, use_user

pytestmark = pytest.mark.kiwi_id(2517)


async def test_detail_and_unread(shared_tenant_engine: AsyncEngine) -> None:
    """详情查看即已读；mark_read=False 不改状态；未读数下降。"""
    async with write_session(shared_tenant_engine) as session:
        row = add_notification(session, user_id=1, title="A")
        await session.flush()
        tokens = use_user(1)
        try:
            center = DatabaseNotificationCenter(session_opener=lambda: session_opener(session), transactional=False)
            assert await center.unread_count() == 1
            preview = await center.detail(int(row.id), mark_read=False)
            assert preview.is_read is False
            detail = await center.detail(int(row.id))
            assert detail.is_read is True
            assert await center.unread_count() == 0
        finally:
            reset_user(tokens)


async def test_list_with_filters(shared_tenant_engine: AsyncEngine) -> None:
    """列表按类型 / 已读筛选。"""
    async with write_session(shared_tenant_engine) as session:
        add_notification(session, user_id=1, title="A", notification_type="approval")
        add_notification(session, user_id=1, title="B", is_read=True)
        await session.flush()
        tokens = use_user(1)
        try:
            center = DatabaseNotificationCenter(session_opener=lambda: session_opener(session), transactional=False)
            page = await center.list(
                BaseFilterQuery(filters=ConcurrentStableList((FilterSpec(field="type", value="approval"),))),
                BasePageQuery(),
            )
            assert page.total == 1
            page = await center.list(
                BaseFilterQuery(filters=ConcurrentStableList((FilterSpec(field="is_read", value=1),))),
                BasePageQuery(),
            )
            assert page.total == 1
        finally:
            reset_user(tokens)


async def test_mark_read_and_all(shared_tenant_engine: AsyncEngine) -> None:
    """批量 / 全部已读与参数校验。"""
    async with write_session(shared_tenant_engine) as session:
        first = add_notification(session, user_id=1, title="A")
        add_notification(session, user_id=1, title="B")
        await session.flush()
        tokens = use_user(1)
        try:
            center = DatabaseNotificationCenter(session_opener=lambda: session_opener(session), transactional=False)
            assert await center.mark_read(ConcurrentStableList((int(first.id),))) == 1
            assert await center.mark_all_read() == 0
            with pytest.raises(NotificationBatchInvalidError):
                await center.mark_read(ConcurrentStableList())
            with pytest.raises(NotificationBatchInvalidError):
                await center.mark_read(ConcurrentStableList(range(501)))
        finally:
            reset_user(tokens)


async def test_delete_and_forbidden(shared_tenant_engine: AsyncEngine) -> None:
    """删除本人通知；他人通知拒绝；不存在拒绝。"""
    async with write_session(shared_tenant_engine) as session:
        own = add_notification(session, user_id=1, title="A")
        other = add_notification(session, user_id=2, title="B")
        await session.flush()
        tokens = use_user(1)
        try:
            center = DatabaseNotificationCenter(session_opener=lambda: session_opener(session), transactional=False)
            assert await center.delete(int(own.id)) is True
            with pytest.raises(NotificationNotFoundError):
                await center.delete(int(own.id))
            with pytest.raises(NotificationDeleteForbiddenError):
                await center.delete(int(other.id))
            with pytest.raises(NotificationNotFoundError):
                await center.delete(99999)
            with pytest.raises(NotificationForbiddenError):
                await center.detail(int(other.id))
            with pytest.raises(NotificationNotFoundError):
                await center.detail(99999)
        finally:
            reset_user(tokens)


async def test_missing_user_context(shared_tenant_engine: AsyncEngine) -> None:
    """无用户上下文时读面拒绝。"""
    async with write_session(shared_tenant_engine) as session:
        center = DatabaseNotificationCenter(session_opener=lambda: session_opener(session), transactional=False)
        with pytest.raises(ParamError):
            await center.list(BaseFilterQuery(), BasePageQuery())
        with pytest.raises(ParamError):
            await center.unread_count()


async def test_transactional_and_default_scope(
    shared_tenant_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """生产路径：写操作自开事务；缺省会话开合口按配置构造。"""
    import bms_notification.domains.notification.center as module

    @asynccontextmanager
    async def opener() -> AsyncGenerator[DbSession]:
        async with AsyncSession(shared_tenant_engine) as session:
            yield cast("DbSession", session)

    tokens = use_user(uuid4().int % 10**12)
    try:
        center = DatabaseNotificationCenter(session_opener=opener, transactional=True)
        assert await center.mark_all_read() == 0

        class _Registry:
            pass

        monkeypatch.setattr(module, "EngineRegistry", lambda factory: _Registry())
        monkeypatch.setattr(module, "session_scope", lambda *args, **kwargs: opener())
        default_center = DatabaseNotificationCenter()
        assert await default_center.unread_count() == 0
        assert await default_center.unread_count() == 0
    finally:
        reset_user(tokens)


async def test_invalid_filter(shared_tenant_engine: AsyncEngine) -> None:
    """不支持的筛选字段 / 操作符 / 类型值拒绝。"""
    async with write_session(shared_tenant_engine) as session:
        tokens = use_user(1)
        try:
            center = DatabaseNotificationCenter(session_opener=lambda: session_opener(session), transactional=False)
            for spec in (
                FilterSpec(field="title", value="x"),
                FilterSpec(field="type", operator="like", value="system"),
                FilterSpec(field="type", value="bad"),
                FilterSpec(field="is_read", value="bad"),
            ):
                with pytest.raises(ParamError):
                    await center.list(BaseFilterQuery(filters=ConcurrentStableList((spec,))), BasePageQuery())
            for value in (True, 0, "1", "false"):
                await center.list(
                    BaseFilterQuery(filters=ConcurrentStableList((FilterSpec(field="is_read", value=value),))),
                    BasePageQuery(),
                )
        finally:
            reset_user(tokens)
