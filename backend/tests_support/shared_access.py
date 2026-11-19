"""测试辅助模块的统一数据库访问入口（13_08 T7）。

背景：`tests_support/` 下的辅助函数原先各自 `create_async_engine(...)` 直连共享库，**不取读写门**。
直连的长读事务会在 SQLite 层挡住走门的写者（表现为「有人持写门很久」），24 路并行时整体卡顿。
本模块把「按引擎所在库取门 → 开会话」收成一条路：新增辅助函数只调这里，不再自己建引擎。

用法::

    async with shared_read(engine) as session:
        ...
    async with shared_write(engine) as session:
        ...
        await session.commit()
    async with shared_window(engine), engine.begin() as connection:
        ...

口径：

- 只对共享平台库 / 租户库取门（按引擎库文件名推断，见 `gate_for_engine`）；临时库与内存库直通；
- 读会话持读门，写会话走 `gate_scope` 的「让读 → 取写 → 放写 → 补读」升级路径；
- 写会话退出**不自动提交**：辅助函数按需 `await session.commit()`（与原 `async_sessionmaker` 口径一致）。
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import AbstractAsyncContextManager, asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from bms_core.db.gate import db_access_gate
from bms_core.testing.transaction import gate_for_engine, gated_session

__all__ = ["shared_engine", "shared_read", "shared_session", "shared_window", "shared_write"]


def shared_engine(url: str, **kwargs: object) -> AsyncEngine:
    """按连接串建共享库引擎（**本模块是唯一允许直连的地方**，已在 `base_modules` 登记）。

    统一在这里建引擎，是为了让辅助模块不再各自 `create_async_engine`——引擎本身不取门，
    取门由 `shared_session` / `shared_window` 完成。

    Args:
        url: 数据库连接串。
        **kwargs: 传给 `create_async_engine` 的关键字参数（缺省 `NullPool`）。

    Returns:
        AsyncEngine: 引擎（调用方负责 `dispose`）。
    """
    kwargs.setdefault("poolclass", NullPool)
    return create_async_engine(url, **kwargs)


@asynccontextmanager
async def shared_session(url: str, *, read_only: bool) -> AsyncGenerator[AsyncSession]:
    """按连接串开「取门会话」：建引擎 → 取门 → 产出会话（退出关会话并释放引擎）。

    写会话退出**不自动提交**：需要落库的辅助函数在会话内 `await session.commit()`。

    Args:
        url: 数据库连接串。
        read_only: 只读 True（持读门）；写 False（升级写门）。

    Yields:
        AsyncSession: 门内会话。
    """
    engine = shared_engine(url)
    try:
        async with gated_session(engine, read_only=read_only) as session:
            yield session
    finally:
        await engine.dispose()


def shared_read(engine: AsyncEngine) -> AbstractAsyncContextManager[AsyncSession]:
    """共享库只读会话（持读门；作用域＝会话生命周期）。

    Args:
        engine: 共享平台库 / 租户库引擎（临时库直通）。

    Returns:
        AbstractAsyncContextManager[AsyncSession]: 门内只读会话。
    """
    return gated_session(engine, read_only=True)


def shared_write(engine: AsyncEngine) -> AbstractAsyncContextManager[AsyncSession]:
    """共享库写会话（升级写门；退出不自动提交）。

    Args:
        engine: 共享平台库 / 租户库引擎（临时库直通）。

    Returns:
        AbstractAsyncContextManager[AsyncSession]: 门内读写会话。
    """
    return gated_session(engine, read_only=False)


@asynccontextmanager
async def shared_window(engine: AsyncEngine) -> AsyncGenerator[None]:
    """共享库写门区间（给必须自己 `engine.begin()` 的 DDL / 批量写法用）。

    Args:
        engine: 共享平台库 / 租户库引擎（临时库直通）。

    Yields:
        None: 写门内区间。
    """
    name = gate_for_engine(engine)
    if name is None:
        yield
        return
    async with db_access_gate(name, read_only=False):
        yield
