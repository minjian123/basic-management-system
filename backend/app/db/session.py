"""异步会话工厂与请求级依赖：`SessionFactory` + 读写选引擎的请求会话。

- `get_db`：按请求上下文只读标记选引擎（只读走副本、写走主库）。
- `get_read_db` / `get_write_db`：显式强制只读 / 主库（只读数据集与写路径用）。
- `get_uow`：工作单元绑定**主库会话**（写与事务强制走主库，写后同会话内读主库）。
- 租户路由：请求态租户上下文存在时取该租户库键（`tenant_{code}`）引擎；否则回落平台库
  （豁免路径 / 平台侧接口 / 未经租户中间件的调用）。
- 禁止异步会话跨请求共享；每请求独立会话，退出即释放。
- 主库故障只读降级：写路径在降级态先探测，失败抛 `DatabaseUnavailableError`。
- 工厂链：`SessionFactory → BaseDbFactory → BaseFactory → BasePluggable`（02-54）；实现可替换
  （插件键 `session_factory`，配置经 `[session_factory].provider` 选择，缺省 `default`）。
"""

from collections.abc import AsyncIterator
from typing import Annotated, cast

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.context import is_read_only
from app.core.exceptions import DatabaseUnavailableError
from app.core.factory import BaseDbFactory
from app.db.health import PrimaryHealth
from app.db.registry import PLATFORM_DB_KEY, EngineRegistry
from app.db.unit_of_work import DbUnitOfWork


class SessionFactory(BaseDbFactory[AsyncEngine, async_sessionmaker[AsyncSession]]):
    """异步会话工厂：由引擎产出 `async_sessionmaker`。"""

    key: str = "session_factory"

    def create(self, options: AsyncEngine) -> async_sessionmaker[AsyncSession]:
        """构建异步会话工厂。

        Args:
            options: 异步引擎。

        Returns:
            async_sessionmaker[AsyncSession]: 会话工厂。
        """
        return async_sessionmaker(options, expire_on_commit=False)


def _resolve_db_key(request: Request) -> str:
    """请求级数据源键：有租户上下文取租户库键，否则回落平台库。

    Args:
        request: 当前请求。

    Returns:
        str: 数据源键。
    """
    tenant = request.scope.get("state", {}).get("tenant")
    db_key = getattr(tenant, "db_key", None)
    return str(db_key) if db_key else PLATFORM_DB_KEY


async def _resolve_engine(request: Request, registry: EngineRegistry, *, read_only: bool) -> AsyncEngine:
    """按租户与读写角色取引擎（写路径在降级态先探测主库）。

    Args:
        request: 当前请求。
        registry: 引擎注册表。
        read_only: 是否只读。

    Returns:
        AsyncEngine: 异步引擎。

    Raises:
        DatabaseUnavailableError: 主库降级且探测失败（写被拒）。
    """
    db_key = _resolve_db_key(request)
    if read_only:
        return await registry.get(db_key, read_only=True)
    health = cast("PrimaryHealth | None", getattr(request.app.state, "primary_health", None))
    if health is not None and health.is_degraded(db_key) and not await health.probe(db_key):
        raise DatabaseUnavailableError("主数据库不可用，系统处于只读降级模式，写操作被拒绝")
    return await registry.get(db_key, read_only=False)


async def _open_session(request: Request, *, read_only: bool) -> AsyncIterator[AsyncSession]:
    """打开请求级会话（选引擎 → 建会话 → 退出释放）。

    Args:
        request: 当前请求。
        read_only: 是否只读。

    Yields:
        AsyncSession: 请求级异步会话。
    """
    registry = cast(EngineRegistry, request.app.state.engine_registry)
    engine = await _resolve_engine(request, registry, read_only=read_only)
    factory = cast("SessionFactory | None", getattr(request.app.state, "session_factory", None)) or SessionFactory()
    async with factory.create(engine)() as session:
        yield session


async def get_db(request: Request) -> AsyncIterator[AsyncSession]:
    """请求级会话依赖（按只读上下文标记选主 / 副本；每请求独立，退出释放）。

    Args:
        request: 当前请求。

    Yields:
        AsyncSession: 请求级异步会话。
    """
    async for session in _open_session(request, read_only=is_read_only()):
        yield session


async def get_read_db(request: Request) -> AsyncIterator[AsyncSession]:
    """强制只读会话依赖（读从库；报表数据集 / 只读接口显式覆盖）。

    Args:
        request: 当前请求。

    Yields:
        AsyncSession: 只读异步会话。
    """
    async for session in _open_session(request, read_only=True):
        yield session


async def get_write_db(request: Request) -> AsyncIterator[AsyncSession]:
    """强制主库会话依赖（写路径 / 事务）。

    Args:
        request: 当前请求。

    Yields:
        AsyncSession: 主库异步会话。
    """
    async for session in _open_session(request, read_only=False):
        yield session


async def get_uow(session: Annotated[AsyncSession, Depends(get_write_db)]) -> DbUnitOfWork:
    """请求级工作单元依赖（绑定主库会话）。

    Args:
        session: 主库异步会话。

    Returns:
        DbUnitOfWork: 数据库工作单元。
    """
    return DbUnitOfWork(session)
