"""db 能力域缺省实现（Null Object）：占位返回、无副作用（02-3 自 bms_core.db.unit_of_work.py 迁入）。"""

from collections.abc import AsyncGenerator
from contextlib import AbstractAsyncContextManager, asynccontextmanager

from bms_core.core.capability import BaseNullObject
from bms_core.db.unit_of_work import UnitOfWork

__all__ = [
    "NullUnitOfWork",
]


@asynccontextmanager
async def _null_transaction() -> AsyncGenerator[None]:
    """无副作用异步事务上下文。"""
    yield


class NullUnitOfWork(UnitOfWork, BaseNullObject):
    """空工作单元（占位 / 内存基线）：无事务、无副作用。"""

    def begin(self) -> AbstractAsyncContextManager[object]:
        """无事务上下文。

        Returns:
            AbstractAsyncContextManager[object]: 无副作用上下文。
        """
        return _null_transaction()

    async def commit(self) -> None:
        """空提交（无操作）。"""
        return None

    async def rollback(self) -> None:
        """空回滚（无操作）。"""
        return None
