"""国际化基座边界用例（Kiwi 2404）：抽象契约 / 占位缓存 / SQL 清单 / 失效异常 / 规则 / 种子入口。"""

import asyncio
from pathlib import Path
from typing import cast

import pytest
from sqlalchemy import Table
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.config import I18nSettings
from bms_core.db.registry import EngineRegistry
from bms_core.i18n import seed as seed_module
from bms_core.i18n.cache import I18nCacheRegion, MemoryI18nCacheRegion
from bms_core.i18n.cache_null import NullI18nCacheRegion
from bms_core.i18n.db import (
    DbTranslator,
    _query_messages,  # pyright: ignore[reportPrivateUsage]
)
from bms_core.i18n.invalidate import I18nInvalidator
from bms_core.i18n.locale import LocaleInfo
from bms_core.i18n.registry_null import NullLocaleRegistry
from bms_core.i18n.registry_sql import SqlLocaleRegistry, _query_locales  # pyright: ignore[reportPrivateUsage]
from bms_core.i18n.rules import (
    is_locale_code_valid,
    is_message_key_valid,
    is_message_value_valid,
    message_module,
    normalize_locale,
)
from bms_core.i18n.seed import build_parser, main, seed_i18n_entry
from bms_core.models.base import Base
from bms_core.models.platform.i18n import SysI18nLocale, SysI18nMessage

pytestmark = [
    pytest.mark.kiwi_id(2404),
    pytest.mark.own_db("语言清单回源与种子入口的建表即被测：临时库验证查询排序与自建引擎写入"),
]

_TENANT = "1001"


class _BareRegion(I18nCacheRegion):
    """仅实现缓存域必需抽象的最小实现（用于验证扩展方法契约）。"""

    def get(self, key: str) -> object | None:
        """占位读。

        Args:
            key: 缓存 key。

        Returns:
            object | None: 恒 None。
        """
        del key
        return None

    def set(self, key: str, value: object, ttl: int | None = None) -> None:
        """占位写。

        Args:
            key: 缓存 key。
            value: 缓存值。
            ttl: 有效期。
        """
        del key, value, ttl

    def delete(self, key: str) -> bool:
        """占位删。

        Args:
            key: 缓存 key。

        Returns:
            bool: 恒 False。
        """
        del key
        return False

    def get_global_version(self) -> int:
        """占位版本。

        Returns:
            int: 恒 0。
        """
        return 0


async def test_base_region_extension_methods_not_implemented() -> None:
    """扩展方法在基类为契约占位（未覆写即抛 NotImplementedError）。"""
    region = _BareRegion()
    assert region.messages_cache_key(_TENANT, "zh-CN").endswith(":i18n:messages:zh-CN")
    assert region.locales_cache_key(_TENANT).endswith(":i18n:locales")
    assert region.version_cache_key(_TENANT).endswith(":i18n:version")
    for call in (
        region.aget_messages(_TENANT, "zh-CN", version=0),
        region.aset_messages(_TENANT, "zh-CN", ConcurrentStableDict[str, str](), version=0, ttl=1),
        region.adrop_messages(_TENANT, "zh-CN"),
        region.aget_locales(_TENANT, version=0),
        region.aset_locales(_TENANT, ConcurrentStableList[LocaleInfo](), version=0, ttl=1),
        region.adrop_locales(_TENANT),
        region.aversion(_TENANT),
        region.aincrease_version(_TENANT),
    ):
        with pytest.raises(NotImplementedError):
            await call


async def test_null_cache_region_is_noop() -> None:
    """占位缓存：读写全空操作、版本恒 0 / 递增 1。"""
    region = NullI18nCacheRegion()
    assert region.get("k") is None
    region.set("k", {"a": 1})
    assert region.delete("k") is False
    assert region.get_global_version() == 0
    assert await region.aget_messages(_TENANT, "zh-CN", version=0) is None
    await region.aset_messages(_TENANT, "zh-CN", ConcurrentStableDict({"k": "v"}), version=0, ttl=1)
    await region.adrop_messages(_TENANT, "zh-CN")
    assert await region.aget_locales(_TENANT, version=0) is None
    await region.aset_locales(_TENANT, ConcurrentStableList((LocaleInfo(code="zh-CN"),)), version=0, ttl=1)
    await region.adrop_locales(_TENANT)
    assert await region.aversion(_TENANT) == 0
    assert await region.aincrease_version(_TENANT) == 1


def _sql_registry(monkeypatch: pytest.MonkeyPatch, loader: object, *, version_check: bool = True) -> SqlLocaleRegistry:
    """构造 SQL 清单实现并打桩回源。

    Args:
        monkeypatch: pytest 打桩器。
        loader: 回源可调用对象（async）。
        version_check: 是否比对版本。

    Returns:
        SqlLocaleRegistry: 清单实例。
    """
    registry = SqlLocaleRegistry(
        engines=cast("EngineRegistry", object()),
        cache=MemoryI18nCacheRegion(),
        options=I18nSettings(version_check=version_check),
    )
    monkeypatch.setattr(registry, "_load", loader)
    return registry


async def test_sql_registry_cache_hit_and_seed_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    """回源为空 → 种子清单；再次读取命中缓存不回源；`enabled_only` 过滤。"""
    calls = ConcurrentStableList[str]()

    async def empty_loader() -> ConcurrentStableList[LocaleInfo] | None:
        calls.add("load")
        return None

    registry = _sql_registry(monkeypatch, empty_loader)
    assert [item.code for item in await registry.list_locales()] == ["zh-CN", "en-US"]
    assert [item.code for item in await registry.list_locales(enabled_only=True)] == ["zh-CN", "en-US"]
    assert len(calls) == 1
    assert registry.cache is not None

    async def custom_loader() -> ConcurrentStableList[LocaleInfo] | None:
        calls.add("load")
        return ConcurrentStableList((LocaleInfo(code="ar-SA", rtl=True, sort=1), LocaleInfo(code="zh-CN", sort=2)))

    monkeypatch.setattr(registry, "_load", custom_loader)
    await registry.refresh()
    assert registry.default_locale() == "ar-SA"
    assert registry.is_rtl("ar-SA") is True


async def test_sql_registry_load_exception_degrades(monkeypatch: pytest.MonkeyPatch) -> None:
    """回源异常 → 降级返回 None（上层回退种子清单）。"""
    registry = SqlLocaleRegistry(
        engines=cast("EngineRegistry", object()),
        cache=MemoryI18nCacheRegion(),
        options=I18nSettings(version_check=False),
    )
    assert await registry._load() is None  # pyright: ignore[reportPrivateUsage]
    assert await registry.list_locales() != ConcurrentStableList()


async def test_sql_registry_query_locales_from_db(tmp_path: Path) -> None:
    """真库查询：按 `sort` 升序返回，空表返回 None。"""
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'q.db'}")
    tables = [cast("Table", SysI18nLocale.__table__), cast("Table", SysI18nMessage.__table__)]
    async with engine.begin() as conn:
        await conn.run_sync(lambda sync_conn: Base.metadata.create_all(sync_conn, tables=tables))  # type: ignore[arg-type]
    factory: async_sessionmaker[AsyncSession] = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        assert await _query_locales(session) is None
        session.add(SysI18nLocale(code="en-US", name="English", sort=20))
        session.add(SysI18nLocale(code="zh-CN", name="简体中文", sort=10, is_default=True))
        await session.commit()
        rows = await _query_locales(session)
        assert rows is not None
        assert [row.code for row in rows] == ["zh-CN", "en-US"]
        assert rows[0].is_default is True
    await engine.dispose()


async def test_invalidator_degrades_on_failure() -> None:
    """失效异常 → 返回 0（不反噬业务写）。"""

    class _BrokenCache(MemoryI18nCacheRegion):
        """构造删除即失败的缓存域。"""

        async def adrop_messages(self, tenant: str | None, locale: str) -> None:
            """抛错模拟 Redis 抖动。

            Args:
                tenant: 租户标识。
                locale: 语言。

            Raises:
                RuntimeError: 恒抛。
            """
            del tenant, locale
            raise RuntimeError("redis down")

        async def adrop_locales(self, tenant: str | None) -> None:
            """抛错模拟 Redis 抖动。

            Args:
                tenant: 租户标识。

            Raises:
                RuntimeError: 恒抛。
            """
            del tenant
            raise RuntimeError("redis down")

    invalidator = I18nInvalidator(_BrokenCache(), NullLocaleRegistry())
    assert await invalidator.invalidate_messages(ConcurrentStableList(("zh-CN",))) == 0
    assert await invalidator.invalidate_all() == 0


def test_rules_boundaries() -> None:
    """规则边界：locale 归一 / 合法性 / key 与值 / 模块前缀。"""
    assert normalize_locale("zh-hant-tw") == "zh-Hant-TW"
    assert normalize_locale("en-us") == "en-US"
    assert normalize_locale("x-private-1") == "x-private-1"
    assert normalize_locale("") == ""
    assert is_locale_code_valid("zh-CN") is True
    assert is_locale_code_valid("") is False
    assert is_locale_code_valid("z" * 17) is False
    assert is_message_key_valid("common.confirm") is True
    assert is_message_key_valid("common") is False
    assert is_message_key_valid("Common.confirm") is False
    assert is_message_value_valid("") is True
    assert is_message_value_valid("x" * 4000) is True
    assert is_message_value_valid("x" * 4001) is False
    assert message_module("common.confirm") == "common"
    assert message_module("nodot") == "nodot"


def test_seed_cli_dry_run(capsys: pytest.CaptureFixture[str]) -> None:
    """种子命令行：`--dry-run` 只打印目标库。"""
    assert build_parser().parse_args(["--dry-run"]).dry_run is True
    assert main(ConcurrentStableList(["--dry-run"])) == 0
    assert "seed_i18n" in capsys.readouterr().out


async def _create_i18n_tables(db_url: str) -> None:
    """建 i18n 两表（种子命令行用例的准备步骤）。

    Args:
        db_url: 目标库连接串。
    """
    engine = create_async_engine(db_url)
    tables = [cast("Table", SysI18nLocale.__table__), cast("Table", SysI18nMessage.__table__)]
    async with engine.begin() as conn:
        await conn.run_sync(lambda sync_conn: Base.metadata.create_all(sync_conn, tables=tables))
    await engine.dispose()


def test_seed_cli_runs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """种子命令行（非 dry-run）：自建引擎写入并打印新增行数。"""
    db_url = f"sqlite+aiosqlite:///{tmp_path / 'cli.db'}"
    asyncio.run(_create_i18n_tables(db_url))
    monkeypatch.setattr("bms_core.i18n.seed._database_url", lambda: db_url)
    assert main(ConcurrentStableList()) == 0


async def test_seed_entry_and_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """种子入口（编排路径）与自建引擎单步入口都能写入。"""
    db_url = f"sqlite+aiosqlite:///{tmp_path / 'entry.db'}"
    engine = create_async_engine(db_url)
    tables = [cast("Table", SysI18nLocale.__table__), cast("Table", SysI18nMessage.__table__)]
    async with engine.begin() as conn:
        await conn.run_sync(lambda sync_conn: Base.metadata.create_all(sync_conn, tables=tables))  # type: ignore[arg-type]
    await engine.dispose()

    monkeypatch.setattr("bms_core.i18n.seed._database_url", lambda: db_url)
    created = await seed_module._run()  # pyright: ignore[reportPrivateUsage]
    assert created > 0

    factory: async_sessionmaker[AsyncSession] = async_sessionmaker(create_async_engine(db_url), expire_on_commit=False)
    async with factory() as session:
        await seed_i18n_entry(session, ConcurrentStableDict())
        await session.commit()


async def test_query_messages_skips_blank_values(tmp_path: Path) -> None:
    """语言包回源跳过空白文案（视为缺失）。"""
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'msg.db'}")
    tables = [cast("Table", SysI18nMessage.__table__)]
    async with engine.begin() as conn:
        await conn.run_sync(lambda sync_conn: Base.metadata.create_all(sync_conn, tables=tables))
    factory: async_sessionmaker[AsyncSession] = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        session.add(SysI18nMessage(msg_key="common.blank", locale="zh-CN", value="   "))
        session.add(SysI18nMessage(msg_key="common.ok", locale="zh-CN", value="有值"))
        await session.commit()
        loaded = await _query_messages(session, "zh-CN")
        assert dict(loaded) == {"common.ok": "有值"}
    await engine.dispose()


async def test_ensure_single_default_without_seed_row(tmp_path: Path) -> None:
    """库中无出厂默认语言行且无默认标记 → 不置位（交由调用方按业务补齐）。"""
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'nodefault.db'}")
    tables = [cast("Table", SysI18nLocale.__table__)]
    async with engine.begin() as conn:
        await conn.run_sync(lambda sync_conn: Base.metadata.create_all(sync_conn, tables=tables))
    factory: async_sessionmaker[AsyncSession] = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        session.add(SysI18nLocale(code="en-US", name="English", is_default=False))
        await session.commit()
        await seed_module._ensure_single_default(session)  # pyright: ignore[reportPrivateUsage]
        await session.commit()
    await engine.dispose()


def test_database_url_prefers_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """种子目标库：环境变量优先于配置模板。"""
    monkeypatch.setenv("BMS_MIGRATION_URL", "sqlite+aiosqlite:///env.db")
    assert seed_module._database_url() == "sqlite+aiosqlite:///env.db"  # pyright: ignore[reportPrivateUsage]


async def test_resolve_locale_all_disabled_falls_back_to_seed() -> None:
    """快照内全部停用 → 解析回退种子清单。"""
    registry = NullLocaleRegistry()
    registry._replace_snapshot(  # pyright: ignore[reportPrivateUsage]
        ConcurrentStableList((LocaleInfo(code="zh-CN", status="disabled"),))
    )
    assert registry.resolve_locale("zh-CN") == "zh-CN"


async def test_db_translator_load_degrades() -> None:
    """回源异常（引擎不可用）→ 空映射 + 告警，不抛错。"""
    translator = DbTranslator(
        engines=cast("EngineRegistry", object()),
        registry=NullLocaleRegistry(),
        cache=MemoryI18nCacheRegion(),
    )
    assert not await translator.load_messages("zh-CN")
