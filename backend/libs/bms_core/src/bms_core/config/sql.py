"""系统参数 SQL 取数（`sql` 实现，数据权威侧）：租户库查询 + 缓存域。

- 租户：实现侧从上下文解析并经 `EngineRegistry` 取租户库；缓存键租户位取 `current_tenant_id_str()`
  （雪花 id，无主键落 global）；调用方不传租户。
- 缓存：**每批取一次**版本号 → 逐 key 按版本读载荷（内存 / Redis，版本不一致即视为未命中）→ 未命中批量回源
  （一次 `IN`）后按版本回填；缺失键写短 TTL 负缓存防穿透。`[config].version_check=false` 时跳过版本比对。
- 降级：DB 异常返回空结果 + 日志告警（调用方回落代码默认表，不抛业务错）。
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy import select

from bms_core.config.base import BaseConfigSource, ConfigCacheRegion
from bms_core.config.cache import MemoryConfigCacheRegion
from bms_core.config.models import SysConfig
from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.config import ConfigCacheSettings
from bms_core.core.logging import get_logger
from bms_core.db.registry import EngineRegistry
from bms_core.db.session import DbSession, session_scope
from bms_core.db.tenant import current_tenant_id_str

__all__ = ["SqlConfigSource"]

_LOGGER = get_logger("bms")


class SqlConfigSource(BaseConfigSource):
    """真实系统参数取数（插件名 `sql`）：租户库查询 + 缓存域。"""

    plugin_name: str = "sql"

    def __init__(
        self,
        *,
        engines: EngineRegistry,
        cache: ConfigCacheRegion | None = None,
        options: ConfigCacheSettings | None = None,
    ) -> None:
        """初始化。

        Args:
            engines: 多租户引擎注册表（按租户库键取引擎）。
            cache: 系统参数缓存域（缺省进程内实现；装配侧注入配置选定的实现）。
            options: 缓存参数（`[config]`；缺省取内置默认值）。
        """
        self._engines = engines
        self._cache = cache or MemoryConfigCacheRegion()
        self._options = options if options is not None else ConfigCacheSettings()

    @property
    def cache(self) -> ConfigCacheRegion:
        """系统参数缓存域（供测试与登记核对）。

        Returns:
            ConfigCacheRegion: 缓存域实例。
        """
        return self._cache

    async def get_many(self, keys: ConcurrentStableList[str]) -> ConcurrentStableDict[str, str]:
        """批量取参数值（缓存优先，未命中回源，缺失负缓存）。

        Args:
            keys: 参数键序列（插入序）。

        Returns:
            ConcurrentStableDict[str, str]: 命中键 → 值（插入序）；无命中返回空映射（降级不抛错）。
        """
        unique = list(dict.fromkeys(key for key in keys if key))
        if not unique:
            return ConcurrentStableDict()
        tenant = current_tenant_id_str()
        version = await self._cache.aversion(tenant) if self._options.version_check else 0
        result: ConcurrentStableDict[str, str] = ConcurrentStableDict()
        missing: ConcurrentStableList[str] = ConcurrentStableList()
        for key in unique:
            entry = await self._cache.aget_entry(tenant, key, version)
            if entry is None:
                missing.add(key)
            elif not entry.missing:
                result.set(key, entry.value)
        if not missing:
            return result
        loaded = await self._load(missing)
        for key, value in loaded.items():
            await self._cache.aset_value_at(tenant, key, value, version, self._options.value_ttl_seconds)
        for key in missing:
            if key not in loaded:
                await self._cache.aset_missing(tenant, key, version, self._options.missing_ttl_seconds)
        result.update(loaded.items())
        return result

    async def _load(self, keys: ConcurrentStableList[str]) -> ConcurrentStableDict[str, str]:
        """回源租户库取参数值（一次 `IN` 查询；异常降级空结果）。

        Args:
            keys: 缺失参数键序列（插入序）。

        Returns:
            ConcurrentStableDict[str, str]: 命中键 → 值（插入序）；异常返回空映射。
        """
        try:
            async with self._session() as session:
                return await _query_values(session, keys)
        except Exception as exc:
            _LOGGER.warning("系统参数取数降级", scope="get_many", keys=len(keys), error=repr(exc))
            return ConcurrentStableDict()

    @asynccontextmanager
    async def _session(self) -> AsyncGenerator[DbSession]:
        """租户库会话（统一会话入口：按当前租户上下文取引擎）。

        Yields:
            DbSession: 租户库会话。
        """
        async with session_scope(self._engines) as session:
            yield session


async def _query_values(session: DbSession, keys: ConcurrentStableList[str]) -> ConcurrentStableDict[str, str]:
    """查租户库参数值（一次 `IN`）。

    Args:
        session: 租户库会话。
        keys: 参数键序列（插入序）。

    Returns:
        ConcurrentStableDict[str, str]: 命中键 → 值（插入序；仅未删除行）。
    """
    stmt = select(SysConfig.config_key, SysConfig.value).where(
        SysConfig.config_key.in_(tuple(keys)),
        SysConfig.deleted_at.is_(None),
    )
    rows = (await session.execute(stmt)).all()
    return ConcurrentStableDict({str(key): str(value) for key, value in rows})
