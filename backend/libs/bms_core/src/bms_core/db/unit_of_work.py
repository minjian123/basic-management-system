"""db 层工作单元：统一异步事务公共方法。

- 事务边界、提交与回滚收敛到工作单元，服务写操作统一经其 `begin()` 进入事务。
  `DbUnitOfWork` 基于会话公共契约 `DbSession`（异步会话，或达梦等同步方言下的同步门面）。
"""

from abc import ABC, abstractmethod
from contextlib import AbstractAsyncContextManager

from bms_core.core.base import BaseObject
from bms_core.db.gate import LazyGatedSession, ReadOperationGatedSession, requires_gate
from bms_core.db.sync import DbSession


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
    def session(self) -> DbSession | None:
        """请求级会话（占位 None；`DbUnitOfWork` 提供 `DbSession`）。"""
        return None


class DbUnitOfWork(UnitOfWork):
    """数据库工作单元：基于会话公共契约 `DbSession` 的事务边界。"""

    def __init__(self, session: DbSession) -> None:
        """初始化（测试期校验会话已经过读写门）。

        为什么在这里拦：业务写单元是「必须排队」的边界。测试基座把 SQLite 的 `busy_timeout`
        压到 0.1s、写排队只走读写门，绑定裸 `AsyncSession` 的写单元会绕过排队，与
        `write_session` 抢 SQLite 库级写锁（表现为 `database is locked` → 驱动层关闭事务）。
        是否「必须经门」由测试基座注入的判定决定（仅共享库为 True，独占库不受约束）；确需并发事务的
        用例可在会话 `info` 写 `bms.gate.exempt` 显式豁免（须注明理由）。生产不注入，零开销。

        Args:
            session: 请求级会话（异步会话或同步方言下的同步门面）。

        Raises:
            RuntimeError: 测试期（门已注入）绑定了未经门的**真会话**（测试替身无 `execute`，放行）。
        """
        exempt = bool(getattr(session, "info", {}).get("bms.gate.exempt")) if hasattr(session, "info") else False
        if (
            hasattr(session, "execute")
            and requires_gate(session)
            and not exempt
            and not isinstance(session, (LazyGatedSession, ReadOperationGatedSession))
        ):
            raise RuntimeError(
                "DbUnitOfWork 绑定了未经读写门的会话（测试期）："
                f"{type(session).__name__}。业务写单元必须经 session_scope() / get_uow() 取会话，"
                "或显式用 LazyGatedSession 包装；裸 async_sessionmaker 会绕过写门排队。"
            )
        self._session = session

    @property
    def session(self) -> DbSession:
        """请求级会话。"""
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
