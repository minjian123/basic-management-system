"""系统参数写 / 失效服务：先写库后删缓存 + 递增租户版本键（本轮无管理 API）。

- 仅服务方法（`set` / `drop`），供「策略变更即时生效」验证与后续阶段八管理面复用。
- 失效协议：写库 → 删缓存 key（含 L1）→ 递增租户版本键（多实例 L1 惰性失效）。
- 租户：按当前上下文取租户库（`session_scope`）。
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy import select
from sqlalchemy.orm.exc import StaleDataError

from bms_core.config.base import ConfigCacheRegion
from bms_core.config.cache import MemoryConfigCacheRegion
from bms_core.config.models import SysConfig
from bms_core.core.base import BaseObject
from bms_core.core.exceptions import ConcurrentConflictError
from bms_core.db.registry import EngineRegistry
from bms_core.db.session import DbSession, session_scope
from bms_core.db.tenant import current_tenant_context

__all__ = ["ConfigService"]


class ConfigService(BaseObject):
    """系统参数写 / 失效服务（无管理 API；先写库后删缓存 + 递增版本）。"""

    def __init__(self, *, engines: EngineRegistry, cache: ConfigCacheRegion | None = None) -> None:
        """初始化。

        Args:
            engines: 多租户引擎注册表。
            cache: 系统参数缓存域（缺省进程内实现）。
        """
        self._engines = engines
        self._cache = cache or MemoryConfigCacheRegion()

    async def set(self, *, config_key: str, value: str, remark: str | None = None) -> None:
        """写租户覆盖参数（存在则更新，否则插入）并失效缓存。

        Args:
            config_key: 参数键。
            value: 参数值。
            remark: 备注（None 不改动既有备注）。

        Raises:
            ConcurrentConflictError: 乐观锁冲突。
        """
        async with self._session() as session:
            row = await _find(session, config_key)
            if row is None:
                session.add(SysConfig(config_key=config_key, value=value, remark=remark))
            else:
                row.value = value
                if remark is not None:
                    row.remark = remark
            await self._commit(session)
        await self._invalidate(config_key)

    async def drop(self, *, config_key: str) -> None:
        """软删除租户覆盖参数（恢复平台默认）并失效缓存。

        Args:
            config_key: 参数键。

        Raises:
            ConcurrentConflictError: 乐观锁冲突。
        """
        async with self._session() as session:
            row = await _find(session, config_key)
            if row is not None:
                row.soft_delete()
                await self._commit(session)
        await self._invalidate(config_key)

    async def _invalidate(self, config_key: str) -> None:
        """失效参数缓存：删 key + 递增租户版本键（跨实例失效）。

        Args:
            config_key: 参数键。
        """
        tenant = current_tenant_context().tenant_code
        await self._cache.adrop_value(tenant, config_key)
        await self._cache.aincrease_version(tenant)

    async def _commit(self, session: DbSession) -> None:
        """提交（乐观锁冲突转统一错误）。

        Args:
            session: 租户库会话。

        Raises:
            ConcurrentConflictError: 乐观锁冲突。
        """
        try:
            await session.commit()
        except StaleDataError as exc:
            raise ConcurrentConflictError("系统参数已被修改，请刷新后重试") from exc

    @asynccontextmanager
    async def _session(self) -> AsyncGenerator[DbSession]:
        """租户库会话（统一会话入口）。

        Yields:
            DbSession: 租户库会话。
        """
        async with session_scope(self._engines) as session:
            yield session


async def _find(session: DbSession, config_key: str) -> SysConfig | None:
    """按参数键取未删除行。

    Args:
        session: 租户库会话。
        config_key: 参数键。

    Returns:
        SysConfig | None: 参数行；不存在 / 已删返回 None。
    """
    stmt = select(SysConfig).where(SysConfig.config_key == config_key, SysConfig.deleted_at.is_(None))
    return (await session.execute(stmt)).scalar_one_or_none()
