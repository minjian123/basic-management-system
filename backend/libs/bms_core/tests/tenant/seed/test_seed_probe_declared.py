"""种子统计探针「声明驱动」用例（07B `03_03` §3.4）：目标表取声明、值列自动派生。

**Kiwi 编号**：`2364`（07B `03_03`）；既有 2254 为 `03_03` 改造对象。

**覆盖面**：声明 → 表口径映射（真实表名 / 多列自然键）、值列自动派生（排除主键 / 自然键 / 系统列）、
未知表名警示不阻断、无声明种子不登记、按本次记录登记（不再读平台侧硬编码表）。
"""

from typing import Any

import pytest

from bms_core.core.concurrent import (
    ConcurrentStableDict,
    ConcurrentStableFrozenDict,
    ConcurrentStableList,
)
from bms_core.services.module_registry import SeedRecord
from bms_core.tenant.seed.probe import SeedStatsProbe, register_seed_probes


class _Participant:
    """事务参与方替身（记录登记结果）。"""

    def __init__(self) -> None:
        """初始化登记表。"""
        self.registered: ConcurrentStableDict[str, Any] = ConcurrentStableDict()

    def register_stats_probe(self, op: str, probe: Any) -> None:
        """记录探针。

        Args:
            op: 操作名。
            probe: 探针。
        """
        self.registered.set(op, probe)


def _record(name: str, *, op: str = "", **tables: str) -> SeedRecord:
    """构造种子记录（只填统计相关字段）。

    Args:
        name: 种子名。
        **tables: 目标表声明（真实表名 = 自然键）。
        op: 分支操作名（空表示取 `name`）。

    Returns:
        SeedRecord: 种子记录。
    """
    return SeedRecord(
        name=name,
        module="demo.seeds",
        entry="seed",
        service="platform",
        db_key="platform_platform",
        op=op,
        tables=ConcurrentStableFrozenDict(tables),
    )


def _specs(record: SeedRecord) -> tuple[SeedStatsProbe, ConcurrentStableList[str]]:
    """登记单个种子并取探针与警示。

    Args:
        record: 种子记录。

    Returns:
        tuple[SeedStatsProbe, ConcurrentStableList[str]]: 探针与警示。
    """
    participant = _Participant()
    warnings = register_seed_probes(participant, [record])
    return participant.registered[record.op or record.name], warnings


@pytest.mark.kiwi_id(2364)
def test_value_columns_derived_from_table_shape() -> None:
    """值列自动派生：排除主键 / 自然键 / 系统列，其余业务列参与「是否更新」判定。"""
    probe, warnings = _specs(_record("seed-menu", sys_business="code"))
    spec = probe._tables[0]  # pyright: ignore[reportPrivateUsage]
    assert spec.table == "sys_business"
    assert list(spec.key_columns) == ["code"]
    assert "name" in spec.value_columns
    assert "status" in spec.value_columns
    for excluded in ("id", "code", "tenant_id", "created_at", "updated_at", "deleted_at", "created_by", "version"):
        assert excluded not in spec.value_columns
    assert list(warnings) == []


@pytest.mark.kiwi_id(2364)
def test_multi_column_natural_key() -> None:
    """多列自然键按声明拆分（组合键命中判定）。"""
    probe, _ = _specs(_record("seed-platform-grant", sys_role_permission="role_id,perm_type,target_id"))
    spec = probe._tables[0]  # pyright: ignore[reportPrivateUsage]
    assert list(spec.key_columns) == ["role_id", "perm_type", "target_id"]
    assert "role_id" not in spec.value_columns


@pytest.mark.kiwi_id(2364)
def test_unknown_table_warns_without_blocking() -> None:
    """未知表名：记警示并跳过该表，不登记空探针（不阻断编排）。"""
    participant = _Participant()
    warnings = register_seed_probes(participant, [_record("seed-x", no_such_table="id")])
    assert len(warnings) == 1
    assert "no_such_table" in warnings[0] and "seed-x" in warnings[0]
    assert dict(participant.registered) == {}


@pytest.mark.kiwi_id(2364)
def test_record_without_tables_not_registered() -> None:
    """未声明 `tables` 的种子不登记探针（报告按无口径处理）。"""
    participant = _Participant()
    warnings = register_seed_probes(participant, [_record("seed-plain")])
    assert dict(participant.registered) == {}
    assert list(warnings) == []


@pytest.mark.kiwi_id(2364)
def test_registration_follows_records_and_ops() -> None:
    """只登记传入的记录，键取 `op`（缺省取种子名）。"""
    participant = _Participant()
    records = [
        _record("seed-menu", sys_business="code"),
        _record("demo-admin-codes", sys_business="code", op="demo-codes"),
    ]
    register_seed_probes(participant, records)
    assert set(participant.registered) == {"seed-menu", "demo-codes"}
    assert isinstance(participant.registered["demo-codes"], SeedStatsProbe)


@pytest.mark.kiwi_id(2364)
def test_participant_without_probe_support_is_skipped() -> None:
    """无 `register_stats_probe` 的参与方（占位实现）静默跳过且无警示。"""
    assert list(register_seed_probes(object(), [_record("seed-menu", sys_business="code")])) == []
