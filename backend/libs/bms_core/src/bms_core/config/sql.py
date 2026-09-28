"""系统参数 SQL 取数（`sql` 实现，数据权威侧）：租户库查询 + 缓存域。

- 租户：实现侧从上下文解析（`current_tenant_context().code`）并经 `EngineRegistry` 取租户库；调用方不传租户。
- 缓存：逐 key 先查缓存域（内存 / Redis），未命中批量回源（一次 `IN`）后回填；Redis 不可用由 Region 内部兜底。
- 降级：DB 异常返回空结果 + 日志告警（调用方回落代码默认表，不抛业务错）。
"""

from collections.abc import AsyncGenerator, Mapping, Sequence
from contextlib import asynccontextmanager

from sqlalchemy import select

from bms_core.config.base import BaseConfigSource, ConfigCacheRegion
from bms_core.config.cache import MemoryConfigCacheRegion
from bms_core.config.models import SysConfig
from bms_core.core.logging import get_logger
from bms_core.db.registry import EngineRegistry
from bms_core.db.session import DbSession, session_scope
from bms_core.db.tenant import current_tenant_context

__all__ = ["SqlConfigSource"]

_LOGGER = get_logger("bms")


class SqlConfigSource(BaseConfigSource):
    """真实系统参数取数（插件名 `sql`）：租户库查询 + 缓存域。"""

    plugin_name: str = "sql"

    def __init__(self, *, engines: EngineRegistry, cache: ConfigCacheRegion | None = None) -> None:
        """初始化。

        Args:
            engines: 多租户引擎注册表（按租户库键取引擎）。
            cache: 系统参数缓存域（缺省进程内实现；装配侧注入配置选定的实现）。
        """
        self._engines = engines
        self._cache = cache or MemoryConfigCacheRegion()

    @property
    def cache(self) -> ConfigCacheRegion:
        """系统参数缓存域（供测试与登记核对）。

        Returns:
            ConfigCacheRegion: 缓存域实例。
        """
        return self._cache

    async def get_many(self, keys: Sequence[str]) -> Mapping[str, str]:
        """批量取参数值（缓存优先，未命中回源）。

        Args:
            keys: 参数键序列。

        Returns:
            Mapping[str, str]: 命中键 → 值；无命中返回空映射（降级不抛错）。
        """
        unique = list(dict.fromkeys(key for key in keys if key))
        if not unique:
            return {}
        tenant = current_tenant_context().code
        result: dict[str, str] = {}
        missing: list[str] = []
        for key in unique:
            cached = await self._cache.aget_value(tenant, key)
            if cached is not None:
                result[key] = cached
            else:
                missing.append(key)
        if not missing:
            return result
        loaded = await self._load(missing)
        for key, value in loaded.items():
            await self._cache.aset_value(tenant, key, value)
        result.update(loaded)
        return result

    async def _load(self, keys: Sequence[str]) -> Mapping[str, str]:
        """回源租户库取参数值（一次 `IN` 查询；异常降级空结果）。

        Args:
            keys: 缺失参数键序列。

        Returns:
            Mapping[str, str]: 命中键 → 值；异常返回空映射。
        """
        try:
            async with self._session() as session:
                return await _query_values(session, keys)
        except Exception as exc:
            _LOGGER.warning("系统参数取数降级", scope="get_many", keys=len(keys), error=repr(exc))
            return {}

    @asynccontextmanager
    async def _session(self) -> AsyncGenerator[DbSession]:
        """租户库会话（统一会话入口：按当前租户上下文取引擎）。

        Yields:
            DbSession: 租户库会话。
        """
        async with session_scope(self._engines) as session:
            yield session


async def _query_values(session: DbSession, keys: Sequence[str]) -> Mapping[str, str]:
    """查租户库参数值（一次 `IN`）。

    Args:
        session: 租户库会话。
        keys: 参数键序列。

    Returns:
        Mapping[str, str]: 命中键 → 值（仅未删除行）。
    """
    stmt = select(SysConfig.config_key, SysConfig.value).where(
        SysConfig.config_key.in_(tuple(keys)),
        SysConfig.deleted_at.is_(None),
    )
    rows = (await session.execute(stmt)).all()
    return {str(key): str(value) for key, value in rows}
