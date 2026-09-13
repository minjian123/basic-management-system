"""db 层工作单元：统一事务公共方法（占位，真实实现归 02-5-1）。

- 事务边界、提交与回滚收敛到工作单元，服务写操作统一经其 `begin()` 进入事务。
- 占位实现 `NullUnitOfWork` 无副作用（内存基线 / 无事务场景）；
  真实实现 `DbUnitOfWork`（基于 AsyncSession）随数据访问底座接入。
"""

from abc import ABC, abstractmethod
from contextlib import AbstractContextManager, nullcontext

from app.core.base import BaseObject


class UnitOfWork(BaseObject, ABC):
    """工作单元：统一事务边界与提交 / 回滚。"""

    @abstractmethod
    def begin(self) -> AbstractContextManager[None]:
        """开启事务边界（上下文管理器）。"""

    @abstractmethod
    def commit(self) -> None:
        """提交当前事务。"""

    @abstractmethod
    def rollback(self) -> None:
        """回滚当前事务。"""

    @property
    def session(self) -> object | None:
        """请求级会话（占位 None；`DbUnitOfWork` 提供 `AsyncSession`）。"""
        return None


class NullUnitOfWork(UnitOfWork):
    """空工作单元（占位 / 内存基线）：无事务、无副作用。"""

    def begin(self) -> AbstractContextManager[None]:
        """无事务上下文。

        Returns:
            AbstractContextManager[None]: 无副作用上下文。
        """
        return nullcontext()

    def commit(self) -> None:
        """空提交（无操作）。"""
        return None

    def rollback(self) -> None:
        """空回滚（无操作）。"""
        return None
