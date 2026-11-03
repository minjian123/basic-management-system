"""语言清单 SQL 实现（`sql` 实现，数据权威侧）：缓存优先 + 回源租户库。

- 租户：实现侧从上下文解析并经 `EngineRegistry` 取租户库；缓存键租户位取 `current_tenant_id_str()`。
- 读路径：版本号 → 缓存载荷（版本不符即未命中）→ 回源 `sys_i18n_locale`（一次全表，语言数极小）→ 回填
  缓存并替换进程内快照；`[i18n].version_check=false` 时版本恒 0（纯 TTL）。
- 降级：DB 异常回退**种子清单**（`SEED_LOCALES`）并告警——语言解析不得因库抖动而不可用。
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy import select

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.config import I18nSettings
from bms_core.core.logging import get_logger
from bms_core.db.registry import EngineRegistry
from bms_core.db.session import DbSession, session_scope
from bms_core.db.tenant import current_tenant_id_str
from bms_core.i18n.cache import I18nCacheRegion, MemoryI18nCacheRegion
from bms_core.i18n.locale import LocaleInfo
from bms_core.i18n.registry import BaseLocaleRegistry, seed_locale_infos
from bms_core.models.platform.i18n import SysI18nLocale

__all__ = ["SqlLocaleRegistry"]

_LOGGER = get_logger("bms")


class SqlLocaleRegistry(BaseLocaleRegistry):
    """真实语言清单（插件名 `sql`）：缓存 + 租户库 + 进程内快照。"""

    plugin_name: str = "sql"

    def __init__(
        self,
        *,
        engines: EngineRegistry,
        cache: I18nCacheRegion | None = None,
        options: I18nSettings | None = None,
    ) -> None:
        """初始化。

        Args:
            engines: 多租户引擎注册表（按当前租户上下文取租户库）。
            cache: 国际化缓存域（缺省进程内实现；装配侧注入配置选定的实现）。
            options: 缓存参数（`[i18n]`；缺省取内置默认值）。
        """
        super().__init__()
        self._engines = engines
        self._cache = cache or MemoryI18nCacheRegion()
        self._options = options if options is not None else I18nSettings()

    @property
    def cache(self) -> I18nCacheRegion:
        """国际化缓存域（供测试与登记核对）。

        Returns:
            I18nCacheRegion: 缓存域实例。
        """
        return self._cache

    async def list_locales(self, *, enabled_only: bool = False) -> ConcurrentStableList[LocaleInfo]:
        """查询语言清单（缓存优先，未命中回源）。

        Args:
            enabled_only: 是否只返回启用语言。

        Returns:
            ConcurrentStableList[LocaleInfo]: 清单条目（按 `sort` 升序）。
        """
        tenant = current_tenant_id_str()
        version = await self._version(tenant)
        cached = await self._cache.aget_locales(tenant, version=version)
        locales = cached
        if locales is None:
            loaded = await self._load()
            locales = loaded if loaded is not None else seed_locale_infos()
            await self._cache.aset_locales(tenant, locales, version=version, ttl=self._options.locales_ttl_seconds)
        self._replace_snapshot(locales)
        if enabled_only:
            return ConcurrentStableList(item for item in locales if item.enabled)
        return ConcurrentStableList(locales)

    async def refresh(self) -> None:
        """强制回源并把快照替换为库内清单（失败回退种子清单）。"""
        tenant = current_tenant_id_str()
        version = await self._version(tenant)
        loaded = await self._load()
        locales = loaded if loaded is not None else seed_locale_infos()
        await self._cache.aset_locales(tenant, locales, version=version, ttl=self._options.locales_ttl_seconds)
        self._replace_snapshot(locales)

    async def _version(self, tenant: str | None) -> int:
        """取当前版本号（`version_check=false` 时恒 0，退回纯 TTL）。

        Args:
            tenant: 租户标识。

        Returns:
            int: 版本号。
        """
        if not self._options.version_check:
            return 0
        return await self._cache.aversion(tenant)

    async def _load(self) -> ConcurrentStableList[LocaleInfo] | None:
        """回源租户库取完整清单（异常降级返回 None）。

        Returns:
            ConcurrentStableList[LocaleInfo] | None: 清单条目；库空 / 异常返回 None。
        """
        try:
            async with self._session() as session:
                return await _query_locales(session)
        except Exception as exc:
            _LOGGER.warning("语言清单取数降级", scope="list_locales", error=repr(exc))
            return None

    @asynccontextmanager
    async def _session(self) -> AsyncGenerator[DbSession]:
        """租户库会话（统一会话入口：按当前租户上下文取引擎）。

        Yields:
            DbSession: 租户库会话。
        """
        async with session_scope(self._engines) as session:
            yield session


async def _query_locales(session: DbSession) -> ConcurrentStableList[LocaleInfo] | None:
    """查租户库语言清单（全表，按 `sort` 升序）。

    Args:
        session: 租户库会话。

    Returns:
        ConcurrentStableList[LocaleInfo] | None: 清单条目；无行返回 None。
    """
    stmt = (
        select(SysI18nLocale).where(SysI18nLocale.deleted_at.is_(None)).order_by(SysI18nLocale.sort, SysI18nLocale.code)
    )
    rows = (await session.execute(stmt)).scalars().all()
    if not rows:
        return None
    return ConcurrentStableList(
        LocaleInfo(
            code=row.code,
            name=row.name,
            rtl=row.rtl,
            is_default=row.is_default,
            status=row.status,
            sort=row.sort,
        )
        for row in rows
    )
