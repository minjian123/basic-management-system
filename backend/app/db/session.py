"""异步会话工厂与请求级依赖：`SessionFactory` + 读写选引擎的请求会话。

- `get_db`：按请求上下文只读标记选引擎（只读走副本、写走主库）。
- `get_read_db` / `get_write_db`：显式强制只读 / 主库（只读数据集与写路径用）。
- `get_uow`：工作单元绑定**主库会话**（写与事务强制走主库，写后同会话内读主库）。
- 租户路由：请求态租户上下文存在时取该租户库键（`tenant_{code}`）引擎；否则回落平台库
  （豁免路径 / 平台侧接口 / 未经租户中间件的调用）。
- **方言分流**：目标库为同步方言（达梦，无异步驱动）时，会话改由 `app/db/sync.py` 的
  同步门面 `SyncSession` 承载（阻塞调用经 `asyncio.to_thread`），对外仍以 `DbSession`
  公共契约暴露，`session_scope` / HTTP 依赖的调用方无须感知差异。
- 禁止异步会话跨请求共享；每请求独立会话，退出即释放。
- 主库故障只读降级：写路径在降级态先探测，失败抛 `DatabaseUnavailableError`。
- 工厂链：`SessionFactory → BaseDbFactory → BaseFactory → BasePluggable`（02-54）；实现可替换
  （插件键 `session_factory`，配置经 `[session_factory].provider` 选择，缺省 `default`）。
"""

from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated, cast

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.context import is_read_only
from app.core.exceptions import DatabaseUnavailableError
from app.core.factory import BaseDbFactory
from app.db.health import PrimaryHealth
from app.db.registry import PLATFORM_DB_KEY, EngineRegistry
from app.db.sync import DbSession, sync_session_scope
from app.db.tenant import current_tenant_context
from app.db.unit_of_work import DbUnitOfWork

__all__ = [
    "DbSession",
    "SessionFactory",
    "get_db",
    "get_read_db",
    "get_uow",
    "get_write_db",
    "session_scope",
]


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


async def _guard_degraded(request: Request, db_key: str, *, read_only: bool) -> None:
    """写路径降级守卫：主库降级且探测失败即拒绝写（异步与同步路径共用）。

    Args:
        request: 当前请求。
        db_key: 数据源键。
        read_only: 是否只读（只读不校验）。

    Raises:
        DatabaseUnavailableError: 主库降级且探测失败（写被拒）。
    """
    if read_only:
        return
    health = cast("PrimaryHealth | None", getattr(request.app.state, "primary_health", None))
    if health is not None and health.is_degraded(db_key) and not await health.probe(db_key):
        raise DatabaseUnavailableError("主数据库不可用，系统处于只读降级模式，写操作被拒绝")


async def _resolve_engine(request: Request, registry: EngineRegistry, *, read_only: bool) -> AsyncEngine:
    """按租户与读写角色取异步引擎（写路径在降级态先探测主库）。

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
    await _guard_degraded(request, db_key, read_only=read_only)
    return await registry.get(db_key, read_only=read_only)


async def _open_session(request: Request, *, read_only: bool) -> AsyncIterator[DbSession]:
    """打开请求级会话（按方言分流：同步方言走同步门面；选引擎 → 建会话 → 退出释放）。

    Args:
        request: 当前请求。
        read_only: 是否只读。

    Yields:
        DbSession: 请求级会话（异步会话或同步门面）。
    """
    registry = cast(EngineRegistry, request.app.state.engine_registry)
    db_key = _resolve_db_key(request)
    if registry.is_sync_only(db_key):
        await _guard_degraded(request, db_key, read_only=read_only)
        engine = await registry.get_sync(db_key, read_only=read_only)
        async with sync_session_scope(engine) as sync_session:
            yield sync_session
        return
    engine = await _resolve_engine(request, registry, read_only=read_only)
    factory = cast("SessionFactory | None", getattr(request.app.state, "session_factory", None)) or SessionFactory()
    async with factory.create(engine)() as session:
        yield session


async def get_db(request: Request) -> AsyncIterator[DbSession]:
    """请求级会话依赖（按只读上下文标记选主 / 副本；每请求独立，退出释放）。

    Args:
        request: 当前请求。

    Yields:
        DbSession: 请求级会话（异步会话或同步方言下的同步门面）。
    """
    async for session in _open_session(request, read_only=is_read_only()):
        yield session


async def get_read_db(request: Request) -> AsyncIterator[DbSession]:
    """强制只读会话依赖（读从库；报表数据集 / 只读接口显式覆盖）。

    Args:
        request: 当前请求。

    Yields:
        DbSession: 只读会话。
    """
    async for session in _open_session(request, read_only=True):
        yield session


async def get_write_db(request: Request) -> AsyncIterator[DbSession]:
    """强制主库会话依赖（写路径 / 事务）。

    Args:
        request: 当前请求。

    Yields:
        DbSession: 主库会话。
    """
    async for session in _open_session(request, read_only=False):
        yield session


async def get_uow(session: Annotated[DbSession, Depends(get_write_db)]) -> DbUnitOfWork:
    """请求级工作单元依赖（绑定主库会话）。

    Args:
        session: 主库会话。

    Returns:
        DbUnitOfWork: 数据库工作单元。
    """
    return DbUnitOfWork(session)


@asynccontextmanager
async def session_scope(
    registry: EngineRegistry,
    *,
    db_key: str | None = None,
    read_only: bool = False,
    factory: SessionFactory | None = None,
) -> AsyncGenerator[DbSession]:
    """统一会话入口：按库键 / 当前租户上下文取引擎并开会话（按方言分流）。

    - 库键：显式 `db_key` 优先；为空取当前租户上下文库键（无上下文回落演示租户）；
    - 读写角色：缺省主库（写后读同库，避免副本旧值）；只读从库经 `read_only=True`；
    - 方言：目标库为同步方言（达梦）时经 `registry.get_sync` + 同步门面承载（`factory` 不参与）；
    - 事务：只负责建会话与释放，`commit` / `rollback` 与事务边界归调用方（服务层工作单元）。

    Args:
        registry: 引擎注册表。
        db_key: 数据源键；None 取当前租户库键。
        read_only: 是否只读。
        factory: 会话工厂（仅异步方言路径）；None 新建缺省工厂。

    Yields:
        DbSession: 会话（异步会话或同步方言下的同步门面）。
    """
    resolved = db_key if db_key is not None else current_tenant_context().db_key
    if registry.is_sync_only(resolved):
        sync_engine = await registry.get_sync(resolved, read_only=read_only)
        async with sync_session_scope(sync_engine) as sync_session:
            yield sync_session
        return
    engine = await registry.get(resolved, read_only=read_only)
    session_factory = factory if factory is not None else SessionFactory()
    async with session_factory.create(engine)() as session:
        yield session
