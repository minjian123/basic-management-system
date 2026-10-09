"""达梦悬挂分支回收与可回放 `xid` 载体用例（强一致专项 05_07；Kiwi 2271）。

`do_recover_twophase` 原恒返回空、且 `_xid_raw` 以 `blake2b` **不可逆派生**——「列举得出、驱动不了」。
本用例覆盖补齐后的两要点：① 可回放载体 `DMXARecoveredXid` 被 `_xid_raw` **直接使用、不再哈希**；
② 经 `TABLE(DBMS_XA.XA_RECOVER())` + `RAWTOHEX` 还原悬挂分支；并发起 `commit` / `rollback` 驱动验证。
"""

import pytest
from sqlalchemy import TextClause

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.db.dialects.dm_xa import DMXADialect, DMXARecoveredXid

pytestmark = [pytest.mark.kiwi_id(2271)]


class _FakeResult:
    """`execute(...)` 返回值替身：只提供 `fetchall`。"""

    def __init__(self, rows: ConcurrentStableList[tuple[object, object]]) -> None:
        self._rows = rows

    def fetchall(self) -> ConcurrentStableList[tuple[object, object]]:
        """返回预设行。"""
        return self._rows


class _FakeConnection:
    """SQLAlchemy 连接替身：记录执行的 SQL（断言驱动语句内容）。"""

    def __init__(self, rows: ConcurrentStableList[tuple[object, object]] | None = None) -> None:
        self.rows: ConcurrentStableList[tuple[object, object]] = (
            rows if rows is not None else ConcurrentStableList[tuple[object, object]]()
        )
        self.statements: ConcurrentStableList[str] = ConcurrentStableList()

    def execute(self, statement: TextClause) -> _FakeResult:
        """记录并返回预设结果。

        Args:
            statement: SQL 语句。

        Returns:
            _FakeResult: 预设行。
        """
        self.statements.add(str(statement))
        return _FakeResult(self.rows)


def test_recovered_xid_text_and_equality() -> None:
    """可回放载体：文本形态 `gtrid|bqual`、小写归一、按值相等与可哈希。"""
    left = DMXARecoveredXid("AB12", "CD34")
    right = DMXARecoveredXid("ab12", "cd34")

    assert str(left) == "ab12|cd34"
    assert left == right
    assert hash(left) == hash(right)
    assert len({left, right}) == 1


def test_xid_raw_uses_recovered_hex_directly() -> None:
    """`_xid_raw` 对可回放载体**直接使用**（不再 `blake2b` 派生）。"""
    recovered = DMXARecoveredXid("0123456789abcdef", "fedcba9876543210")

    assert DMXADialect._xid_raw(recovered) == ("0123456789abcdef", "fedcba9876543210")  # pyright: ignore[reportPrivateUsage]


def test_xid_raw_derives_stable_hex_for_plain_xid() -> None:
    """普通 `xid`（字符串）仍走稳定派生，且与可回放形态**不同**（防误用）。"""
    first = DMXADialect._xid_raw("branch-1")  # pyright: ignore[reportPrivateUsage]
    second = DMXADialect._xid_raw("branch-1")  # pyright: ignore[reportPrivateUsage]

    assert first == second
    assert all(len(part) == 16 for part in first)
    assert first != DMXADialect._xid_raw(DMXARecoveredXid("branch-1", "branch-1"))  # pyright: ignore[reportPrivateUsage]


def test_recover_twophase_returns_replayable_xids() -> None:
    """悬挂列举：`RAWTOHEX` 还原为可回放载体，空值行跳过。"""
    connection = _FakeConnection(rows=ConcurrentStableList([("AB12", "CD34"), (None, None), ("0099", "0088")]))

    recovered = DMXADialect().do_recover_twophase(connection)

    assert list(recovered) == [DMXARecoveredXid("ab12", "cd34"), DMXARecoveredXid("0099", "0088")]
    assert "DBMS_XA.XA_RECOVER" in connection.statements[0]
    assert "RAWTOHEX" in connection.statements[0]


def test_recovered_xid_drives_commit_and_rollback() -> None:
    """回放闭环：可回放载体可直接驱动 `XA_COMMIT` / `XA_ROLLBACK`（原样 `HEXTORAW`）。"""
    dialect = DMXADialect()
    recovered = DMXARecoveredXid("ab12", "cd34")
    commit_link = _FakeConnection()
    rollback_link = _FakeConnection()

    dialect.do_commit_twophase(commit_link, recovered, is_prepared=True, recover=True)
    dialect.do_rollback_twophase(rollback_link, recovered, is_prepared=True, recover=True)

    assert "XA_COMMIT" in commit_link.statements[0]
    assert "HEXTORAW('ab12')" in commit_link.statements[0]
    assert "HEXTORAW('cd34')" in commit_link.statements[0]
    assert "XA_ROLLBACK" in rollback_link.statements[0]
    assert "HEXTORAW('ab12')" in rollback_link.statements[0]


def test_recover_twophase_returns_empty_when_no_hung_branch() -> None:
    """无悬挂分支：返回空表（不报错）。"""
    assert list(DMXADialect().do_recover_twophase(_FakeConnection())) == []  # pyright: ignore[reportPrivateUsage]
