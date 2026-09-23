"""四库类型映射、软删除复合唯一索引与索引命名测试（Kiwi 1050）：离线 DDL 编译 + SQLite 真库。

真库确认（01_05，2026-09-22）：本登记表的四方言落点已在 mjbk 常驻三库真库复核一致
（`BIGINT` / `DATETIME` / `VARCHAR2(n CHAR)` / `SMALLINT` 布尔 / `JSON`，见
`tests/integration/test_dm8_dialect_measure.py` 与 `test_three_db_integration.py`）；
**已知方言差异**：达梦 `JSON` 列经 dmPython 读出为字符串（应用层需 `json.loads`）、
复合唯一 `(唯一字段, deleted_at)` 在达梦视 NULL 相等（未删行不能共存）——
差异与兜底归口见 01_05 测试记录与《数据库设计 · 方言特性 · 达梦 DM8》。
"""

from pathlib import Path
from typing import cast

import pytest
from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Integer,
    MetaData,
    SmallInteger,
    String,
    Table,
    Text,
    create_engine,
    inspect,
    select,
    text,
)
from sqlalchemy.dialects import mysql, postgresql, sqlite
from sqlalchemy.engine import Dialect
from sqlalchemy.orm import Session
from sqlalchemy.schema import CreateTable

from bms_core.models.platform import SysModule
from bms_platform.models.system import SysTask

_SYS_MODULE_TABLE = cast("Table", SysModule.__table__)

_PROBE = Table(
    "type_probe",
    MetaData(),
    Column("big", BigInteger, primary_key=True, autoincrement=False),
    Column("flag", Boolean),
    Column("tiny", SmallInteger),
    Column("count", Integer),
    Column("name", String(16)),
    Column("note", Text),
    Column("at", DateTime),
    Column("tags", JSON),
)
"""类型探针表：覆盖公共字段与布尔 / 多值口径（不连库，仅编译 DDL）。"""

_EXPECTED_TYPES: dict[str, dict[str, str]] = {
    "sqlite": {
        "big": "BIGINT",
        "flag": "BOOLEAN",
        "tiny": "SMALLINT",
        "count": "INTEGER",
        "name": "VARCHAR(16)",
        "note": "TEXT",
        "at": "DATETIME",
        "tags": "JSON",
    },
    "mysql": {
        "big": "BIGINT",
        "flag": "BOOL",
        "tiny": "SMALLINT",
        "count": "INTEGER",
        "name": "VARCHAR(16)",
        "note": "TEXT",
        "at": "DATETIME",
        "tags": "JSON",
    },
    "postgresql": {
        "big": "BIGINT",
        "flag": "BOOLEAN",
        "tiny": "SMALLINT",
        "count": "INTEGER",
        "name": "VARCHAR(16)",
        "note": "TEXT",
        "at": "TIMESTAMP WITHOUT TIME ZONE",
        "tags": "JSON",
    },
    "dm": {
        "big": "BIGINT",
        "flag": "SMALLINT",
        "tiny": "SMALLINT",
        "count": "INTEGER",
        "name": "VARCHAR2(16 CHAR)",
        "note": "TEXT",
        "at": "DATETIME",
        "tags": "JSON",
    },
}
"""四库类型映射实测登记表（与 `BaseModel` docstring 一致）。

离线 DDL 编译断言为**对照基线**；真库落库复核结论见本模块 docstring
（2026-09-22 三库真库集成实测，达梦 `JSON` 读出为字符串为已知差异）。
"""


def _dialect(name: str) -> Dialect:
    """取方言实例（达梦经 `dmSQLAlchemy` 注册的 `dm+dmPython` 方言，不建连）。

    Args:
        name: sqlite / mysql / postgresql / dm。

    Returns:
        Dialect: 方言实例。
    """
    if name == "sqlite":
        return sqlite.dialect()
    if name == "mysql":
        return mysql.dialect()
    if name == "postgresql":
        return postgresql.dialect()
    return create_engine("dm+dmPython://user:password@localhost:5236").dialect


def _module(code: str, segment: str) -> SysModule:
    """构造模块注册行（绕过表默认值，仅用例数据）。

    Args:
        code: 模块简称。
        segment: 错误码段。

    Returns:
        SysModule: 模块注册行。
    """
    return SysModule(
        module_key=code,
        name=code.upper(),
        table_prefix=f"{code}_",
        errcode_segment=segment,
        event_domain=code,
    )


@pytest.mark.kiwi_id(1050)
@pytest.mark.parametrize("name", ["sqlite", "mysql", "postgresql", "dm"])
def test_four_dialect_type_mapping(name: str) -> None:
    """四库类型映射：编译 DDL 断言字段类型。"""
    ddl = str(CreateTable(_PROBE).compile(dialect=_dialect(name)))
    for column, expected in _EXPECTED_TYPES[name].items():
        assert f"{column} {expected}" in ddl, (name, column)


@pytest.mark.kiwi_id(1050)
@pytest.mark.parametrize("name", ["sqlite", "mysql", "postgresql", "dm"])
def test_soft_delete_composite_unique_in_ddl(name: str) -> None:
    """软删除复合唯一索引：四库 DDL 均含非空列 `(唯一字段, deleted_at)` 复合唯一（段位不建唯一）。"""
    ddl = str(CreateTable(_SYS_MODULE_TABLE).compile(dialect=_dialect(name)))
    for column in ("module_key", "table_prefix", "event_domain"):
        assert f"UNIQUE ({column}, deleted_at)" in ddl, (name, column)
    assert "UNIQUE (errcode_segment, deleted_at)" not in ddl


@pytest.mark.kiwi_id(1050)
def test_index_naming_convention() -> None:
    """`index=True` 生成 `idx_{表}_{列}`；显式 `uq_*` 命名不变。"""
    assert {index.name for index in _SYS_MODULE_TABLE.indexes} == {"idx_sys_module_deleted_at"}
    constraints = {constraint.name for constraint in _SYS_MODULE_TABLE.constraints}
    assert "uq_sys_module_key_deleted_at" in constraints


@pytest.mark.kiwi_id(1050)
def test_sqlite_soft_delete_unique_semantics(tmp_path: Path) -> None:
    """SQLite 真库：未删行（NULL deleted_at）共存、删除后同键复用、DDL 索引名对齐。"""
    engine = create_engine(f"sqlite:///{tmp_path / 'module.db'}")
    try:
        _SYS_MODULE_TABLE.create(engine)
        assert {index["name"] for index in inspect(engine).get_indexes("sys_module")} == {"idx_sys_module_deleted_at"}
        with Session(engine) as session:
            session.add(_module("sys", "01"))
            session.add(_module("wf", "02"))
            session.commit()

            first = session.execute(select(SysModule).where(SysModule.module_key == "sys")).scalar_one()
            first.soft_delete()
            session.commit()

            session.add(_module("sys", "11"))
            session.commit()
            rows = session.execute(select(SysModule).where(SysModule.module_key == "sys")).scalars().all()
            assert len(rows) == 2
            assert sorted(row.deleted_at is None for row in rows) == [False, True]
    finally:
        engine.dispose()


@pytest.mark.kiwi_id(1050)
def test_boolean_storage_roundtrip(tmp_path: Path) -> None:
    """布尔字段 SQLite 真库按小整数 1/0 落库。"""
    engine = create_engine(f"sqlite:///{tmp_path / 'task.db'}")
    try:
        cast("Table", SysTask.__table__).create(engine)
        with Session(engine) as session:
            session.add(SysTask(name="demo", handler="bms_core.tasks.demo"))
            session.commit()
            assert session.execute(text("SELECT enabled FROM sys_task")).scalar_one() == 1
    finally:
        engine.dispose()
