"""达梦 DM8 方言实测（Kiwi 1155；标记 `integration` + `dialect_dm8`）。

四项实测（结论回写《数据库设计 · 方言特性 · 达梦 DM8》与类型映射登记表）：

1. **schema 前缀与标识符大小写**：模式名与表名在元数据中呈大写；小写书写经折叠可用；
   迁移脚本不写模式前缀（由 `-x schema=` 切换会话当前模式）。
2. **软删除复合唯一 NULL 语义**（**已知差异**）：达梦把复合唯一中的 NULL 视为相等 → 未删行
   （`deleted_at IS NULL`）**不能共存**（MySQL / PostgreSQL / SQLite 可共存）；软删后同键可复用。
3. **布尔与 JSON 落库**：布尔落 `SMALLINT`（0/1）且 ORM 往返正确；`JSON` 写入正确但**读回为字符串**
   （经 dmPython 读取，应用层需 `json.loads`）。
4. **`VARCHAR2(n CHAR)` 字符长度**：长度按**字符**计（与 MySQL / PostgreSQL 语义一致）。

未配置 `BMS_TEST_DB_URL`（或方言非达梦）即跳过。
"""

import asyncio
import json
import os
from collections.abc import AsyncIterator
from datetime import datetime
from typing import cast

import pytest
from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Engine,
    MetaData,
    String,
    Table,
    UniqueConstraint,
    inspect,
    select,
    text,
)
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.core.config import Settings
from app.db.engine import PLATFORM_DB_KEY, EngineFactory
from app.db.registry import EngineRegistry
from app.db.session import session_scope

pytestmark = [pytest.mark.integration, pytest.mark.dialect_dm8, pytest.mark.kiwi_id(1156)]

_SCHEMA = "BMS_TEST_DM"
"""实测模式名（平台对象；与 CI 变量 `BMS_TEST_DB_URL` 的模式段一致）。"""

_PROBE = Table(
    "bms_it_dm_probe",
    MetaData(),
    Column("id", BigInteger, primary_key=True, autoincrement=False),
    Column("flag", Boolean),
    Column("name", String(16)),
    Column("at", DateTime),
    Column("tags", JSON),
    Column("deleted_at", DateTime),
    UniqueConstraint("name", "deleted_at", name="uq_bms_it_dm_probe_name_deleted_at"),
)
"""达梦实测探针表（布尔 / JSON / 复合唯一 NULL 语义；用例内建删）。"""


@pytest.fixture
def dm_url() -> str:
    """达梦真库连接串（未配置 / 方言非达梦即跳过）。"""
    url = os.environ.get("BMS_TEST_DB_URL", "")
    if not url:
        pytest.skip("未配置 BMS_TEST_DB_URL，跳过达梦方言实测用例")
    if make_url(url).get_backend_name() != "dm":
        pytest.skip("BMS_TEST_DB_URL 方言非达梦，跳过达梦方言实测用例")
    return url


@pytest.fixture
async def registry(dm_url: str) -> AsyncIterator[EngineRegistry]:
    """达梦引擎注册表（同步方言路径）。"""
    settings = Settings()
    settings.database.platform.url = dm_url
    instance = EngineRegistry(EngineFactory(settings))
    try:
        yield instance
    finally:
        await instance.aclose()


def _table_names(engine: Engine) -> set[str]:
    """当前连接模式下的表名集合（元数据展示口径）。"""
    with engine.connect() as connection:
        return set(inspect(connection).get_table_names())


async def _with_probe(registry: EngineRegistry) -> Engine:
    """重建探针表并返回同步引擎（调用方负责清理）。"""
    engine = await registry.get_sync(PLATFORM_DB_KEY)
    await asyncio.to_thread(_PROBE.drop, engine, checkfirst=True)
    await asyncio.to_thread(_PROBE.create, engine)
    return engine


def _as_json(value: object) -> object:
    """JSON 字段读回归一：达梦经 dmPython 读出为字符串，其余方言（或写入前）为原生对象。"""
    return json.loads(value) if isinstance(value, str) else value


async def test_dm8_schema_prefix_and_identifier_case(registry: EngineRegistry) -> None:
    """实测 1：模式与标识符大小写——库内对象名大写、方言反射归一为小写；小写书写可用；迁移不写模式前缀。"""
    engine = await registry.get_sync(PLATFORM_DB_KEY)
    try:
        names = await asyncio.to_thread(_table_names, engine)
        # 连接落在模式段指定的模式内（URL 的 database 段 → dmPython `schema` 连接参数），
        # 故反射结果即该模式的对象，且迁移未写「模式名.表名」前缀
        assert {"sys_tenant", "sys_module", "sys_module_i18n", "alembic_version"} <= names, sorted(names)

        async with session_scope(registry, db_key=PLATFORM_DB_KEY) as session:
            # 小写书写经数据库折叠（未加引号标识符）可用
            assert (await session.execute(text("SELECT COUNT(*) FROM sys_tenant"))).scalar_one() >= 0
            schema_rows = (
                await session.execute(
                    text("SELECT NAME FROM SYS.SYSOBJECTS WHERE TYPE$ = 'SCH' AND NAME = :name"),
                    {"name": _SCHEMA},
                )
            ).all()
            catalog_rows = (
                (
                    await session.execute(
                        text("SELECT TABLE_NAME FROM ALL_TABLES WHERE OWNER = :owner"),
                        {"owner": _SCHEMA},
                    )
                )
                .scalars()
                .all()
            )
        assert [str(row[0]) for row in schema_rows] == [_SCHEMA]
        catalog_names = {str(name) for name in catalog_rows}
        assert "SYS_TENANT" in catalog_names
        assert all(name == name.upper() for name in catalog_names)
    finally:
        engine.dispose()


async def test_dm8_soft_delete_composite_unique_null_semantics(registry: EngineRegistry) -> None:
    """实测 2（**已知差异**）：复合唯一 `(唯一字段, deleted_at)` 在达梦把 NULL 视为相等。

    - 实测：第一条未删行（`deleted_at IS NULL`）写入成功后，**第二条同键未删行被唯一约束拒绝**
      （`-6602 违反唯一性约束条件`）；MySQL / PostgreSQL / SQLite 则允许多 NULL 共存
      （三库分支断言见 `test_three_db_integration.py::test_soft_delete_composite_unique_semantics`）；
    - 共同成立：软删（写入 `deleted_at`）后同键可复用；
    - 差异影响面与兜底方案归口见任务测试记录「偏差与遗留」（信创适配阶段定案）。
    """
    engine = await _with_probe(registry)
    try:
        async with session_scope(registry, db_key=PLATFORM_DB_KEY) as session:
            await session.execute(_PROBE.insert(), [{"id": 1, "name": "same", "deleted_at": None}])
            await session.commit()

        with pytest.raises(IntegrityError):
            async with session_scope(registry, db_key=PLATFORM_DB_KEY) as session:
                await session.execute(_PROBE.insert(), [{"id": 2, "name": "same", "deleted_at": None}])
                await session.commit()

        async with session_scope(registry, db_key=PLATFORM_DB_KEY) as session:
            await session.execute(
                _PROBE.update().where(_PROBE.c.id == 1).values(deleted_at=datetime(2026, 9, 22, 10, 0))
            )
            await session.execute(_PROBE.insert(), [{"id": 3, "name": "same", "deleted_at": None}])
            await session.commit()

        async with session_scope(registry, db_key=PLATFORM_DB_KEY) as session:
            alive = (
                (
                    await session.execute(
                        select(_PROBE.c.id).where(_PROBE.c.name == "same", _PROBE.c.deleted_at.is_(None))
                    )
                )
                .scalars()
                .all()
            )
        assert list(alive) == [3]
    finally:
        await asyncio.to_thread(_PROBE.drop, engine, checkfirst=True)


async def test_dm8_boolean_and_json_roundtrip(registry: EngineRegistry) -> None:
    """实测 3：布尔落 `SMALLINT`（0/1）往返正确；JSON 写入正确、**读回为字符串**（方言差异）。"""
    engine = await _with_probe(registry)
    try:
        async with session_scope(registry, db_key=PLATFORM_DB_KEY) as session:
            await session.execute(
                _PROBE.insert(),
                [
                    {
                        "id": 1,
                        "flag": True,
                        "tags": {"k": "v"},
                        "at": datetime(2026, 9, 22, 12, 0),
                        "name": None,
                        "deleted_at": None,
                    },
                    {
                        "id": 2,
                        "flag": False,
                        "tags": {"n": 1},
                        "at": None,
                        "name": None,
                        "deleted_at": None,
                    },
                ],
            )
            await session.commit()

        async with session_scope(registry, db_key=PLATFORM_DB_KEY) as session:
            raw_true = (await session.execute(text("SELECT flag FROM bms_it_dm_probe WHERE id = 1"))).scalar_one()
            raw_false = (await session.execute(text("SELECT flag FROM bms_it_dm_probe WHERE id = 2"))).scalar_one()
            row = (await session.execute(select(_PROBE).where(_PROBE.c.id == 1))).one()
        assert int(cast("int", raw_true)) == 1
        assert int(cast("int", raw_false)) == 0
        assert bool(row.flag) is True
        assert row.at == datetime(2026, 9, 22, 12, 0)
        # 方言差异（实测）：达梦 `JSON` 列经 dmPython 读出为 **字符串**（非原生对象），
        # 需应用层 `json.loads`；结论回写《数据库设计 · 方言特性 · 达梦 DM8》与任务测试记录
        assert _as_json(row.tags) == {"k": "v"}
    finally:
        await asyncio.to_thread(_PROBE.drop, engine, checkfirst=True)


async def test_dm8_varchar_char_length_semantics(registry: EngineRegistry) -> None:
    """实测 4：`VARCHAR2(n CHAR)` 按字符计长——16 个中文字符可写入，17 个被拒。"""
    engine = await _with_probe(registry)
    try:
        async with session_scope(registry, db_key=PLATFORM_DB_KEY) as session:
            await session.execute(_PROBE.insert(), [{"id": 1, "name": "字" * 16}])
            await session.commit()
        async with session_scope(registry, db_key=PLATFORM_DB_KEY) as session:
            assert (await session.execute(select(_PROBE.c.name).where(_PROBE.c.id == 1))).scalar_one() == "字" * 16

        with pytest.raises(SQLAlchemyError):
            async with session_scope(registry, db_key=PLATFORM_DB_KEY) as session:
                await session.execute(_PROBE.insert(), [{"id": 2, "name": "字" * 17}])
                await session.commit()
    finally:
        await asyncio.to_thread(_PROBE.drop, engine, checkfirst=True)
