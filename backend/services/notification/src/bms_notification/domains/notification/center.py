"""通知中心真实实现（插件名 `db`）：`BaseNotificationCenter` → 真实落库读面。

- 每次调用开租户库会话（库键取当前租户上下文），构造 `NotificationService`；
- 写操作自行提交（可注入 `transactional=False` 供回滚会话测试）；
- 用户维度、错误码与幂等口径见 `services/notification.py`。
"""

from __future__ import annotations

from collections.abc import AsyncGenerator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.config import get_settings
from bms_core.db.engine import EngineFactory
from bms_core.db.registry import EngineRegistry
from bms_core.db.session import DbSession, SessionFactory, session_scope
from bms_core.notification.base import BaseNotificationCenter, Notification
from bms_core.schemas.filters import BaseFilterQuery
from bms_core.schemas.pagination import BasePageQuery, BasePageResponse
from bms_notification.domains.notification.services.notification import NotificationService

__all__ = ["DatabaseNotificationCenter"]

type SessionOpener = Callable[[], AbstractAsyncContextManager[DbSession]]
"""会话开合口（默认 `session_scope`；测试注入共享租户库回滚会话）。"""


class DatabaseNotificationCenter(BaseNotificationCenter):
    """真实通知中心（租户库 `sys_notification`）。"""

    plugin_name: str = "db"

    def __init__(
        self,
        *,
        session_opener: SessionOpener | None = None,
        transactional: bool = True,
        registry: EngineRegistry | None = None,
    ) -> None:
        """初始化。

        Args:
            session_opener: 会话开合口（None 使用按配置懒建的引擎注册表）。
            transactional: 写操作是否自行开启事务（回滚会话测试置 False）。
            registry: 引擎注册表（None 首次使用时按配置懒建）。
        """
        self._session_opener = session_opener
        self._transactional = transactional
        self._registry = registry

    async def list(self, filter: BaseFilterQuery, page: BasePageQuery) -> BasePageResponse[Notification]:
        """列当前用户通知。

        Args:
            filter: 筛选契约。
            page: 分页契约。

        Returns:
            BasePageResponse[Notification]: 分页通知。
        """
        async with self._open() as session:
            return await NotificationService(session).list(filter, page)

    async def detail(self, notification_id: int, *, mark_read: bool = True) -> Notification:
        """取通知详情（查看即已读）。

        Args:
            notification_id: 通知主键。
            mark_read: 命中是否标记已读。

        Returns:
            Notification: 通知对象。
        """
        if not mark_read:
            async with self._open() as session:
                return await NotificationService(session).detail(notification_id, mark_read=False)
        async with self._write() as session:
            return await NotificationService(session).detail(notification_id, mark_read=True)

    async def unread_count(self) -> int:
        """当前未读总数。

        Returns:
            int: 未读数。
        """
        async with self._open() as session:
            return await NotificationService(session).unread_count()

    async def mark_read(self, ids: ConcurrentStableList[int]) -> int:
        """按 id 批量标记已读。

        Args:
            ids: 通知主键清单。

        Returns:
            int: 操作后的未读总数。
        """
        async with self._write() as session:
            return await NotificationService(session).mark_read(ids)

    async def mark_all_read(self) -> int:
        """全部标记已读。

        Returns:
            int: 操作后的未读总数（恒 0）。
        """
        async with self._write() as session:
            return await NotificationService(session).mark_all_read()

    async def delete(self, notification_id: int) -> bool:
        """删除单条通知（软删除，仅本人）。

        Args:
            notification_id: 通知主键。

        Returns:
            bool: 是否删除到既有通知。
        """
        async with self._write() as session:
            return await NotificationService(session).delete(notification_id)

    @asynccontextmanager
    async def _open(self) -> AsyncGenerator[DbSession]:
        """只读会话。

        Yields:
            DbSession: 租户库会话。
        """
        async with self._opener() as session:
            yield session

    @asynccontextmanager
    async def _write(self) -> AsyncGenerator[DbSession]:
        """写会话（按需开启事务）。

        Yields:
            DbSession: 租户库会话。
        """
        async with self._opener() as session:
            if self._transactional:
                async with session.begin():
                    yield session
            else:
                yield session

    def _opener(self) -> AbstractAsyncContextManager[DbSession]:
        """取会话开合口（默认按当前租户上下文）。

        Returns:
            AbstractAsyncContextManager[DbSession]: 会话上下文。
        """
        if self._session_opener is not None:
            return self._session_opener()
        return self._default_scope()

    @asynccontextmanager
    async def _default_scope(self) -> AsyncGenerator[DbSession]:
        """按配置懒建引擎注册表并开会话。

        Yields:
            DbSession: 租户库会话。
        """
        if self._registry is None:
            self._registry = EngineRegistry(EngineFactory(get_settings()))
        async with session_scope(self._registry, factory=SessionFactory()) as session:
            yield session
