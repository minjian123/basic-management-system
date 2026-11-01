"""SnowflakeId 存储类型测试（Kiwi 2394）：四库 DDL、绑定读回、SQLite 补零与排序。"""

from decimal import Decimal
from typing import cast

import pytest
from sqlalchemy import Column, MetaData, String, Table, create_engine, select, text
from sqlalchemy.dialects import mysql, postgresql, sqlite
from sqlalchemy.engine import Dialect
from sqlalchemy.engine.url import make_url
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.schema import CreateTable

from bms_core.core.id import MAX_ID
from bms_core.models.base import SQLITE_PADDED_WIDTH, SnowflakeId
from bms_core.testing.namespace import Namespace


def _dialect(name: str) -> Dialect:
    """取方言实例（达梦经 `dmSQLAlchemy` 注册的方言；只解析连接串，不建引擎、不建连）。"""
    if name == "sqlite":
        return sqlite.dialect()
    if name == "mysql":
        return mysql.dialect()
    if name == "postgresql":
        return postgresql.dialect()
    return make_url("dm+dmPython://user:password@localhost:5236").get_dialect()()


def _probe() -> Table:
    """构造类型探针表（主键 + 可空雪花列）。"""
    return Table(
        "snow_probe",
        MetaData(),
        Column("id", SnowflakeId(), primary_key=True, autoincrement=False),
        Column("parent_id", SnowflakeId(), nullable=True),
        Column("name", String(16)),
    )


@pytest.mark.kiwi_id(2394)
@pytest.mark.parametrize("name", ["sqlite", "mysql", "postgresql", "dm"])
def test_four_dialect_ddl(name: str) -> None:
    """四库 DDL：SQLite 为 TEXT，MySQL / PostgreSQL / 达梦为 DECIMAL(38, 0)。"""
    ddl = str(CreateTable(_probe()).compile(dialect=_dialect(name)))
    expected = "TEXT" if name == "sqlite" else "DECIMAL(38, 0)"
    assert f"id {expected} NOT NULL" in ddl
    assert f"parent_id {expected}" in ddl
    assert "AUTO_INCREMENT" not in ddl and "SERIAL" not in ddl


@pytest.mark.kiwi_id(2394)
def test_bind_param_by_dialect() -> None:
    """绑定：SQLite 转 38 位补零文本，其余方言保持整数；NULL 原样。"""
    snowflake = SnowflakeId()
    assert snowflake.process_bind_param(MAX_ID, sqlite.dialect()) == str(MAX_ID).zfill(SQLITE_PADDED_WIDTH)
    assert len(str(snowflake.process_bind_param(MAX_ID, sqlite.dialect()))) == SQLITE_PADDED_WIDTH
    assert snowflake.process_bind_param(MAX_ID, mysql.dialect()) == MAX_ID
    assert snowflake.process_bind_param(None, sqlite.dialect()) is None


@pytest.mark.kiwi_id(2394)
def test_bind_param_accepts_decimal_and_text() -> None:
    """绑定：接受 `Decimal` / 数字字符串（含补零），统一转整数。"""
    snowflake = SnowflakeId()
    assert snowflake.process_bind_param(Decimal(MAX_ID), mysql.dialect()) == MAX_ID
    assert snowflake.process_bind_param(str(MAX_ID).zfill(SQLITE_PADDED_WIDTH), sqlite.dialect()) == str(MAX_ID).zfill(
        SQLITE_PADDED_WIDTH
    )


@pytest.mark.kiwi_id(2394)
@pytest.mark.parametrize("value", [-1, MAX_ID + 1, True, Decimal("1.5"), 1.5, object()])
def test_bind_param_rejects_invalid(value: object) -> None:
    """绑定：负数、超上限、布尔、非整数 Decimal、浮点与未知类型一律抛错。"""
    with pytest.raises(ValueError):
        SnowflakeId().process_bind_param(value, mysql.dialect())


@pytest.mark.kiwi_id(2394)
def test_result_value_normalizes_to_int() -> None:
    """读回：int / Decimal / 补零字符串统一整数；NULL 原样。"""
    snowflake = SnowflakeId()
    assert snowflake.process_result_value(MAX_ID, mysql.dialect()) == MAX_ID
    assert snowflake.process_result_value(Decimal(MAX_ID), mysql.dialect()) == MAX_ID
    assert snowflake.process_result_value(str(MAX_ID).zfill(SQLITE_PADDED_WIDTH), sqlite.dialect()) == MAX_ID
    assert snowflake.process_result_value(None, sqlite.dialect()) is None


@pytest.mark.kiwi_id(2394)
async def test_sqlite_roundtrip_and_ordering(shared_platform_engine: AsyncEngine, ns: Namespace) -> None:
    """SQLite 真库：38 位补零往返不丢精度；字典序 = 数值序；范围比较正确。

    单库叠加口径：探针表建在共享平台库上（幂等），行按命名空间前缀写入并限定查询，
    断言只看本用例自己的行。
    """
    table = _probe()
    values = [0, 2**63 + 1, MAX_ID, MAX_ID - 1]
    prefix = ns.code("snow")
    async with shared_platform_engine.begin() as connection:
        await connection.run_sync(lambda sync_conn: table.create(sync_conn, checkfirst=True))
        await connection.execute(table.delete().where(table.c.name.like(f"{prefix}-%")))
        for index, value in enumerate(values):
            await connection.execute(table.insert().values(id=value, parent_id=None, name=f"{prefix}-{index}"))
        stored = (
            await connection.execute(
                text("select id, length(id) from snow_probe where name like :pattern order by id"),
                {"pattern": f"{prefix}-%"},
            )
        ).all()
        assert [int(row[0]) for row in stored] == sorted(values)
        assert {row[1] for row in stored} == {SQLITE_PADDED_WIDTH}
        greater = (
            (
                await connection.execute(
                    text("select id from snow_probe where name like :pattern and id > :bound order by id"),
                    {"pattern": f"{prefix}-%", "bound": str(2**63).zfill(SQLITE_PADDED_WIDTH)},
                )
            )
            .scalars()
            .all()
        )
        assert [int(item) for item in greater] == [2**63 + 1, MAX_ID - 1, MAX_ID]


@pytest.mark.kiwi_id(2394)
def test_orm_roundtrip_keeps_int() -> None:
    """ORM 往返：属性恒为 int（含审计人、逻辑外键、tenant_scope 哨兵 0）。"""
    from bms_core.models.platform.user import SysUser

    engine = create_engine("sqlite://")
    try:
        cast("Table", SysUser.__table__).create(engine)
        from sqlalchemy.orm import Session

        with Session(engine) as session:
            user = SysUser(username="u1", password_hash="x", name="用户一", status="enabled")
            session.add(user)
            session.commit()
            identifier = user.id
            assert isinstance(identifier, int) and identifier > 0
            user.parent_id = 0
            session.commit()
        with Session(engine) as session:
            loaded = session.execute(select(SysUser).where(SysUser.id == identifier)).scalar_one()
            assert isinstance(loaded.id, int)
            assert loaded.id == identifier
            assert loaded.parent_id == 0
    finally:
        engine.dispose()
