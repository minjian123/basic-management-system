"""种子统计探针用例（07B `02_03` §3.10）：分支内前后快照求差。

**Kiwi 编号**：本批新增用例暂不标 `kiwi_id`，统一归 `05_01` 回填。

**覆盖面**：`snapshot` 真实取数（SQLite）、`diff` 的 created / updated / skipped 三态、
未登记表跳过、非法快照兜底、`register_seed_probes` 的登记与无方法跳过。
"""

from pathlib import Path
from typing import Any, cast

import pytest
from sqlalchemy import Table, create_engine, text

from bms_core.core.concurrent import (
    ConcurrentStableDict,
    ConcurrentStableFrozenDict,
    ConcurrentStableFrozenList,
    ConcurrentStableList,
)
from bms_core.services.module_registry import SeedRecord
from bms_core.tenant.seed.probe import (
    SeedStatsProbe,
    TableSnapshot,
    _as_snapshot,  # pyright: ignore[reportPrivateUsage]
    register_seed_probes,
)


def _probe(
    table: str, *, keys: ConcurrentStableList[str], values: ConcurrentStableList[str] | None = None
) -> SeedStatsProbe:
    """构造只含一张表的探针（用例夹具）。

    Args:
        table: 真实表名。
        keys: 自然键列。
        values: 值列。

    Returns:
        SeedStatsProbe: 探针。
    """
    from bms_core.tenant.seed.probe import _TableSpec  # pyright: ignore[reportPrivateUsage]

    return SeedStatsProbe(
        ConcurrentStableList(
            [
                _TableSpec(  # pyright: ignore[reportPrivateUsage]
                    table=table,
                    key_columns=ConcurrentStableFrozenList(keys),
                    value_columns=ConcurrentStableFrozenList(values or ConcurrentStableList()),
                )
            ]
        )
    )


# ---- diff 三态 ----


def test_diff_counts_created_updated_skipped() -> None:
    """`diff`：新增 / 变更 / 未变分别计入 created / updated / skipped。"""
    probe = _probe("t", keys=ConcurrentStableList(["code"]), values=ConcurrentStableList(["name"]))
    before: TableSnapshot = ConcurrentStableFrozenDict(
        {"t": ConcurrentStableFrozenDict({"a": ("旧",), "b": ("同名",)})}
    )
    after: TableSnapshot = ConcurrentStableFrozenDict(
        {"t": ConcurrentStableFrozenDict({"a": ("新",), "b": ("同名",), "c": ("新增",)})}
    )
    stats = probe.diff(before, after)
    assert (stats.created, stats.updated, stats.skipped) == (1, 1, 1)


def test_diff_ignores_tables_absent_in_before() -> None:
    """执行前不含该表（表刚建好）：全部计为新建。"""
    probe = _probe("t", keys=ConcurrentStableList(["code"]))
    after: TableSnapshot = ConcurrentStableFrozenDict({"t": ConcurrentStableFrozenDict({"a": (), "b": ()})})
    assert probe.diff(cast("Any", ConcurrentStableFrozenDict()), after).created == 2  # pyright: ignore


def test_diff_tolerates_invalid_snapshots() -> None:
    """非法 / 空快照按空处理（不抛错）。"""
    probe = _probe("t", keys=ConcurrentStableList(["code"]))
    assert probe.diff(None, None).created == 0
    assert probe.diff("bad", 123).created == 0


def test_as_snapshot_normalizes_inputs() -> None:  # pyright: ignore[reportPrivateUsage]
    """`_as_snapshot`：冻结映射与可变映射均规整为可变映射；其他值给空映射。"""
    frozen: TableSnapshot = ConcurrentStableFrozenDict({"t": ConcurrentStableFrozenDict({"a": ()})})
    assert list(_as_snapshot(frozen)) == ["t"]  # pyright: ignore[reportPrivateUsage]
    mutable: ConcurrentStableDict[str, ConcurrentStableFrozenDict[str, object]] = ConcurrentStableDict()
    mutable.set("x", ConcurrentStableFrozenDict())
    assert list(_as_snapshot(mutable)) == ["x"]  # pyright: ignore[reportPrivateUsage]
    assert list(_as_snapshot(object())) == []  # pyright: ignore[reportPrivateUsage]


# ---- snapshot 真实取数 ----


def test_snapshot_reads_real_table(tmp_path: Path) -> None:
    """`snapshot` 在真实 SQLite 连接上按自然键 / 值列取快照。"""
    from bms_core.models.base import Base
    from bms_core.models.platform.permission_meta import SysBusiness

    url = f"sqlite:///{tmp_path / 'probe.db'}"
    engine = create_engine(url)
    try:
        Base.metadata.create_all(engine, tables=[cast("Table", SysBusiness.__table__)])
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO sys_business (form_key, code, name, status, id, created_at, updated_at, version) "
                    "VALUES ('business', 'mdm', '主数据', 'enabled', 1, '2026-01-01', '2026-01-01', 1)"
                )
            )
        probe = _probe("sys_business", keys=ConcurrentStableList(["code"]), values=ConcurrentStableList(["name"]))
        with engine.connect() as connection:
            snapshot = probe.snapshot(connection)
        assert "sys_business" in snapshot
        assert snapshot["sys_business"]["mdm"] == ("主数据",)
    finally:
        engine.dispose()


def test_snapshot_skips_unregistered_table() -> None:
    """未登记表名被跳过（不抛错，快照里不含该表）。"""
    probe = _probe("no_such_table", keys=ConcurrentStableList(["id"]))
    assert dict(probe.snapshot(object())) == {}


# ---- 登记（声明驱动，07B `03_03`）----


def _record(name: str, **tables: str) -> SeedRecord:
    """构造只带统计声明的种子记录。

    Args:
        name: 种子名。
        **tables: 目标表声明（真实表名 = 自然键）。

    Returns:
        SeedRecord: 种子记录。
    """
    return SeedRecord(
        name=name,
        module="demo.seeds",
        entry="seed",
        service="platform",
        db_key="platform_platform",
        tables=ConcurrentStableFrozenDict(tables),
    )


def test_register_seed_probes_registers_declared_tables() -> None:
    """`register_seed_probes` 按传入记录登记（多表一条种子仍为一个探针）。"""
    registered: ConcurrentStableDict[str, Any] = ConcurrentStableDict()

    class _Participant:
        """参与方替身。"""

        def register_stats_probe(self, op: str, probe: Any) -> None:
            """记录探针。

            Args:
                op: 操作名。
                probe: 探针。
            """
            registered.set(op, probe)

    register_seed_probes(
        _Participant(),
        [
            _record("seed-module", sys_module="module_key", sys_product="product_key"),
            _record("seed-menu", sys_business="code"),
        ],
    )
    assert set(registered) == {"seed-module", "seed-menu"}
    assert len(registered["seed-module"]._tables) == 2  # pyright: ignore[reportPrivateUsage]


def test_register_seed_probes_skips_participant_without_method() -> None:
    """无 `register_stats_probe` 的参与方（占位实现）静默跳过。"""
    assert list(register_seed_probes(object(), [_record("seed-menu", sys_business="code")])) == []


@pytest.mark.parametrize("table", ["sys_module", "sys_business", "sys_config"])
def test_registered_probe_has_target_tables(table: str) -> None:
    """登记的探针带目标表口径（可对真实库取快照）。"""
    registered: ConcurrentStableDict[str, Any] = ConcurrentStableDict()

    class _Participant:
        """参与方替身。"""

        def register_stats_probe(self, name: str, probe: Any) -> None:
            """记录探针。

            Args:
                name: 操作名。
                probe: 探针。
            """
            registered.set(name, probe)

    register_seed_probes(_Participant(), [_record("seed-x", **{table: "id"})])
    probe = registered["seed-x"]
    assert isinstance(probe, SeedStatsProbe)
    assert probe._tables  # pyright: ignore[reportPrivateUsage]
