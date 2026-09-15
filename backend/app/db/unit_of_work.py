"""db 层工作单元：统一异步事务公共方法。

- 事务边界、提交与回滚收敛到工作单元，服务写操作统一经其 `begin()` 进入事务。
  `DbUnitOfWork` 基于 `AsyncSession`（真实数据库场景）。
"""

from abc import ABC, abstractmethod
from contextlib import AbstractAsyncContextManager

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base import BaseObject


class UnitOfWork(BaseObject, ABC):
    """工作单元：统一异步事务边界与提交 / 回滚。"""

    @abstractmethod
    def begin(self) -> AbstractAsyncContextManager[object]:
        """开启事务边界（异步上下文管理器）。"""

    @abstractmethod
    async def commit(self) -> None:
        """提交当前事务。"""

    @abstractmethod
    async def rollback(self) -> None:
        """回滚当前事务。"""

    @property
    def session(self) -> AsyncSession | None:
        """请求级会话（占位 None；`DbUnitOfWork` 提供 `AsyncSession`）。"""
        return None


class DbUnitOfWork(UnitOfWork):
    """数据库工作单元：基于 `AsyncSession` 的事务边界。"""

    def __init__(self, session: AsyncSession) -> None:
        """初始化。

        Args:
            session: 请求级异步会话。
        """
        self._session = session

    @property
    def session(self) -> AsyncSession:
        """请求级异步会话。"""
        return self._session

    def begin(self) -> AbstractAsyncContextManager[object]:
        """开启会话事务。

        Returns:
            AbstractAsyncContextManager[object]: 会话事务上下文。
        """
        return self._session.begin()

    async def commit(self) -> None:
        """提交当前事务。"""
        await self._session.commit()

    async def rollback(self) -> None:
        """回滚当前事务。"""
        await self._session.rollback()
