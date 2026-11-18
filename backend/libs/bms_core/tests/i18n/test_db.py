"""翻译器数据库实现的回源路径（Kiwi 2533）：语言包取数经统一会话入口按只读取租户库。

为什么单列：`load_messages` 常被错误响应 / 日志路径调用，此时请求可能已持读门；会话未标只读会按
写门取，报「禁止原地升级」并把原始错误盖成语言包降级（13_08 实测）。本文件锁定「回源走只读会话」
这一口径，防止后续把 `read_only=True` 去掉后静默回退。
"""

from __future__ import annotations

from typing import cast

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from bms_core.db.registry import EngineRegistry
from bms_core.i18n.db import DbTranslator
from bms_core.i18n.null import NullLocaleRegistry
from bms_core.models.platform.i18n import SysI18nMessage
from bms_core.testing.gates import write_window
from bms_core.testing.namespace import Namespace

pytestmark = pytest.mark.kiwi_id(2533)


class _TenantEngines:
    """会话入口所需的最小注册表替身：一律返回共享租户库引擎。"""

    def __init__(self, engine: AsyncEngine) -> None:
        """保存引擎。

        Args:
            engine: 共享租户库引擎。
        """
        self._engine = engine

    def is_sync_only(self, db_key: str) -> bool:
        """共享租户库是异步方言。

        Args:
            db_key: 库键（未使用）。

        Returns:
            bool: 恒 False。
        """
        del db_key
        return False

    async def get(self, db_key: str, *, read_only: bool = False) -> AsyncEngine:
        """返回共享租户库引擎。

        Args:
            db_key: 库键（未使用）。
            read_only: 是否只读（未使用）。

        Returns:
            AsyncEngine: 共享租户库引擎。
        """
        del db_key, read_only
        return self._engine


async def test_load_messages_reads_tenant_db(shared_tenant_engine: AsyncEngine, ns: Namespace) -> None:
    """缓存未命中时回源租户库：取数走只读会话并回填缓存。"""
    locale = f"{ns.prefix}zh"[:16]
    key = ns.code("common-ok")
    factory = async_sessionmaker(shared_tenant_engine, expire_on_commit=False)
    async with write_window("tenant_demo"), factory() as session:
        session.add(SysI18nMessage(msg_key=key, locale=locale, value="有值"))
        await session.commit()

    translator = DbTranslator(
        engines=cast("EngineRegistry", _TenantEngines(shared_tenant_engine)),
        registry=NullLocaleRegistry(),
    )

    assert dict(await translator.load_messages(locale)) == {key: "有值"}


async def test_load_messages_reuses_cache(shared_tenant_engine: AsyncEngine, ns: Namespace) -> None:
    """同语言二次取数命中缓存：不再回源（库内新增文案本轮不可见）。"""
    locale = f"{ns.prefix}en"[:16]
    key = ns.code("common-cached")
    factory = async_sessionmaker(shared_tenant_engine, expire_on_commit=False)
    async with write_window("tenant_demo"), factory() as session:
        session.add(SysI18nMessage(msg_key=key, locale=locale, value="首版"))
        await session.commit()

    translator = DbTranslator(
        engines=cast("EngineRegistry", _TenantEngines(shared_tenant_engine)),
        registry=NullLocaleRegistry(),
    )
    assert dict(await translator.load_messages(locale)) == {key: "首版"}

    async with write_window("tenant_demo"), factory() as session:
        session.add(SysI18nMessage(msg_key=ns.code("common-later"), locale=locale, value="后加"))
        await session.commit()

    assert dict(await translator.load_messages(locale)) == {key: "首版"}
