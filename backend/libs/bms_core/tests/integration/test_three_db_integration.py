"""三库真库集成用例（Kiwi 1155；标记 `integration` + `dialect_*`）。

- **环境守卫**：`BMS_TEST_DB_URL`（平台对象）与 `BMS_TEST_TENANT_DB_URL`（租户对象）均需配置，
  且平台连接串方言与参数一致，否则跳过（不阻塞冒烟层）。
- **前置**：由 `ops/test_db.py create / migrate --execute` 备好对象（平台对象跑 `platform` 链、
  租户对象跑 `tenant` 链）。
- **方言过滤**：参数 id 与用例名均含方言标识（`mysql` / `postgres` / `dm8`），并挂方言标记，
  保证 `pytest -k "$DB_DIALECT"` 与 `pytest -m dialect_*` 双路可命中。
- 达梦为同步方言：会话经 `session_scope` 的同步门面路径（本用例同时覆盖该路径）。
"""

import asyncio
import json
import os
from collections.abc import AsyncIterator, Callable
from datetime import datetime
from typing import Any, cast

import pytest
from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Column,
    Connection,
    DateTime,
    Engine,
    MetaData,
    String,
    Table,
    UniqueConstraint,
    insert,
    select,
    text,
)
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from bms_core.core.config import Settings
from bms_core.core.plugin import resolve_plugin
from bms_core.db.engine import PLATFORM_DB_KEY, EngineFactory
from bms_core.db.migration import current_revision, head_revision, resolve_chain
from bms_core.db.registry import EngineRegistry
from bms_core.db.session import session_scope
from bms_core.repositories.ordering import order_criteria
from bms_core.schemas.sorting import SortDirection, SortSpec
from bms_core.sharding.base import ShardingRouter
from bms_core.sharding.null import NullShardingRouter

pytestmark = [pytest.mark.integration, pytest.mark.kiwi_id(1156)]

_DIALECT_NAME = {"mysql": "mysql", "postgres": "postgresql", "dm8": "dm"}
"""参数方言 → 连接串方言名（`DB_DIALECT` 取值口径）。"""

_TENANT_DB_KEY = "tenant_demo"
"""租户库键（`url_template` 置空时回落配置的租户连接串）。"""

_PROBE = Table(
    "bms_it_probe",
    MetaData(),
    Column("id", BigInteger, primary_key=True, autoincrement=False),
    Column("flag", Boolean),
    Column("name", String(16)),
    Column("at", DateTime),
    Column("tags", JSON),
)
"""真库探针表（类型落库往返与排序 NULL 位次取证；用例内建删）。"""

_UNIQUE_PROBE = Table(
    "bms_it_unique_probe",
    MetaData(),
    Column("id", BigInteger, primary_key=True, autoincrement=False),
    Column("name", String(16)),
    Column("deleted_at", DateTime),
    UniqueConstraint("name", "deleted_at", name="uq_bms_it_unique_probe_name_deleted_at"),
)
"""软删除复合唯一探针表（未删行多 NULL 语义取证；用例内建删）。"""


@pytest.fixture(
    params=[
        pytest.param("mysql", marks=pytest.mark.dialect_mysql),
        pytest.param("postgres", marks=pytest.mark.dialect_postgres),
        pytest.param("dm8", marks=pytest.mark.dialect_dm8),
    ]
)
def dialect(request: pytest.FixtureRequest) -> str:
    """方言参数（带方言标记；参数 id 即方言标识，供 `-k` 命中）。"""
    return cast(str, request.param)


@pytest.fixture
def urls(dialect: str) -> tuple[str, str]:
    """真库两对象连接串（未配置 / 方言不匹配即跳过）。"""
    platform_url = os.environ.get("BMS_TEST_DB_URL", "")
    tenant_url = os.environ.get("BMS_TEST_TENANT_DB_URL", "")
    if not platform_url or not tenant_url:
        pytest.skip("未配置 BMS_TEST_DB_URL / BMS_TEST_TENANT_DB_URL，跳过三库真库集成用例")
    if make_url(platform_url).get_backend_name() != _DIALECT_NAME[dialect]:
        pytest.skip(f"BMS_TEST_DB_URL 方言与 {dialect} 不匹配")
    return platform_url, tenant_url


def _settings(
    platform_url: str,
    tenant_url: str,
    *,
    replicas: list[str] | None = None,
) -> Settings:
    """按真库连接串构造配置（租户模板置空 → 租户库键回落该连接串）。"""
    settings = Settings()
    settings.database.platform.url = platform_url
    settings.database.platform.replicas = replicas if replicas is not None else []
    settings.database.tenants.url = tenant_url
    settings.database.tenants.url_template = ""
    return settings


@pytest.fixture
async def registry(urls: tuple[str, str]) -> AsyncIterator[EngineRegistry]:
    """真库引擎注册表（用例结束释放全部引擎）。"""
    platform_url, tenant_url = urls
    instance = EngineRegistry(EngineFactory(_settings(platform_url, tenant_url)))
    try:
        yield instance
    finally:
        await instance.aclose()


async def _can_select(registry: EngineRegistry, db_key: str, table: str) -> bool:
    """该对象内可否查询指定表（NULL 位次 / 表集断言共用；表名取自链注册表，受控）。"""
    try:
        async with session_scope(registry, db_key=db_key) as session:
            await session.execute(text(f"SELECT COUNT(*) FROM {table}"))
    except SQLAlchemyError:
        return False
    return True


async def _scalar(
    registry: EngineRegistry,
    db_key: str,
    statement: str,
    params: dict[str, Any] | None = None,
) -> Any:
    """在指定对象上取单值（同步 / 异步方言经统一会话入口；参数化避免方言字面量差异）。"""
    async with session_scope(registry, db_key=db_key) as session:
        return (await session.execute(text(statement), params or {})).scalar_one()


def _as_json(value: object) -> object:
    """JSON 字段读回归一：达梦经 dmPython 读出为字符串（方言差异，见《方言特性 · 达梦 DM8》）。"""
    return json.loads(value) if isinstance(value, str) else value


def _with_connection(engine: Engine, action: Callable[[Connection], None]) -> None:
    """同步引擎上执行一次建删动作（达梦路径经 `asyncio.to_thread` 调用）。"""
    with engine.begin() as connection:
        action(connection)


async def _recreate_table(registry: EngineRegistry, db_key: str, table: Table) -> None:
    """重建探针表（先删后建，保证用例可重复执行；按方言走同步 / 异步引擎）。"""

    def action(connection: Connection) -> None:
        table.drop(connection, checkfirst=True)
        table.create(connection)

    if registry.is_sync_only(db_key):
        await asyncio.to_thread(_with_connection, await registry.get_sync(db_key), action)
        return
    engine = await registry.get(db_key)
    async with engine.begin() as connection:
        await connection.run_sync(action)


async def _drop_table(registry: EngineRegistry, db_key: str, table: Table) -> None:
    """删除探针表（幂等；按方言走同步 / 异步引擎）。"""

    def action(connection: Connection) -> None:
        table.drop(connection, checkfirst=True)

    if registry.is_sync_only(db_key):
        await asyncio.to_thread(_with_connection, await registry.get_sync(db_key), action)
        return
    engine = await registry.get(db_key)
    async with engine.begin() as connection:
        await connection.run_sync(action)


async def test_multi_datasource_routing(dialect: str, urls: tuple[str, str], registry: EngineRegistry) -> None:
    """多数据源路由：平台 / 租户两对象指向不同库（模式），各自可查询。"""
    platform_url, tenant_url = urls
    assert platform_url != tenant_url
    factory = EngineFactory(_settings(platform_url, tenant_url))
    assert factory.resolve_url(PLATFORM_DB_KEY) == platform_url
    assert factory.resolve_url(_TENANT_DB_KEY) == tenant_url
    assert await _scalar(registry, PLATFORM_DB_KEY, "SELECT 1") == 1
    assert await _scalar(registry, _TENANT_DB_KEY, "SELECT 1") == 1


async def test_migration_head_and_tables(dialect: str, urls: tuple[str, str], registry: EngineRegistry) -> None:
    """迁移结果：平台 / 租户对象分别处于各自链 head，且各自链表可查询（表集取自链注册）。"""
    platform_url, tenant_url = urls
    assert await current_revision(platform_url) == head_revision(resolve_chain("platform"))
    assert await current_revision(tenant_url) == head_revision(resolve_chain("tenant"))
    for table in sorted(resolve_chain("platform").tables):
        assert await _can_select(registry, PLATFORM_DB_KEY, table) is True, table
    for table in sorted(resolve_chain("tenant").tables):
        assert await _can_select(registry, _TENANT_DB_KEY, table) is True, table


async def test_tenant_isolation(dialect: str, urls: tuple[str, str], registry: EngineRegistry) -> None:
    """租户隔离：平台对象与租户对象为不同物理对象——各自链表互不可见。"""
    assert await _can_select(registry, PLATFORM_DB_KEY, "sys_tenant") is True
    assert await _can_select(registry, _TENANT_DB_KEY, "sys_dict_type") is True
    assert await _can_select(registry, PLATFORM_DB_KEY, "sys_dict_type") is False
    assert await _can_select(registry, _TENANT_DB_KEY, "sys_tenant") is False


async def test_read_replica_routing(dialect: str, urls: tuple[str, str]) -> None:
    """读写分离路由：配置副本后只读请求命中副本引擎（副本 URL），写路径仍绑主引擎。"""
    platform_url, tenant_url = urls
    instance = EngineRegistry(EngineFactory(_settings(platform_url, tenant_url, replicas=[platform_url])))
    try:
        if dialect == "dm8":
            main_engine: Any = await instance.get_sync(PLATFORM_DB_KEY)
            replica_engine: Any = await instance.get_sync(PLATFORM_DB_KEY, read_only=True)
        else:
            main_engine = await instance.get(PLATFORM_DB_KEY)
            replica_engine = await instance.get(PLATFORM_DB_KEY, read_only=True)
        assert main_engine is not replica_engine
        assert replica_engine.url == make_url(platform_url)
        assert await _scalar(instance, PLATFORM_DB_KEY, "SELECT 1") == 1
        async with session_scope(instance, db_key=PLATFORM_DB_KEY, read_only=True) as session:
            assert (await session.execute(text("SELECT 1"))).scalar_one() == 1
    finally:
        await instance.aclose()


async def test_sharding_key_query(dialect: str, urls: tuple[str, str], registry: EngineRegistry) -> None:
    """分片：缺省路由契约（不路由）+ 真库按分片键（日期列）条件查询（分片表预创建归任务调度阶段）。"""
    router = cast(ShardingRouter, resolve_plugin("sharding", ""))
    assert isinstance(router, NullShardingRouter)
    binding = router.resolve("bms_it_probe", shard_key="202609")
    assert binding.db_key == "default"
    assert binding.physical_table == "bms_it_probe"

    await _recreate_table(registry, _TENANT_DB_KEY, _PROBE)
    try:
        async with session_scope(registry, db_key=_TENANT_DB_KEY) as session:
            await session.execute(
                _PROBE.insert(),
                [
                    {"id": 1, "name": "a", "at": datetime(2026, 9, 1)},
                    {"id": 2, "name": "b", "at": datetime(2026, 10, 1)},
                ],
            )
            await session.commit()
        async with session_scope(registry, db_key=_TENANT_DB_KEY) as session:
            statement = select(_PROBE.c.id).where(_PROBE.c.at >= datetime(2026, 9, 15))
            assert (await session.execute(statement)).scalars().all() == [2]
    finally:
        await _drop_table(registry, _TENANT_DB_KEY, _PROBE)


async def test_type_probe_roundtrip(dialect: str, urls: tuple[str, str], registry: EngineRegistry) -> None:
    """类型落库往返：布尔 / JSON / 日期 / 字符串写入读回一致（各库落点见方言特性文档）。"""
    await _recreate_table(registry, _TENANT_DB_KEY, _PROBE)
    try:
        async with session_scope(registry, db_key=_TENANT_DB_KEY) as session:
            await session.execute(
                insert(_PROBE).values(id=1, flag=True, name="bms", at=datetime(2026, 9, 22, 12, 0), tags={"k": "v"}),
            )
            await session.commit()
        async with session_scope(registry, db_key=_TENANT_DB_KEY) as session:
            row = (await session.execute(select(_PROBE).where(_PROBE.c.id == 1))).one()
        assert row.name == "bms"
        assert bool(row.flag) is True
        assert row.at == datetime(2026, 9, 22, 12, 0)
        assert _as_json(row.tags) == {"k": "v"}
        assert (
            await _scalar(
                registry,
                _TENANT_DB_KEY,
                "SELECT COUNT(*) FROM bms_it_probe WHERE flag = :flag",
                {"flag": True},
            )
            == 1
        )
    finally:
        await _drop_table(registry, _TENANT_DB_KEY, _PROBE)


async def test_soft_delete_composite_unique_semantics(
    dialect: str, urls: tuple[str, str], registry: EngineRegistry
) -> None:
    """软删除复合唯一 `(唯一字段, deleted_at)` 的多 NULL 语义（**方言差异登记**）。

    - MySQL / PostgreSQL / SQLite：未删行（`deleted_at IS NULL`）可共存（DB 级保证未删行唯一）；
    - 达梦 DM8（实测）：复合唯一视 NULL 相等 → 第二条未删行被拒（差异与兜底归口见任务测试记录）；
    - 两者共同成立：软删（写入 `deleted_at`）后同键可复用。
    """
    await _recreate_table(registry, _TENANT_DB_KEY, _UNIQUE_PROBE)
    try:
        async with session_scope(registry, db_key=_TENANT_DB_KEY) as session:
            await session.execute(_UNIQUE_PROBE.insert(), [{"id": 1, "name": "same", "deleted_at": None}])
            await session.commit()

        if dialect == "dm8":
            with pytest.raises(IntegrityError):
                async with session_scope(registry, db_key=_TENANT_DB_KEY) as session:
                    await session.execute(_UNIQUE_PROBE.insert(), [{"id": 2, "name": "same", "deleted_at": None}])
                    await session.commit()
        else:
            async with session_scope(registry, db_key=_TENANT_DB_KEY) as session:
                await session.execute(_UNIQUE_PROBE.insert(), [{"id": 2, "name": "same", "deleted_at": None}])
                await session.commit()
            async with session_scope(registry, db_key=_TENANT_DB_KEY) as session:
                assert (await session.execute(text("SELECT COUNT(*) FROM bms_it_unique_probe"))).scalar_one() == 2

        async with session_scope(registry, db_key=_TENANT_DB_KEY) as session:
            await session.execute(
                _UNIQUE_PROBE.update().where(_UNIQUE_PROBE.c.id == 1).values(deleted_at=datetime(2026, 9, 22, 10, 0))
            )
            await session.execute(_UNIQUE_PROBE.insert(), [{"id": 3, "name": "same", "deleted_at": None}])
            await session.commit()
        async with session_scope(registry, db_key=_TENANT_DB_KEY) as session:
            alive = (
                (
                    await session.execute(
                        select(_UNIQUE_PROBE.c.id).where(
                            _UNIQUE_PROBE.c.name == "same", _UNIQUE_PROBE.c.deleted_at.is_(None)
                        )
                    )
                )
                .scalars()
                .all()
            )
        assert sorted(alive) == ([3] if dialect == "dm8" else [2, 3])
    finally:
        await _drop_table(registry, _TENANT_DB_KEY, _UNIQUE_PROBE)


async def test_ordering_nulls_last(dialect: str, urls: tuple[str, str], registry: EngineRegistry) -> None:
    """排序 NULL 位次：真库升 / 降序下 NULL 恒排末位（四库统一口径的真库取证）。"""
    await _recreate_table(registry, _TENANT_DB_KEY, _PROBE)
    try:
        async with session_scope(registry, db_key=_TENANT_DB_KEY) as session:
            await session.execute(
                _PROBE.insert(),
                [{"id": 1, "name": None}, {"id": 2, "name": "b"}, {"id": 3, "name": None}],
            )
            await session.commit()

        def resolve(field: str) -> Any:
            return _PROBE.c.name if field == "name" else None

        async with session_scope(registry, db_key=_TENANT_DB_KEY) as session:
            ascending = select(_PROBE.c.name).order_by(
                *order_criteria(
                    [SortSpec(field="name", direction=SortDirection.ASC)],
                    resolve=resolve,
                    id_column=_PROBE.c.id,
                )
            )
            assert (await session.execute(ascending)).scalars().all() == ["b", None, None]
            descending = select(_PROBE.c.name).order_by(
                *order_criteria(
                    [SortSpec(field="name", direction=SortDirection.DESC)],
                    resolve=resolve,
                    id_column=_PROBE.c.id,
                )
            )
            assert (await session.execute(descending)).scalars().all() == ["b", None, None]
    finally:
        await _drop_table(registry, _TENANT_DB_KEY, _PROBE)
