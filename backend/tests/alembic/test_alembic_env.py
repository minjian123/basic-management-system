"""迁移环境与链取值测试（Kiwi 1078）：版本号读取（异步 / 同步）与链元数据校验。"""

from pathlib import Path

import pytest
from sqlalchemy import create_engine

import app.db.migration as migration
from app.core.exceptions import ConfigError
from app.db.migration import MigrationChain, chain_metadata, current_revision, resolve_chain, resolve_chain_from_section


def _write_version(sync_url: str, revision: str) -> None:
    """用同步引擎写入 `alembic_version`（模拟迁移后状态）。

    Args:
        sync_url: 同步连接串。
        revision: 版本号。
    """
    engine = create_engine(sync_url)
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)")
            connection.exec_driver_sql(f"INSERT INTO alembic_version (version_num) VALUES ('{revision}')")
    finally:
        engine.dispose()


@pytest.mark.kiwi_id(1078)
def test_resolve_chain_from_section_rejects_foreign_section() -> None:
    """非 `alembic` 前缀的配置段 → `ConfigError`（不猜测链）。"""
    with pytest.raises(ConfigError):
        resolve_chain_from_section("engine")


@pytest.mark.kiwi_id(1078)
def test_chain_metadata_rejects_unknown_table() -> None:
    """链表集登记了模型中不存在的表 → `ConfigError`（声明与实现不符快速失败）。"""
    broken = MigrationChain(name="platform", tables=frozenset({"sys_tenant", "sys_ghost"}), scope="平台库")
    with pytest.raises(ConfigError) as excinfo:
        chain_metadata(broken)
    assert "sys_ghost" in str(excinfo.value)
    assert resolve_chain("tenant").name == "tenant"


@pytest.mark.kiwi_id(1078)
async def test_current_revision_unmigrated_and_migrated(tmp_path: Path) -> None:
    """`current_revision`：未迁移（无 `alembic_version` 表）返回 None；迁移后回读版本号。"""
    url = f"sqlite+aiosqlite:///{tmp_path / 'rev.db'}"
    assert await current_revision(url) is None

    _write_version(f"sqlite:///{tmp_path / 'rev.db'}", "0001_demo")
    assert await current_revision(url) == "0001_demo"


@pytest.mark.kiwi_id(1078)
def test_read_revision_sync_variant(tmp_path: Path) -> None:
    """同步读取变体（达梦等无异步方言驱动）：未迁移 None、迁移后回读版本号。"""
    sync_url = f"sqlite:///{tmp_path / 'sync_rev.db'}"
    assert migration._read_revision(sync_url, "") is None  # pyright: ignore[reportPrivateUsage]
    _write_version(sync_url, "0002_demo")
    assert migration._read_revision(sync_url, "") == "0002_demo"  # pyright: ignore[reportPrivateUsage]


class _FakeDialect:
    """伪方言（仅承载 `name`，用于达梦分支单测）。"""

    def __init__(self, name: str) -> None:
        self.name = name


class _FakeConnection:
    """伪连接：记录执行语句、事务状态与提交，可指定首条语句抛错（验证回落分支）。"""

    def __init__(self, dialect: str, *, fail_first: bool = False, in_transaction: bool = False) -> None:
        self.dialect = _FakeDialect(dialect)
        self.statements: list[str] = []
        self.commits = 0
        self._fail_first = fail_first
        self._in_transaction = in_transaction

    def exec_driver_sql(self, statement: str) -> None:
        """记录语句；`fail_first` 时首条抛错（模拟达梦不支持 `SET SCHEMA`）。

        Args:
            statement: SQL 语句。

        Raises:
            RuntimeError: 首条语句且 `fail_first` 为真时抛出。
        """
        self.statements.append(statement)
        if self._fail_first and len(self.statements) == 1:
            raise RuntimeError("SET SCHEMA 不支持")

    def in_transaction(self) -> bool:
        """是否处于事务中（测试替身口径可控）。

        Returns:
            bool: 事务中 True。
        """
        return self._in_transaction

    def commit(self) -> None:
        """提交并计入次数（验证 `SET SCHEMA` 后的隐式事务被结束）。"""
        self.commits += 1
        self._in_transaction = False


@pytest.mark.kiwi_id(1078)
def test_apply_session_schema_dialect_and_fallback() -> None:
    """模式切换：非达梦 / 未指定模式为空操作；达梦优先 `SET SCHEMA`，不支持时回落标准 SQL。"""
    sqlite_connection = _FakeConnection("sqlite")
    migration.apply_session_schema(sqlite_connection, "BMS_MIGRCHECK")  # type: ignore[arg-type]
    assert sqlite_connection.statements == []

    dm_connection = _FakeConnection("dm")
    migration.apply_session_schema(dm_connection, "")  # type: ignore[arg-type]
    assert dm_connection.statements == []

    migration.apply_session_schema(dm_connection, "BMS_MIGRCHECK")  # type: ignore[arg-type]
    assert dm_connection.statements == ["SET SCHEMA BMS_MIGRCHECK"]

    fallback = _FakeConnection("dm", fail_first=True)
    migration.apply_session_schema(fallback, "BMS_MIGRCHECK")  # type: ignore[arg-type]
    assert fallback.statements == [
        "SET SCHEMA BMS_MIGRCHECK",
        "ALTER SESSION SET CURRENT_SCHEMA BMS_MIGRCHECK",
    ]

    # 达梦下 `SET SCHEMA` 打开的隐式事务须立即结束（否则 Alembic 视为外部事务、版本行回滚）
    in_tx = _FakeConnection("dm", in_transaction=True)
    migration.apply_session_schema(in_tx, "BMS_MIGRCHECK")  # type: ignore[arg-type]
    assert in_tx.commits == 1


@pytest.mark.kiwi_id(1078)
def test_has_revisions_missing_directory() -> None:
    """版本目录不存在时视为空链（`False`）。"""
    ghost = MigrationChain(name="ghost", tables=frozenset(), scope="测试")
    assert migration.has_revisions(ghost) is False  # pyright: ignore[reportPrivateUsage]


@pytest.mark.kiwi_id(1078)
async def test_current_revision_delegates_to_sync_for_dm(monkeypatch: pytest.MonkeyPatch) -> None:
    """达梦方言走同步读取线程（不尝试异步引擎）。"""
    calls: list[tuple[str, str]] = []

    def fake_read(url: str, schema: str) -> str:
        """替身：记录调用并返回版本号。"""
        calls.append((url, schema))
        return "0001_demo"

    monkeypatch.setattr(migration, "_read_revision", fake_read)
    url = "dm+dmPython://SYSDBA:p@127.0.0.1:5236"
    assert await current_revision(url, schema="BMS_MIGRCHECK") == "0001_demo"
    assert calls == [(url, "BMS_MIGRCHECK")]
