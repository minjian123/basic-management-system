"""达梦悬挂分支「列举 → 驱动」可回放真库用例（需求 05-5；Kiwi 2271；标记 `integration` + `dialect_dm8`）。

- **口径**：`XA_PREPARE` 后经 `do_recover_twophase`（`TABLE(DBMS_XA.XA_RECOVER())` + `RAWTOHEX`）列举出的
  分支必须**可直接回放驱动**——载体 `DMXARecoveredXid` 原样喂给 `XA_COMMIT` / `XA_ROLLBACK` 即达终态。
  （原缺陷：列举恒空、`_xid_raw` 用不可逆派生 ⇒「列举得出、驱动不了」。）
- **清理纪律**：断言失败也必须先回滚悬挂分支再删探针表（悬挂分支会以元数据锁挡住 `DROP`）。
- 未配置 `BMS_TEST_DB_URL`（或方言非达梦）即跳过；探针表用例内建删。
"""

import os
import uuid
from collections.abc import Iterator
from typing import cast

import pytest
from sqlalchemy import BigInteger, Column, Engine, MetaData, String, Table, text
from sqlalchemy.engine import make_url

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.config import Settings
from bms_core.db.dialects.dm_xa import DMXADialect, DMXARecoveredXid
from bms_core.db.engine import PLATFORM_DB_KEY, EngineFactory

pytestmark = [pytest.mark.integration, pytest.mark.dialect_dm8, pytest.mark.kiwi_id(2271)]

_PROBE = Table(
    f"bms_it_dm_xa_recover_probe_{uuid.uuid4().hex[:8]}",
    MetaData(),
    Column("id", BigInteger, primary_key=True, autoincrement=False),
    Column("note", String(50)),
)
"""悬挂分支可回放探针表（带进程随机后缀，避免 xdist 并行同库撞表；用例内建删）。"""

_XID_COMMIT = "bms-it-dmxa-recover-commit"
"""提交路径的分支标识（`gtrid` 派生源）。"""

_XID_ROLLBACK = "bms-it-dmxa-recover-rollback"
"""回滚路径的分支标识。"""


@pytest.fixture
def dm_url() -> str:
    """达梦真库连接串（未配置 / 方言非达梦即跳过）。"""
    url = os.environ.get("BMS_TEST_DB_URL", "")
    if not url:
        pytest.skip("未配置 BMS_TEST_DB_URL，跳过达梦悬挂分支可回放用例")
    if make_url(url).get_backend_name() != "dm":
        pytest.skip("BMS_TEST_DB_URL 方言非达梦，跳过达梦悬挂分支可回放用例")
    return url


@pytest.fixture
def engine(dm_url: str) -> Iterator[Engine]:
    """达梦同步引擎（经工厂：连接串方言归一为 `dmxa`，并走基座客户端加密模块自检）。"""
    settings = Settings()
    settings.database.platform.url = dm_url
    sync_engine = EngineFactory(settings).create_sync(PLATFORM_DB_KEY)
    try:
        yield sync_engine
    finally:
        sync_engine.dispose()


def _setup(engine: Engine) -> None:
    """建探针表（幂等）。"""
    with engine.begin() as connection:
        _PROBE.drop(connection, checkfirst=True)
        _PROBE.create(connection)


def _teardown(engine: Engine) -> None:
    """删探针表（幂等）。"""
    with engine.begin() as connection:
        _PROBE.drop(connection, checkfirst=True)


def _dialect(engine: Engine) -> DMXADialect:
    """取达梦自定义 XA 方言（引擎经工厂建出，方言即 `dmxa`）。"""
    return cast("DMXADialect", engine.dialect)


def _hung_branch(engine: Engine, xid: str) -> ConcurrentStableList[DMXARecoveredXid]:
    """列举与本分支对应的悬挂分支（可回放载体）。"""
    dialect = _dialect(engine)
    found: ConcurrentStableList[DMXARecoveredXid] = ConcurrentStableList()
    with engine.connect() as connection:
        for item in dialect.do_recover_twophase(connection):
            if dialect.matches_recovered_xid(xid, item):
                found.add(item)
    return found


def _note(engine: Engine, probe_id: int) -> str | None:
    """读某探针 id 的 note（无行返回 None）。"""
    with engine.connect() as connection:
        return connection.execute(text(f"SELECT note FROM {_PROBE.name} WHERE id = :i"), {"i": probe_id}).scalar()


def _prepare_hung(engine: Engine, xid: str, probe_id: int, note: str) -> None:
    """开分支 → 写探针行 → `prepare` → 分离连接（分支由数据库侧持有，驱动走新连接）。

    分离是必需的：SQLAlchemy 的 `TwoPhaseTransaction` 在 `prepare()` 后 `is_active` 仍为真，
    直接 `close()` 会**回滚已 prepared 的分支**（见 `bms_core/transaction/xa.py` 同源口径）。
    """
    connection = engine.connect()
    txn = connection.begin_twophase(xid)
    connection.execute(text(f"INSERT INTO {_PROBE.name} (id, note) VALUES (:i, :n)"), {"i": probe_id, "n": note})
    txn.prepare()
    connection.detach()


def _rollback_hung(engine: Engine, xid: str) -> None:
    """尽力回滚悬挂分支（清理用；失败不掩盖原始异常）。"""
    try:
        dialect = _dialect(engine)
        with engine.connect() as connection:
            for item in dialect.do_recover_twophase(connection):
                if dialect.matches_recovered_xid(xid, item):
                    dialect.do_rollback_twophase(connection, item, True, True)
    except Exception:  # 清理路径失败不掩盖用例结论
        return


def test_recovered_branch_drives_commit(engine: Engine) -> None:
    """列举出的悬挂分支经可回放载体直接驱动 `XA_COMMIT`：业务行可见、悬挂清零。"""
    _setup(engine)
    try:
        _prepare_hung(engine, _XID_COMMIT, 1, "recover-commit")
        branch = _hung_branch(engine, _XID_COMMIT)
        assert len(branch) == 1
        assert isinstance(branch[0], DMXARecoveredXid)
        with engine.connect() as driver:
            _dialect(engine).do_commit_twophase(driver, branch[0], True, True)
        assert _note(engine, 1) == "recover-commit"
        assert _hung_branch(engine, _XID_COMMIT) == []
    finally:
        _rollback_hung(engine, _XID_COMMIT)
        _teardown(engine)


def test_recovered_branch_drives_rollback(engine: Engine) -> None:
    """列举出的悬挂分支经可回放载体直接驱动 `XA_ROLLBACK`：业务行不可见、悬挂清零。"""
    _setup(engine)
    try:
        _prepare_hung(engine, _XID_ROLLBACK, 2, "recover-rollback")
        branch = _hung_branch(engine, _XID_ROLLBACK)
        assert len(branch) == 1
        with engine.connect() as driver:
            _dialect(engine).do_rollback_twophase(driver, branch[0], True, True)
        assert _note(engine, 2) is None
        assert _hung_branch(engine, _XID_ROLLBACK) == []
    finally:
        _rollback_hung(engine, _XID_ROLLBACK)
        _teardown(engine)
