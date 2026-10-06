"""达梦 XA 两阶段事务真库用例（需求 05-5；标记 `integration` + `dialect_dm8`）。

- **达梦单库 2PC**：`prepared→commit` 生效、`rollback`（未 prepare）未落库、`prepare→rollback` 未落库；
  经 `EngineFactory` 取同步引擎（达梦连接串方言归一为 `dmxa`）。
- **跨库框架**：单进程 MySQL × PostgreSQL 同步 2PC（真库齐备才跑；正式接入随任务 05_06）。
- 未配置 `BMS_TEST_DB_URL`（或方言非达梦）即跳过（与 `test_dm8_dialect_measure.py` 同口径）。
"""

import os
from collections.abc import Iterator

import pytest
from sqlalchemy import BigInteger, Column, Connection, Engine, MetaData, String, Table, TwoPhaseTransaction, text
from sqlalchemy.engine import make_url

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.config import Settings
from bms_core.db.engine import PLATFORM_DB_KEY, EngineFactory

pytestmark = [pytest.mark.integration, pytest.mark.dialect_dm8, pytest.mark.kiwi_id(2245)]

_PROBE = Table(
    "bms_it_dm_xa_probe",
    MetaData(),
    Column("id", BigInteger, primary_key=True, autoincrement=False),
    Column("note", String(50)),
)
"""XA 探针表（用例内建删）。"""


@pytest.fixture
def dm_url() -> str:
    """达梦真库连接串（未配置 / 方言非达梦即跳过）。"""
    url = os.environ.get("BMS_TEST_DB_URL", "")
    if not url:
        pytest.skip("未配置 BMS_TEST_DB_URL，跳过达梦 XA 真库用例")
    if make_url(url).get_backend_name() != "dm":
        pytest.skip("BMS_TEST_DB_URL 方言非达梦，跳过达梦 XA 真库用例")
    return url


@pytest.fixture
def engine(dm_url: str) -> Iterator[Engine]:
    """达梦同步引擎（经工厂，连接串方言归一为 `dmxa`）。"""
    settings = Settings()
    settings.database.platform.url = dm_url
    factory = EngineFactory(settings)
    sync_engine = factory.create_sync(PLATFORM_DB_KEY)
    try:
        yield sync_engine
    finally:
        sync_engine.dispose()


def _setup(engine: Engine) -> None:
    with engine.begin() as connection:
        _PROBE.drop(connection, checkfirst=True)
        _PROBE.create(connection)


def _count(engine: Engine, probe_id: int) -> int:
    with engine.connect() as connection:
        return int(
            connection.execute(
                text("SELECT COUNT(*) FROM bms_it_dm_xa_probe WHERE id = :i"), {"i": probe_id}
            ).scalar_one()
        )


def test_dmxa_engine_uses_dmxa_dialect(engine: Engine) -> None:
    """工厂产出的达梦同步引擎方言为 `dmxa`（全部达梦连接改走自定义 XA 方言）。"""
    assert make_url(str(engine.url)).get_backend_name() == "dmxa"


def test_dmxa_two_phase_commit(engine: Engine) -> None:
    """两阶段提交：`XA_START → INSERT → XA_END → XA_PREPARE → XA_COMMIT` 生效。"""
    _setup(engine)
    try:
        with engine.connect() as connection:
            txn = connection.begin_twophase()
            connection.execute(text("INSERT INTO bms_it_dm_xa_probe (id, note) VALUES (1, 'commit')"))
            txn.prepare()
            txn.commit()
        assert _count(engine, 1) == 1
    finally:
        _PROBE.drop(engine, checkfirst=True)


def test_dmxa_two_phase_rollback(engine: Engine) -> None:
    """两阶段回滚：`rollback`（未 prepare）与 `prepare→rollback` 均未落库。"""
    _setup(engine)
    try:
        with engine.connect() as connection:
            txn = connection.begin_twophase()
            connection.execute(text("INSERT INTO bms_it_dm_xa_probe (id, note) VALUES (2, 'rb1')"))
            txn.rollback()
        assert _count(engine, 2) == 0

        with engine.connect() as connection:
            txn = connection.begin_twophase()
            connection.execute(text("INSERT INTO bms_it_dm_xa_probe (id, note) VALUES (3, 'rb2')"))
            txn.prepare()
            txn.rollback()
        assert _count(engine, 3) == 0
    finally:
        _PROBE.drop(engine, checkfirst=True)


def _make(url: str) -> Engine:
    """按传入连接串构造同步引擎（跨库框架用例直连）。"""
    from sqlalchemy import create_engine

    return create_engine(url)


def test_cross_db_two_phase_framework() -> None:
    """跨库框架：单进程 MySQL × PostgreSQL 同步 2PC（两库齐备才跑；正式接入归 05_06）。"""
    mysql_url = os.environ.get("BMS_TEST_MYSQL_URL", "")
    pg_url = os.environ.get("BMS_TEST_PG_URL", "")
    if not mysql_url or not pg_url:
        pytest.skip("未配置 BMS_TEST_MYSQL_URL / BMS_TEST_PG_URL，跳过跨库 2PC 框架用例")

    engines = {"mysql": _make(mysql_url), "pg": _make(pg_url)}
    probes = {
        name: Table(
            f"bms_it_cross_xa_{name}",
            MetaData(),
            Column("id", BigInteger, primary_key=True, autoincrement=False),
            Column("note", String(50)),
        )
        for name in engines
    }
    try:
        for name, target in engines.items():
            with target.begin() as connection:
                probes[name].create(connection, checkfirst=True)

        connections: ConcurrentStableList[Connection] = ConcurrentStableList()
        txns: ConcurrentStableList[TwoPhaseTransaction] = ConcurrentStableList()
        for name, target in engines.items():
            connection = target.connect()
            txn = connection.begin_twophase()
            connection.execute(probes[name].insert().values(id=1, note=f"cross-{name}"))
            connections.add(connection)
            txns.add(txn)
        for txn in txns:
            txn.prepare()
        for txn in txns:
            txn.commit()

        for name, target in engines.items():
            with target.connect() as connection:
                assert (
                    connection.execute(probes[name].select().where(probes[name].c.id == 1)).one().note
                    == f"cross-{name}"
                )
        for connection in connections:
            connection.close()
    finally:
        for name, target in engines.items():
            with target.begin() as connection:
                probes[name].drop(connection, checkfirst=True)
            target.dispose()
