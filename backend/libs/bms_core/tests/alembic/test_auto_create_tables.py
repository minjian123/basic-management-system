"""SQLite 开发库自动建表测试（Kiwi 1078）：开关 / 方言 / 链表子集 / 幂等。"""

import sqlite3
from pathlib import Path

import pytest

from bms_core.core.config import get_settings
from bms_core.db.bootstrap import db_key_for, ensure_development_schema
from bms_core.db.engine import EngineFactory
from bms_core.db.migration import resolve_chain
from bms_core.db.registry import EngineRegistry


def _tables(path: Path) -> set[str]:
    """取 SQLite 文件表名集合。

    Args:
        path: 库文件路径。

    Returns:
        set[str]: 表名集合。
    """
    connection = sqlite3.connect(path)
    try:
        return {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    finally:
        connection.close()


def _point_to(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    """把平台库 / 租户库指向临时 SQLite 文件并刷新配置。

    Args:
        tmp_path: 临时目录。
        monkeypatch: pytest monkeypatch 夹具。

    Returns:
        tuple[Path, Path]: （平台库文件, 租户库文件）。
    """
    platform = tmp_path / "platform.db"
    tenant = tmp_path / "tenant.db"
    monkeypatch.setenv("BMS_DATABASE__PLATFORM__URL", f"sqlite+aiosqlite:///{platform}")
    monkeypatch.setenv("BMS_DATABASE__TENANTS__URL", f"sqlite+aiosqlite:///{tenant}")
    get_settings.cache_clear()
    return platform, tenant


@pytest.mark.kiwi_id(1078)
def test_db_key_mapping() -> None:
    """数据源键映射：平台 → platform；租户 → 缺省租户库键；归档 → archive。"""
    assert db_key_for(resolve_chain("platform")) == "platform"
    assert db_key_for(resolve_chain("tenant")) == "tenants"
    assert db_key_for(resolve_chain("archive")) == "archive"


@pytest.mark.kiwi_id(1078)
async def test_sqlite_auto_create_tables_and_idempotent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """开关开 + SQLite：按链表集建表（平台三表 / 租户七表），重复执行幂等且不建骨架表。"""
    platform, tenant = _point_to(tmp_path, monkeypatch)
    settings = get_settings()
    assert settings.database.auto_create is True

    registry = EngineRegistry(EngineFactory(settings))
    try:
        handled = await ensure_development_schema(registry, settings)
        assert handled == ["platform", "tenants"]
        assert {"sys_tenant", "sys_module", "sys_module_i18n"} <= _tables(platform)
        assert "sys_dict_type" in _tables(tenant)
        assert "sys_task" not in _tables(tenant), "骨架表不入自动建表"

        before = (_tables(platform), _tables(tenant))
        assert await ensure_development_schema(registry, settings) == handled
        assert (_tables(platform), _tables(tenant)) == before, "重复执行不新建表"
    finally:
        await registry.aclose()


@pytest.mark.kiwi_id(1078)
async def test_auto_create_disabled_skips(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """开关关（prod 口径）：不建表。"""
    platform, tenant = _point_to(tmp_path, monkeypatch)
    settings = get_settings()
    settings.database.auto_create = False

    registry = EngineRegistry(EngineFactory(settings))
    try:
        assert await ensure_development_schema(registry, settings) == []
        assert not platform.exists() and not tenant.exists()
    finally:
        await registry.aclose()


@pytest.mark.kiwi_id(1078)
async def test_auto_create_skips_non_sqlite(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """非 SQLite 方言：跳过建表（不建连，三库结构统一走 Alembic 迁移）。"""
    monkeypatch.setenv("BMS_DATABASE__PLATFORM__URL", "mysql+aiomysql://u:p@127.0.0.1:3306/bms_platform")
    monkeypatch.setenv("BMS_DATABASE__TENANTS__URL", "mysql+aiomysql://u:p@127.0.0.1:3306/bms_tenant_demo")
    monkeypatch.setenv("BMS_DATABASE__ARCHIVE__URL", "mysql+aiomysql://u:p@127.0.0.1:3306/bms_archive")
    get_settings.cache_clear()
    settings = get_settings()

    registry = EngineRegistry(EngineFactory(settings))
    try:
        assert await ensure_development_schema(registry, settings) == []
        assert registry.active_keys() == [], "跳过后不应产生引擎"
    finally:
        await registry.aclose()
