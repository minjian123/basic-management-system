"""迁移清单边界与离线兜底（Kiwi 2359）：错误分支 / 布局缺失回落 / Alembic 配置与 head / 达梦模式切换。

口径（04_05 决策 q1=A）：本地无三库也能覆盖的路径一律单测（sqlite 真库 + 替身），不做集成豁免；
断言只锁返回值 / 异常类型 / SQL 字面，不依赖真实 PG / MySQL / 达梦实例。
"""

# pyright: reportPrivateUsage=false, reportUnusedFunction=false
import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest
from sqlalchemy import Connection

import bms_core.boundary.domains as boundary_domains
import bms_core.db.migration as migration
from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableFrozenSet, ConcurrentStableList
from bms_core.core.config import Settings
from bms_core.core.exceptions import ConfigError
from bms_core.db.migration import (
    DATASOURCE_ARCHIVE,
    DATASOURCE_TENANT,
    MigrationSeries,
    alembic_config,
    apply_session_schema,
    build_series_name,
    current_revision,
    default_series,
    domain_model_modules,
    domain_service,
    head_revision,
    import_service_models,
    layout_domain_services,
    resolve_series,
    series_url,
    unit_domains,
    unit_series,
)


def _clear_layout_caches(monkeypatch: pytest.MonkeyPatch) -> None:
    """清空布局 / 域模型的两张模块级缓存（布局替身用例前置）。

    Args:
        monkeypatch: pytest monkeypatch 夹具。
    """
    monkeypatch.setattr(migration, "_LAYOUT_FILE_DOMAIN_CACHE", ConcurrentStableDict[str, str]())
    monkeypatch.setattr(
        migration,
        "_DOMAIN_MODEL_CACHE",
        ConcurrentStableDict[str, ConcurrentStableList[str]](),
    )


class _OwnershipStub:
    """表归属记录替身（只提供域与承载服务两个字段）。"""

    def __init__(self, domain: str, owner: str) -> None:
        """初始化。

        Args:
            domain: 业务域标识。
            owner: 承载服务标识（空串表示无承载服务）。
        """
        self.domain = domain
        self.owner = owner


class _LayoutStub:
    """域布局替身（只提供 `domain_services()`）。"""

    def __init__(self, mapping: ConcurrentStableDict[str, str]) -> None:
        """初始化。

        Args:
            mapping: 域 → 承载服务映射。
        """
        self._mapping = mapping

    def domain_services(self) -> ConcurrentStableDict[str, str]:
        """取域 → 承载服务映射。

        Returns:
            ConcurrentStableDict[str, str]: 映射。
        """
        return self._mapping


class _ConnectionStub:
    """达梦会话连接替身（记录执行过的 SQL；可令首条语句失败）。"""

    def __init__(self, *, fail_first: bool, in_transaction: bool, dialect: str = "dm") -> None:
        """初始化。

        Args:
            fail_first: 首条 `SET SCHEMA` 是否抛错（验证回落分支）。
            in_transaction: `in_transaction()` 的返回值。
            dialect: 方言名。
        """
        self.dialect = SimpleNamespace(name=dialect)
        self.statements = ConcurrentStableList[str]()
        self.committed = 0
        self.calls = 0
        self._fail_first = fail_first
        self._in_transaction = in_transaction

    def exec_driver_sql(self, statement: str) -> None:
        """记录并（首条）模拟不支持 `SET SCHEMA`。

        Args:
            statement: SQL 语句。

        Raises:
            RuntimeError: 首条语句且 `fail_first` 为真时。
        """
        self.calls += 1
        if self._fail_first and self.calls == 1:
            raise RuntimeError("SET SCHEMA 不支持")
        self.statements.add(statement)

    def in_transaction(self) -> bool:
        """是否处于隐式事务。

        Returns:
            bool: 构造时给定的值。
        """
        return self._in_transaction

    def commit(self) -> None:
        """记录提交次数。"""
        self.committed += 1


@pytest.mark.kiwi_id(2359)
def test_build_series_name_rejects_invalid_forms() -> None:
    """清单名构造：空域 / 形态非法 / 数据源非法 / 归档域错配 / 未登记域一律报错。"""
    with pytest.raises(ConfigError, match="需要业务域标识"):
        build_series_name("", DATASOURCE_TENANT)
    with pytest.raises(ConfigError, match="形态非法"):
        build_series_name("Bad-Domain", DATASOURCE_TENANT)
    with pytest.raises(ConfigError, match="数据源段非法"):
        build_series_name("user", "legacy")
    with pytest.raises(ConfigError, match="归档域占位只能配归档数据源"):
        build_series_name(migration.ARCHIVE_DOMAIN, DATASOURCE_TENANT)
    with pytest.raises(ConfigError, match="未登记"):
        build_series_name("no_such_domain", DATASOURCE_TENANT)

    assert build_series_name("user", DATASOURCE_TENANT) == "user:tenant"
    assert build_series_name(migration.ARCHIVE_DOMAIN, DATASOURCE_ARCHIVE) == migration.ARCHIVE_SERIES_NAME


@pytest.mark.kiwi_id(2359)
def test_unit_domains_and_unit_series_edges() -> None:
    """单元域派生：空单元为空清单；单元清单拒绝非法数据源。"""
    assert unit_domains("") == []

    with pytest.raises(ConfigError, match="数据源段非法"):
        unit_series("platform", "legacy")

    assert unit_domains("no_such_carrier") == []


@pytest.mark.kiwi_id(2359)
def test_layout_domain_services_falls_back_to_ownership(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """布局缺失：域 → 承载服务由表归属登记的 `owner` 反推；无承载服务的域不进映射。"""
    monkeypatch.setattr(migration, "REPO_ROOT", tmp_path)
    _clear_layout_caches(monkeypatch)
    monkeypatch.setattr(migration, "registered_domains", lambda: ConcurrentStableList(["role", "ghost"]))
    monkeypatch.setattr(
        migration,
        "table_ownership_view",
        lambda: ConcurrentStableList([_OwnershipStub("role", "platform"), _OwnershipStub("ghost", "")]),
    )

    mapping = layout_domain_services()

    assert mapping == {"role": "platform"}
    assert domain_service("role") == "platform"
    assert domain_service("ghost") is None


@pytest.mark.kiwi_id(2359)
def test_layout_domain_services_merges_layout_first(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """布局在场：布局声明优先，已声明域不再被归属反推覆盖。"""
    layout_file = tmp_path / migration.DOMAIN_LAYOUT_RELATIVE
    layout_file.parent.mkdir(parents=True, exist_ok=True)
    layout_file.write_text("{}", encoding="utf-8")
    _clear_layout_caches(monkeypatch)
    monkeypatch.setattr(migration, "REPO_ROOT", tmp_path)

    def _layout(_path: Path) -> _LayoutStub:
        """替身：声明 role 域的承载服务为 identity。"""
        return _LayoutStub(ConcurrentStableDict({"role": "identity"}))

    monkeypatch.setattr(boundary_domains, "load_layout", _layout)
    monkeypatch.setattr(migration, "registered_domains", lambda: ConcurrentStableList(["role", "user"]))
    monkeypatch.setattr(
        migration,
        "table_ownership_view",
        lambda: ConcurrentStableList([_OwnershipStub("role", "platform"), _OwnershipStub("user", "identity")]),
    )

    mapping = layout_domain_services()

    assert mapping == {"role": "identity", "user": "identity"}


@pytest.mark.kiwi_id(2359)
def test_layout_file_domains_and_module_of_source(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """布局文件缺失返回空索引；源文件路径 → 模块名的各分支（非源码 / 非 py / `__init__`）。"""
    monkeypatch.setattr(migration, "REPO_ROOT", tmp_path)
    _clear_layout_caches(monkeypatch)
    assert migration._layout_file_domains() == {}

    module_of_source = migration._module_of_source
    assert module_of_source("backend/libs/x/src/pkg/a.py") == "pkg.a"
    assert module_of_source("backend/libs/x/src/pkg/__init__.py") == "pkg"
    assert module_of_source("backend/libs/x/src/__init__.py") is None
    assert module_of_source("backend/libs/x/src/pkg/a.json") is None
    assert module_of_source("frontend/src/app.ts") is None


@pytest.mark.kiwi_id(2359)
def test_declares_table_error_and_negative(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """模型声明判据：不可读 / 语法错误 / 无 `__tablename__` / 非常量赋值均判 False，常量赋值判 True。"""
    monkeypatch.setattr(migration, "REPO_ROOT", tmp_path)
    (tmp_path / "broken.py").write_text("def (:\n", encoding="utf-8")
    (tmp_path / "plain.py").write_text("TABLE = 'x'\n", encoding="utf-8")
    (tmp_path / "dynamic.py").write_text("NAME = 'x'\n__tablename__ = NAME\n", encoding="utf-8")
    (tmp_path / "table.py").write_text('__tablename__ = "demo_a"\n', encoding="utf-8")

    declares = migration._declares_table
    assert declares("missing.py") is False
    assert declares("broken.py") is False
    assert declares("plain.py") is False
    assert declares("dynamic.py") is False
    assert declares("table.py") is True


@pytest.mark.kiwi_id(2359)
def test_derived_domain_models_skips_non_package_files(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """布局登记了包外文件：声明了 `__tablename__` 但无法归一为模块 → 不进模型清单。"""
    layout = tmp_path / migration.DOMAIN_LAYOUT_RELATIVE
    layout.parent.mkdir(parents=True, exist_ok=True)
    layout.write_text(
        json.dumps(
            {
                "version": 1,
                "domains": [
                    {
                        "domain_key": "demo",
                        "service_key": "platform",
                        "status": "placement",
                        "paths": ["backend/ops/demo_model.py"],
                        "public_api": [],
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    model = tmp_path / "backend" / "ops" / "demo_model.py"
    model.parent.mkdir(parents=True, exist_ok=True)
    model.write_text('__tablename__ = "demo_a"\n', encoding="utf-8")
    monkeypatch.setattr(migration, "REPO_ROOT", tmp_path)
    _clear_layout_caches(monkeypatch)

    assert migration._derived_domain_models("demo") == []


@pytest.mark.kiwi_id(2359)
def test_domain_model_modules_fallback(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """布局缺失：域模型回落到「公共模型模块 + 服务自声明」；无承载服务的域为空清单。"""
    monkeypatch.setattr(migration, "REPO_ROOT", tmp_path)
    _clear_layout_caches(monkeypatch)
    monkeypatch.setattr(migration, "registered_domains", lambda: ConcurrentStableList(["role"]))
    monkeypatch.setattr(
        migration,
        "table_ownership_view",
        lambda: ConcurrentStableList([_OwnershipStub("role", "platform")]),
    )

    modules = domain_model_modules("role")

    assert "bms_core.models.outbox" in modules
    assert set(modules) == set(migration.COMMON_MODEL_MODULES)
    assert domain_model_modules("ghost") == []


@pytest.mark.kiwi_id(2359)
def test_import_service_models_without_layout(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """布局缺失：按服务导入模型回落公共模块面（不抛错）。"""
    monkeypatch.setattr(migration, "REPO_ROOT", tmp_path)
    _clear_layout_caches(monkeypatch)

    import_service_models("platform")

    assert "sys_outbox" in migration.Base.metadata.tables


@pytest.mark.kiwi_id(2359)
def test_alembic_config_reads_ini_and_missing_section() -> None:
    """清单配置段：缺省清单可读（走 UTF-8 读入替换实现）；未登记段 / 不可读 / 缺 version_locations 即拒。"""
    config = alembic_config(default_series())
    assert config.get_main_option("version_locations")

    with pytest.raises(ConfigError, match="配置段"):
        alembic_config(resolve_series("user:tenant"))


@pytest.mark.kiwi_id(2359)
def test_alembic_config_requires_version_locations(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """段存在但缺 `version_locations` 即拒；配置文件不可读同样快速失败。"""
    (tmp_path / "alembic.ini").write_text(
        "[alembic]\nscript_location = alembic\nversion_locations =\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(migration, "BACKEND_ROOT", tmp_path)
    with pytest.raises(ConfigError, match="缺 version_locations"):
        alembic_config(default_series())

    monkeypatch.setattr(migration, "BACKEND_ROOT", tmp_path / "missing")
    with pytest.raises(ConfigError, match="不可读"):
        alembic_config(default_series())


def _series_with_script(tmp_path: Path) -> MigrationSeries:
    """构造带一条脚本的清单（版本目录与 ini 段都在临时根下）。

    Args:
        tmp_path: 临时根。

    Returns:
        MigrationSeries: 清单定义。
    """
    location = tmp_path / "versions" / "demo" / "tenant"
    location.mkdir(parents=True, exist_ok=True)
    (tmp_path / "scripts").mkdir(parents=True, exist_ok=True)
    (location / "0001_x.py").write_text(
        'revision = "0001_x"\ndown_revision = None\n\n\ndef upgrade() -> None:\n    pass\n',
        encoding="utf-8",
    )
    (tmp_path / "alembic.ini").write_text(
        "[alembic:demo:tenant]\n"
        "script_location = %(here)s/scripts\n"
        "path_separator = os\n"
        "version_locations = %(here)s/versions/demo/tenant\n",
        encoding="utf-8",
    )
    return MigrationSeries(
        name="demo:tenant",
        domain="demo",
        datasource=DATASOURCE_TENANT,
        tables=ConcurrentStableFrozenSet[str](),
        scope="demo 域的服务租户库",
    )


@pytest.mark.kiwi_id(2359)
def test_head_revision_with_and_without_scripts(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """head 读取：无脚本返回 None；有脚本时经 Alembic `ScriptDirectory` 取 head 版本号。"""
    monkeypatch.setattr(migration, "VERSIONS_ROOT", tmp_path / "versions")
    monkeypatch.setattr(migration, "BACKEND_ROOT", tmp_path)
    series = _series_with_script(tmp_path)
    assert head_revision(series) == "0001_x"

    empty = MigrationSeries(
        name="empty:tenant",
        domain="empty",
        datasource=DATASOURCE_TENANT,
        tables=ConcurrentStableFrozenSet[str](),
        scope="empty 域的服务租户库",
    )
    assert head_revision(empty) is None


@pytest.mark.kiwi_id(2359)
def test_series_url_explicit_db_key_and_platform(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """连接串取法：显式库键经引擎工厂；平台数据源按「单元 → 域承载服务」回落库键。"""
    settings = Settings()
    settings.database.sqlite_dir = str(tmp_path)
    settings.database.archive.url = "sqlite+aiosqlite:///./bms_archive.db"
    settings.database.platform.url_template = "sqlite+aiosqlite:///{database}.db"
    settings.database.platform.url = "sqlite+aiosqlite:///./bms_platform.db"
    settings.app.unit = ""
    settings.app.service = ""

    archive = series_url(resolve_series(migration.ARCHIVE_SERIES_NAME), settings, db_key="archive")
    assert archive.endswith("bms_archive.db")

    series = resolve_series("user:platform")
    carrier = domain_service(series.domain) or series.domain
    platform = series_url(series, settings)
    assert platform.endswith(f"bms_{carrier}.db")


@pytest.mark.kiwi_id(2359)
def test_apply_session_schema_dm_branches() -> None:
    """达梦模式切换：非达梦 / 空模式为空操作；`SET SCHEMA` 成功即提交，失败回落标准 SQL 且按事务状态提交。"""
    sqlite_like = _ConnectionStub(fail_first=False, in_transaction=True, dialect="sqlite")
    apply_session_schema(cast(Connection, sqlite_like), "BMS_TEST_DM")
    assert sqlite_like.statements == []

    plain = _ConnectionStub(fail_first=False, in_transaction=True)
    apply_session_schema(cast(Connection, plain), "")
    assert plain.statements == []

    succeeded = _ConnectionStub(fail_first=False, in_transaction=True)
    apply_session_schema(cast(Connection, succeeded), "BMS_TEST_DM")
    assert succeeded.statements == ["SET SCHEMA BMS_TEST_DM"]
    assert succeeded.committed == 1

    fallback = _ConnectionStub(fail_first=True, in_transaction=False)
    apply_session_schema(cast(Connection, fallback), "BMS_TEST_DM")
    assert fallback.statements == ["ALTER SESSION SET CURRENT_SCHEMA BMS_TEST_DM"]
    assert fallback.committed == 0


@pytest.mark.kiwi_id(2359)
def test_read_revision_with_sync_sqlite(tmp_path: Path) -> None:
    """同步版本读取：无版本记录表返回 None；空表返回 None；有值返回版本号。"""
    database = tmp_path / "rev.db"
    url = f"sqlite:///{database}"
    assert migration._read_revision(url, "", "alembic_version_demo") is None

    connection = sqlite3.connect(database)
    try:
        connection.execute("CREATE TABLE alembic_version_demo (version_num VARCHAR(32))")
        connection.commit()
        assert migration._read_revision(url, "", "alembic_version_demo") is None
        connection.execute("INSERT INTO alembic_version_demo (version_num) VALUES ('0001_x')")
        connection.commit()
    finally:
        connection.close()

    assert migration._read_revision(url, "", "alembic_version_demo") == "0001_x"


@pytest.mark.kiwi_id(2359)
async def test_current_revision_dispatches_dm_to_sync(monkeypatch: pytest.MonkeyPatch) -> None:
    """达梦方言走同步线程读取（分派与返回值透传）；非达梦方言走异步引擎（无表即 None）。"""
    calls = ConcurrentStableList[str]()

    def _fake_read(url: str, schema: str, version_table: str) -> str:
        """替身：记录调用并返回固定版本号。"""
        calls.add(f"{url}|{schema}|{version_table}")
        return "0001_x"

    monkeypatch.setattr(migration, "_read_revision", _fake_read)
    result = await current_revision("dm+dmPython://SYSDBA:pwd@127.0.0.1:5236/BMS", version_table="alembic_version_demo")
    assert result == "0001_x"
    assert calls == ["dm+dmPython://SYSDBA:pwd@127.0.0.1:5236/BMS||alembic_version_demo"]


@pytest.mark.kiwi_id(2359)
async def test_current_revision_async_without_table(tmp_path: Path) -> None:
    """非达梦方言：异步引擎读不到版本表即 None（未迁移语义）。"""
    url = f"sqlite+aiosqlite:///{tmp_path / 'async.db'}"
    assert await current_revision(url, version_table="alembic_version_demo") is None
