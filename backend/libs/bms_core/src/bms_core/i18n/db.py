"""固定文案翻译真实实现（`db` 实现）：语言包取词 + 缺省回退 + 插值。

- 语言包来源：`sys_i18n_message`（该语言的非空文案全量），缓存优先（L1 + Redis + 版本比对）。
- 回退链：请求语言 → 系统默认语言 → `key` 原文（仅两语言都缺时才露 key，排障可见）。
- 语言解析：委托 `BaseLocaleRegistry.resolve_locale`（同步快照，零 IO）；`locale` 显式传入时经
  `ensure_supported` 归一（未登记 / 停用回退默认语言，不抛错）。
- 插值：`{var}` 占位，缺参数原样保留占位符（不抛错）。
"""

import re
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy import select

from bms_core.core.concurrent import ConcurrentStableDict
from bms_core.core.config import I18nSettings
from bms_core.core.logging import get_logger
from bms_core.db.registry import EngineRegistry
from bms_core.db.session import DbSession, session_scope
from bms_core.db.tenant import current_tenant_id_str
from bms_core.i18n.base import BaseTranslator
from bms_core.i18n.cache import I18nCacheRegion, MemoryI18nCacheRegion
from bms_core.i18n.registry import BaseLocaleRegistry
from bms_core.models.platform.i18n import SysI18nMessage

__all__ = ["DbTranslator"]

_LOGGER = get_logger("bms")

_PLACEHOLDER_RE = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")
"""插值占位符（`{var}`）。"""


class DbTranslator(BaseTranslator):
    """真实翻译器（插件名 `db`）：读语言包 + 缓存 + 回退。"""

    plugin_name: str = "db"

    def __init__(
        self,
        *,
        engines: EngineRegistry,
        registry: BaseLocaleRegistry,
        cache: I18nCacheRegion | None = None,
        options: I18nSettings | None = None,
    ) -> None:
        """初始化。

        Args:
            engines: 多租户引擎注册表（按当前租户上下文取租户库）。
            registry: 语言清单能力域（语言解析 / 默认语言）。
            cache: 国际化缓存域（缺省进程内实现）。
            options: 缓存参数（`[i18n]`）。
        """
        self._engines = engines
        self._registry = registry
        self._cache = cache or MemoryI18nCacheRegion()
        self._options = options if options is not None else I18nSettings()

    async def translate(
        self, key: str, *, locale: str | None = None, params: ConcurrentStableDict[str, object] | None = None
    ) -> str:
        """取词（请求语言 → 默认语言 → key 原文）。

        Args:
            key: 文案 key（`模块.页面.字段`）。
            locale: 语言；None 用默认语言。
            params: 插值参数（可选）。

        Returns:
            str: 翻译文案。
        """
        target = await self._registry.ensure_supported(locale) if locale else self._registry.default_locale()
        text = (await self.load_messages(target)).get(key)
        if text is None:
            text = (await self.load_messages(self._registry.default_locale())).get(key)
        if text is None:
            return key
        return _interpolate(text, params)

    async def load_messages(self, locale: str) -> ConcurrentStableDict[str, str]:
        """加载语言包（缓存优先，未命中回源并回填）。

        Args:
            locale: 语言。

        Returns:
            ConcurrentStableDict[str, str]: key → 文案映射（该语言非空文案）。
        """
        tenant = current_tenant_id_str()
        version = 0 if not self._options.version_check else await self._cache.aversion(tenant)
        cached = await self._cache.aget_messages(tenant, locale, version=version)
        if cached is not None:
            return cached
        loaded = await self._load(locale)
        messages: ConcurrentStableDict[str, str] = loaded if loaded is not None else ConcurrentStableDict[str, str]()
        await self._cache.aset_messages(
            tenant, locale, messages, version=version, ttl=self._options.messages_ttl_seconds
        )
        return messages

    def resolve_locale(self, accept_language: str | None = None) -> str:
        """解析语言（委托语言清单能力域）。

        Args:
            accept_language: 请求 `Accept-Language` 头。

        Returns:
            str: 语言。
        """
        return self._registry.resolve_locale(accept_language)

    async def _load(self, locale: str) -> ConcurrentStableDict[str, str] | None:
        """回源租户库取某语言的全部非空文案（异常降级返回 None）。

        Args:
            locale: 语言。

        Returns:
            ConcurrentStableDict[str, str] | None: key → 文案；异常返回 None。
        """
        try:
            async with self._session() as session:
                return await _query_messages(session, locale)
        except Exception as exc:
            _LOGGER.warning("语言包取数降级", scope="load_messages", locale=locale, error=repr(exc))
            return None

    @asynccontextmanager
    async def _session(self) -> AsyncGenerator[DbSession]:
        """租户库会话（统一会话入口）。

        Yields:
            DbSession: 租户库会话。
        """
        async with session_scope(self._engines) as session:
            yield session


async def _query_messages(session: DbSession, locale: str) -> ConcurrentStableDict[str, str]:
    """查租户库某语言的语言包（只取非空文案）。

    Args:
        session: 租户库会话。
        locale: 语言。

    Returns:
        ConcurrentStableDict[str, str]: key → 文案（插入序）。
    """
    stmt = select(SysI18nMessage.msg_key, SysI18nMessage.value).where(
        SysI18nMessage.locale == locale,
        SysI18nMessage.deleted_at.is_(None),
    )
    rows = (await session.execute(stmt)).all()
    result: ConcurrentStableDict[str, str] = ConcurrentStableDict()
    for key, value in rows:
        text = str(value or "").strip()
        if text:
            result.set(str(key), text)
    return result


def _interpolate(text: str, params: ConcurrentStableDict[str, object] | None) -> str:
    """按 `params` 替换 `{var}` 占位（缺参数保留占位符）。

    Args:
        text: 文案模板。
        params: 插值参数（可空）。

    Returns:
        str: 替换后的文案。
    """
    if not params:
        return text

    def _replace(matched: re.Match[str]) -> str:
        name = matched.group(1)
        value = params.get(name)
        return matched.group(0) if value is None else str(value)

    return _PLACEHOLDER_RE.sub(_replace, text)
