"""库级建删能力测试（Kiwi 1078）：目标解析、SQLite 真跑与三方言语句断言。"""

from pathlib import Path

import pytest

import app.db.admin as admin
from app.core.exceptions import ConfigError
from app.db.admin import (
    DatabaseTarget,
    admin_url_for,
    create_database,
    database_exists,
    database_name_of,
    drop_database,
    resolve_target,
)


@pytest.mark.kiwi_id(1078)
def test_resolve_target_and_admin_url() -> None:
    """目标解析：库名 / 文件路径 / 模式名（达梦大写）与管理连接串推导。"""
    assert database_name_of("mysql+aiomysql://u:p@h:3306/bms_migrcheck") == "bms_migrcheck"
    assert admin_url_for("mysql+aiomysql://u:p@h:3306/bms_migrcheck").endswith("h:3306")
    assert admin_url_for("postgresql+psycopg://u:p@h:5432/bms_migrcheck").endswith("/postgres")
    assert admin_url_for("sqlite+aiosqlite:///./x.db") == "sqlite+aiosqlite:///./x.db"
    assert admin_url_for("mysql+aiomysql://u:p@h:3306/x", override="mysql+aiomysql://root@h:3306").startswith("mysql")
    assert resolve_target("dm+dmPython://SYSDBA:p@h:5236", name="bms_migrcheck").name == "BMS_MIGRCHECK"


@pytest.mark.kiwi_id(1078)
def test_resolve_target_rejects_illegal_name() -> None:
    """库名 / 模式名形态非法（含注入样例）→ `ConfigError`。"""
    with pytest.raises(ConfigError):
        resolve_target("mysql+aiomysql://u:p@h:3306/x", name="bms;drop")
    with pytest.raises(ConfigError):
        resolve_target("mysql+aiomysql://u:p@h:3306/")
    with pytest.raises(ConfigError):
        resolve_target("sqlite+aiosqlite://")


@pytest.mark.kiwi_id(1078)
async def test_sqlite_create_exists_drop(tmp_path: Path) -> None:
    """SQLite 建删文件：新建 → 存在 → 重复建跳过 → 删除 → 重复删跳过。"""
    url = f"sqlite+aiosqlite:///{tmp_path / 'nested' / 'bms_migrcheck.db'}"
    target = resolve_target(url)
    assert target.is_file is True
    assert await database_exists(target) is False

    assert await create_database(target) is True
    assert await database_exists(target) is True
    assert await create_database(target) is False

    assert await drop_database(target) is True
    assert await database_exists(target) is False
    assert await drop_database(target) is False


@pytest.mark.kiwi_id(1078)
async def test_mysql_statements(monkeypatch: pytest.MonkeyPatch) -> None:
    """MySQL 语句：存在性查询、`CREATE DATABASE IF NOT EXISTS`（utf8mb4）、`DROP DATABASE IF EXISTS`。"""
    url = "mysql+aiomysql://u:p@h:3306/bms_migrcheck"
    target = resolve_target(url)
    statements: list[str] = []
    fetches: list[str] = []

    async def fake_fetch(admin_url: str, statement: str, *, name: str) -> list[object]:
        """替身：记录查询并模拟「不存在」。"""
        del admin_url, name
        fetches.append(statement)
        return []

    async def fake_execute(admin_url: str, statement: str) -> None:
        """替身：记录管理语句。"""
        del admin_url
        statements.append(statement)

    monkeypatch.setattr(admin, "_fetch", fake_fetch)
    monkeypatch.setattr(admin, "_execute", fake_execute)

    assert await create_database(target) is True
    assert statements == [
        "CREATE DATABASE IF NOT EXISTS `bms_migrcheck` DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci"
    ]
    assert "information_schema.SCHEMATA" in fetches[0]

    fetches.clear()
    monkeypatch.setattr(admin, "_fetch", _fetch_existing)
    statements.clear()
    assert await create_database(target) is False, "已存在应跳过"
    assert await drop_database(target) is True
    assert statements == ["DROP DATABASE IF EXISTS `bms_migrcheck`"]


@pytest.mark.kiwi_id(1078)
async def test_postgresql_and_dm_statements(monkeypatch: pytest.MonkeyPatch) -> None:
    """PostgreSQL / 达梦语句：建库（UTF8）/ 建删模式与存在性查询。"""
    statements: list[str] = []

    async def fake_fetch(admin_url: str, statement: str, *, name: str) -> list[object]:
        """替身：模拟不存在。"""
        del admin_url, statement, name
        return []

    async def fake_execute(admin_url: str, statement: str) -> None:
        """替身：记录管理语句。"""
        del admin_url
        statements.append(statement)

    monkeypatch.setattr(admin, "_fetch", fake_fetch)
    monkeypatch.setattr(admin, "_execute", fake_execute)

    pg = resolve_target("postgresql+psycopg://u:p@h:5432/bms_migrcheck")
    assert await create_database(pg) is True
    assert statements == ["""CREATE DATABASE "bms_migrcheck" ENCODING 'UTF8'"""]

    statements.clear()
    dm = resolve_target("dm+dmPython://SYSDBA:p@h:5236", name="bms_migrcheck")
    assert dm.name == "BMS_MIGRCHECK"
    assert await create_database(dm) is True
    assert statements == ["CREATE SCHEMA BMS_MIGRCHECK"]

    statements.clear()
    monkeypatch.setattr(admin, "_fetch", _fetch_existing)
    assert await drop_database(dm) is True
    assert statements == ["DROP SCHEMA BMS_MIGRCHECK CASCADE"]


async def _fetch_existing(admin_url: str, statement: str, *, name: str) -> list[object]:
    """替身：模拟目标已存在。

    Args:
        admin_url: 管理连接串。
        statement: 查询语句。
        name: 目标名。

    Returns:
        list[object]: 单行结果。
    """
    del admin_url, statement, name
    return [(1,)]


@pytest.mark.kiwi_id(1078)
async def test_target_describe_masks_password() -> None:
    """目标描述为脱敏形态（不暴露连接串密码）。"""
    target = DatabaseTarget(
        dialect="mysql",
        name="bms_migrcheck",
        url="mysql+aiomysql://u:secret@h:3306/bms_migrcheck",
        admin_url="mysql+aiomysql://root:secret@h:3306",
    )
    assert target.describe() == "mysql bms_migrcheck"
    assert "secret" not in target.describe()


@pytest.mark.kiwi_id(1078)
async def test_statement_helpers_execute_on_sqlite(tmp_path: Path) -> None:
    """语句执行 / 查询助手（异步与同步变体）真实生效（达梦同步分支同源，SQLite 代跑）。"""
    async_url = f"sqlite+aiosqlite:///{tmp_path / 'helper.db'}"
    sync_url = f"sqlite:///{tmp_path / 'helper.db'}"

    await admin._execute(async_url, "CREATE TABLE probe (id INTEGER)")  # pyright: ignore[reportPrivateUsage]
    await admin._execute(async_url, "INSERT INTO probe (id) VALUES (1)")  # pyright: ignore[reportPrivateUsage]
    rows = await admin._fetch(async_url, "SELECT id FROM probe WHERE id = :name", name="1")  # pyright: ignore[reportPrivateUsage]
    assert len(rows) == 1

    admin._execute_sync(sync_url, "INSERT INTO probe (id) VALUES (2)")  # pyright: ignore[reportPrivateUsage]
    sync_rows = admin._fetch_sync(sync_url, "SELECT id FROM probe", "probe")  # pyright: ignore[reportPrivateUsage]
    assert len(sync_rows) == 2


@pytest.mark.kiwi_id(1078)
async def test_drop_missing_target_skips(monkeypatch: pytest.MonkeyPatch) -> None:
    """非文件型目标不存在时 `drop` 跳过（返回 False，不执行语句）。"""
    statements: list[str] = []

    async def fake_fetch(admin_url: str, statement: str, *, name: str) -> list[object]:
        """替身：模拟目标不存在。"""
        del admin_url, statement, name
        return []

    async def fake_execute(admin_url: str, statement: str) -> None:
        """替身：记录语句。"""
        del admin_url
        statements.append(statement)

    monkeypatch.setattr(admin, "_fetch", fake_fetch)
    monkeypatch.setattr(admin, "_execute", fake_execute)

    target = resolve_target("mysql+aiomysql://u:p@h:3306/bms_migrcheck")
    assert await drop_database(target) is False
    assert statements == []


@pytest.mark.kiwi_id(1078)
async def test_dm_delegates_to_sync_helpers(monkeypatch: pytest.MonkeyPatch) -> None:
    """达梦方言经同步助手线程执行（不尝试异步引擎）。"""
    executed: list[tuple[str, str]] = []
    fetched: list[tuple[str, str, str]] = []

    def fake_execute_sync(admin_url: str, statements: str) -> None:
        """替身：记录同步执行。"""
        executed.append((admin_url, statements))

    def fake_fetch_sync(admin_url: str, statement: str, name: str) -> list[object]:
        """替身：记录同步查询并返回空结果。"""
        fetched.append((admin_url, statement, name))
        return []

    monkeypatch.setattr(admin, "_execute_sync", fake_execute_sync)
    monkeypatch.setattr(admin, "_fetch_sync", fake_fetch_sync)

    url = "dm+dmPython://SYSDBA:p@127.0.0.1:5236"
    await admin._execute(url, "CREATE SCHEMA BMS_MIGRCHECK")  # pyright: ignore[reportPrivateUsage]
    assert executed == [(url, "CREATE SCHEMA BMS_MIGRCHECK")]
    assert await admin._fetch(url, "SELECT 1 FROM ALL_USERS WHERE USERNAME = :name", name="BMS_MIGRCHECK") == []  # pyright: ignore[reportPrivateUsage]
    assert fetched[0][2] == "BMS_MIGRCHECK"
