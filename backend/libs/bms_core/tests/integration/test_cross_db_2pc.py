"""三库单进程 2PC 真库证据用例（Kiwi 2246）：技术储备可行性取证。

- **单库三态**：`prepare→commit` 生效 / `rollback`（未 prepare）未落库 / `prepare→rollback` 未落库。
- **单进程跨库 2PC**：≥2 库齐备时，全员 `prepare→commit` 全部生效、全员 `prepare→rollback` 全部未落库。
- **悬挂分支可见性**：`XA RECOVER`（MySQL）/ `pg_prepared_xacts`（PG）/ `DBMS_XA.XA_RECOVER`（达梦）。
- **2PC 走同步引擎**（异步 API 不暴露两阶段）；达梦连接串须用自定义方言 `dmxa`。
- 环境变量按方言配置（`BMS_TEST_MYSQL_URL` / `BMS_TEST_PG_URL` / `BMS_TEST_DM_URL`）；
  未配置即跳过（不阻塞冒烟层）。凭据不入库，经环境变量注入。
"""

import os

import pytest
from sqlalchemy import Connection, Engine, TwoPhaseTransaction, create_engine, text

import bms_core.db  # noqa: F401  # pyright: ignore[reportUnusedImport]  导入即注册达梦自定义 XA 方言 `dmxa`
from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList

pytestmark = [pytest.mark.integration, pytest.mark.kiwi_id(2246)]

_TABLE = "bms_it_2pc_probe"
_ENV = {
    "mysql": "BMS_TEST_MYSQL_URL",
    "postgres": "BMS_TEST_PG_URL",
    "dm8": "BMS_TEST_DM_URL",
}
_CREATE = {
    "mysql": f"CREATE TABLE {_TABLE} (id INT PRIMARY KEY, note VARCHAR(50)) ENGINE=InnoDB",
    "postgres": f"CREATE TABLE {_TABLE} (id INT PRIMARY KEY, note VARCHAR(50))",
    "dm8": f"CREATE TABLE {_TABLE} (id INT PRIMARY KEY, note VARCHAR(50))",
}
_RECOVER = {
    "mysql": "XA RECOVER",
    "postgres": "SELECT COUNT(*) FROM pg_prepared_xacts",
    "dm8": "SELECT COUNT(*) FROM TABLE(DBMS_XA.XA_RECOVER())",
}


@pytest.fixture(scope="module")
def available_dbs() -> ConcurrentStableDict[str, str]:
    """按环境变量收集可用的真库连接串（一个都没有即跳过整个模块）。"""
    urls: ConcurrentStableDict[str, str] = ConcurrentStableDict(
        {name: os.environ[env] for name, env in _ENV.items() if os.environ.get(env)}
    )
    if not urls:
        pytest.skip("未配置任一 BMS_TEST_*_URL（mysql/postgres/dm8），跳过三库 2PC 真库用例")
    return urls


def _engine(url: str) -> Engine:
    """按连接串构造同步引擎（2PC 仅同步引擎可用）。"""
    return create_engine(url)


def _setup(db_name: str, engine: Engine) -> None:
    """建探测表（幂等）。"""
    with engine.begin() as connection:
        connection.execute(text(f"DROP TABLE IF EXISTS {_TABLE}"))
        connection.execute(text(_CREATE[db_name]))


def _teardown(engine: Engine) -> None:
    """删探测表（幂等）。"""
    try:
        with engine.begin() as connection:
            connection.execute(text(f"DROP TABLE IF EXISTS {_TABLE}"))
    finally:
        engine.dispose()


def _note(engine: Engine, probe_id: int) -> str | None:
    """读某探针 id 的 note（无行返回 None）。"""
    with engine.connect() as connection:
        return connection.execute(text(f"SELECT note FROM {_TABLE} WHERE id = :i"), {"i": probe_id}).scalar()


def _insert_committed(engine: Engine, probe_id: int) -> None:
    """单库两阶段：prepare → commit（应生效）。"""
    with engine.connect() as connection:
        txn = connection.begin_twophase()
        connection.execute(text(f"INSERT INTO {_TABLE} (id, note) VALUES (:i, :n)"), {"i": probe_id, "n": "commit"})
        txn.prepare()
        txn.commit()


@pytest.mark.parametrize("db_name", ["mysql", "postgres", "dm8"])
def test_single_db_two_phase_states(db_name: str, available_dbs: ConcurrentStableDict[str, str]) -> None:
    """单库三态：`prepare→commit` 生效、`rollback`（未 prepare）与 `prepare→rollback` 均未落库。"""
    if db_name not in available_dbs:
        pytest.skip(f"未配置 {_ENV[db_name]}，跳过 {db_name} 单库 2PC 用例")
    engine = _engine(available_dbs[db_name])
    _setup(db_name, engine)
    try:
        _insert_committed(engine, 1)
        assert _note(engine, 1) == "commit"

        with engine.connect() as connection:
            txn = connection.begin_twophase()
            connection.execute(text(f"INSERT INTO {_TABLE} (id, note) VALUES (2, 'rb1')"))
            txn.rollback()
        assert _note(engine, 2) is None

        with engine.connect() as connection:
            txn = connection.begin_twophase()
            connection.execute(text(f"INSERT INTO {_TABLE} (id, note) VALUES (3, 'rb2')"))
            txn.prepare()
            txn.rollback()
        assert _note(engine, 3) is None
    finally:
        _teardown(engine)


@pytest.mark.parametrize("db_name", ["mysql", "postgres", "dm8"])
def test_hung_branch_visible(db_name: str, available_dbs: ConcurrentStableDict[str, str]) -> None:
    """悬挂分支可见：prepare 后经各库恢复视图可见，回滚可清理。"""
    if db_name not in available_dbs:
        pytest.skip(f"未配置 {_ENV[db_name]}，跳过 {db_name} 悬挂分支用例")
    engine = _engine(available_dbs[db_name])
    _setup(db_name, engine)
    try:
        connection = engine.connect()
        txn = connection.begin_twophase()
        connection.execute(text(f"INSERT INTO {_TABLE} (id, note) VALUES (9, 'hung')"))
        txn.prepare()
        with engine.connect() as probe:
            rows = probe.execute(text(_RECOVER[db_name])).fetchall()
        assert rows, f"{db_name} 应可见悬挂分支"
        txn.rollback()
        connection.close()
        assert _note(engine, 9) is None
    finally:
        _teardown(engine)


def test_cross_db_two_phase(available_dbs: ConcurrentStableDict[str, str]) -> None:
    """单进程跨库 2PC：≥2 库全员 prepare→commit 全部生效、全员 prepare→rollback 全部未落库。"""
    if len(available_dbs) < 2:
        pytest.skip("少于两个真库连接串，跳过跨库 2PC 用例")
    engines: ConcurrentStableDict[str, Engine] = ConcurrentStableDict(
        {name: _engine(url) for name, url in available_dbs.items()}
    )
    for name in engines:
        _setup(name, engines[name])
    try:

        def _run(probe_id: int, commit: bool) -> None:
            connections: ConcurrentStableList[Connection] = ConcurrentStableList()
            txns: ConcurrentStableList[TwoPhaseTransaction] = ConcurrentStableList()
            try:
                for name, engine in engines.items():
                    connection = engine.connect()
                    txn = connection.begin_twophase()
                    connection.execute(
                        text(f"INSERT INTO {_TABLE} (id, note) VALUES (:i, :n)"),
                        {"i": probe_id, "n": f"cross-{name}"},
                    )
                    connections.add(connection)
                    txns.add(txn)
                for txn in txns:
                    txn.prepare()
                for txn in txns:
                    txn.commit() if commit else txn.rollback()
            finally:
                for connection in connections:
                    connection.close()

        _run(10, commit=True)
        assert all(_note(engine, 10) == f"cross-{name}" for name, engine in engines.items())

        _run(11, commit=False)
        assert all(_note(engine, 11) is None for engine in engines.values())
    finally:
        for engine in engines.values():
            _teardown(engine)
