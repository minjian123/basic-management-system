"""config 域真实建表与首播用例（Kiwi 2207，03_08）：`sys_config` 建表 / 列集与平台默认种子幂等。

覆盖：`sys_config` 建表（与启动期同一表集派生点）与模型一致 / 平台默认种子幂等。
取数 / 写失效 / 缓存域 / HTTP 取数见 `test_config_runtime.py`。

测试库：临时 SQLite 文件（按 `platform:tenant` 链表集幂等建表）。
"""

import asyncio
import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from bms_core.config.seed import PLATFORM_CONFIG_DEFAULTS, seed_configs
from bms_core.core.config import get_settings
from bms_core.db.bootstrap import apply_unit_schema

pytestmark = pytest.mark.own_db("建表 / 列集与平台默认首播即被测：需空库验证建表派生与首播全量")

EXPECTED_TABLES = {
    "sys_config",
}

EXPECTED_COLUMNS = {
    "id",
    "form_key",
    "code",
    "name",
    "status",
    "value",
    "is_overridden",
    "remark",
    "parent_id",
    "created_at",
    "created_by",
    "updated_at",
    "updated_by",
    "deleted_at",
    "version",
}


def _build_schema(url: str) -> None:
    """对目标库幂等建 `platform:tenant` 链表集（与启动期 / `ops.init_schema` 同一表集派生点）。

    Args:
        url: 数据库 URL。
    """
    asyncio.run(apply_unit_schema("platform", "tenant", url, target="config_test"))


@pytest.fixture
def config_db_url(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    """临时租户库：建表 + 配置覆盖。

    Args:
        tmp_path: 临时目录。
        monkeypatch: 环境变量覆盖。

    Yields:
        str: 测试库 URL。
    """
    url = "sqlite+aiosqlite" + f":///{tmp_path / 'config_test.db'}"
    monkeypatch.setenv("BMS_DATABASE__TENANTS__URL", url)
    monkeypatch.setenv("BMS_CONFIG_SOURCE__PROVIDER", "sql")
    monkeypatch.setenv("BMS_CONFIG_CACHE_REGION__PROVIDER", "memory")
    get_settings.cache_clear()
    _build_schema(url)
    yield url
    get_settings.cache_clear()


@pytest.mark.kiwi_id(2207)
def test_schema_creates_sys_config(config_db_url: str) -> None:
    """建表：`sys_config` 表与关键列齐备。"""
    db_path = config_db_url.split("///")[-1]
    con = sqlite3.connect(db_path)
    try:
        tables = {row[0] for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        columns = {row[1] for row in con.execute("PRAGMA table_info(sys_config)")}
    finally:
        con.close()
    assert tables >= EXPECTED_TABLES
    assert columns == EXPECTED_COLUMNS


@pytest.mark.kiwi_id(2207)
async def test_seed_configs_idempotent(config_db_url: str) -> None:
    """平台默认种子幂等：首次新增全量、二次执行 0 行。"""
    engine = create_async_engine(config_db_url)
    factory: async_sessionmaker[AsyncSession] = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            first = await seed_configs(session)
        async with factory() as session:
            second = await seed_configs(session)
    finally:
        await engine.dispose()
    assert first == len(PLATFORM_CONFIG_DEFAULTS)
    assert second == 0
