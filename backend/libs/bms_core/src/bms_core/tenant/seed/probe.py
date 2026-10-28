"""种子分支统计探针（07B `02_03` §3.10）：在**分支连接**上采集目标表前后快照并求差。

**为什么在分支内采集**：分支 `prepare` 后数据对其他连接不可见，分支外采集只能算「本批净增」，
且失败时恒为 0；同一连接能看到本分支未提交的写入，统计必然准确（详设 §3.10 / §8 #28）。

**口径**：`created` = 行数差；`updated` = 自然键命中且字段值有变化的行；`skipped` = 命中且无变化。

**目标表来源（07B `03_03`）**：取种子声明的 `tables` 段（**真实表名 → 自然键**），不再维护平台侧
硬编码映射；值列（判定「是否更新」的列）由表结构**自动派生**——排除主键列、自然键列与系统列。
"""

from collections.abc import Iterable
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from typing import TYPE_CHECKING, Any, cast

from bms_core.core.concurrent import (
    ConcurrentStableDict,
    ConcurrentStableFrozenDict,
    ConcurrentStableFrozenList,
    ConcurrentStableFrozenSet,
    ConcurrentStableList,
)
from bms_core.core.objects import BaseFrameworkObject, BaseValueObject
from bms_core.transaction.base import BranchStats

if TYPE_CHECKING:
    from bms_core.services.module_registry import SeedRecord

__all__ = ["SeedStatsProbe", "TableSnapshot", "register_seed_probes"]

TableSnapshot = ConcurrentStableFrozenDict[str, ConcurrentStableFrozenDict[str, object]]
"""目标表快照类型：表名 → （自然键文本 → 值列元组）。"""


def _as_snapshot(value: object) -> ConcurrentStableDict[str, ConcurrentStableFrozenDict[str, object]]:
    """把不透明快照规整为可变映射（`diff` 内部用；非法输入按空快照处理）。

    Args:
        value: 快照对象（`snapshot` 的返回值，或任意输入）。

    Returns:
        ConcurrentStableDict[str, ConcurrentStableFrozenDict[str, object]]: 表名 → 行映射。
    """
    if isinstance(value, ConcurrentStableFrozenDict | ConcurrentStableDict):
        return ConcurrentStableDict(cast("dict[str, ConcurrentStableFrozenDict[str, object]]", value))
    return ConcurrentStableDict()


@dataclass(frozen=True)
class _TableSpec(BaseValueObject):
    """单个目标表的统计口径。"""

    table: str
    """真实表名。"""

    key_columns: ConcurrentStableFrozenList[str]
    """自然键列（多列即组合键）。"""

    value_columns: ConcurrentStableFrozenList[str] = dataclass_field(
        default_factory=lambda: ConcurrentStableFrozenList()
    )
    """参与「是否更新」判定的值列（空表示只按行数统计）。"""


class SeedStatsProbe(BaseFrameworkObject):
    """种子分支统计探针（`op` → 目标表集合）。"""

    def __init__(self, tables: ConcurrentStableList[_TableSpec]) -> None:
        """初始化。

        Args:
            tables: 目标表统计口径清单。
        """
        self._tables = tables

    def snapshot(self, connection: Any) -> TableSnapshot:
        """取目标表快照（**同步**；由执行器经 `asyncio.to_thread` 在分支连接上调用）。

        Args:
            connection: 分支连接（同步 SQLAlchemy 连接）。

        Returns:
            TableSnapshot: 表名 → （自然键文本 → 值列元组）。
        """
        from sqlalchemy import select

        from bms_core.models.base import Base

        result: ConcurrentStableDict[str, ConcurrentStableFrozenDict[str, object]] = ConcurrentStableDict()
        for spec in self._tables:
            table = Base.metadata.tables.get(spec.table)
            if table is None:
                continue
            rows: ConcurrentStableDict[str, object] = ConcurrentStableDict()
            for row in connection.execute(select(table)).all():
                mapping: Any = row._mapping
                key = "|".join(str(mapping[column]) for column in spec.key_columns if column in mapping)
                values: ConcurrentStableFrozenList[object] = ConcurrentStableFrozenList(
                    mapping[column] for column in spec.value_columns if column in mapping
                )
                rows.set(key, values)
            result.set(spec.table, ConcurrentStableFrozenDict(rows))
        return ConcurrentStableFrozenDict(result)

    def diff(self, before: object, after: object) -> BranchStats:
        """比对前后快照得出逐项统计。

        Args:
            before: 执行前快照。
            after: 执行后快照。

        Returns:
            BranchStats: 逐项统计。
        """
        before_map = _as_snapshot(before)
        after_map = _as_snapshot(after)
        created = 0
        updated = 0
        skipped = 0
        for table, after_rows in after_map.items():
            before_rows = before_map.get(table) or ConcurrentStableFrozenDict[str, object]()
            for key, values in after_rows.items():
                previous = before_rows.get(key)
                if previous is None:
                    created += 1
                    continue
                if previous == values:
                    skipped += 1
                else:
                    updated += 1
        return BranchStats(created=created, updated=updated, skipped=skipped)


_MODEL_MODULES: ConcurrentStableFrozenList[str] = ConcurrentStableFrozenList(
    (
        "bms_core.models.tenant.tenant",
        "bms_core.models.tenant.tenant_database",
        "bms_core.models.platform.catalog",
        "bms_core.models.platform.menu_form",
        "bms_core.models.platform.permission_meta",
        "bms_core.models.platform.role",
        "bms_core.models.platform.user",
        "bms_core.models.ownership",
        "bms_core.config.models",
    )
)
"""目标表所在模型模块（导入后 `Base.metadata.tables` 可按真实表名查表）。"""

_SYSTEM_COLUMNS: ConcurrentStableFrozenSet[str] = ConcurrentStableFrozenSet(
    ("tenant_id", "created_at", "updated_at", "deleted_at", "created_by", "updated_by", "version")
)
"""值列自动派生时排除的系统列（拓扑 / 审计 / 时间戳 / 并发版本，不参与「是否更新」判定）。"""


def _ensure_models() -> None:
    """导入已知模型模块，确保目标表进入 `Base.metadata`。"""
    import importlib

    for module_name in _MODEL_MODULES:
        importlib.import_module(module_name)


def _specs_for(record: SeedRecord, warnings: ConcurrentStableList[str]) -> ConcurrentStableList[_TableSpec]:
    """按种子声明的 `tables` 段生成该种子的表统计口径。

    Args:
        record: 种子登记记录（`tables` 为「真实表名 → 自然键」）。
        warnings: 警示收集器（未知表名记一条，不阻断）。

    Returns:
        ConcurrentStableList[_TableSpec]: 表统计口径（未知表跳过；无声明时为空）。
    """
    from bms_core.models.base import Base

    specs: ConcurrentStableList[_TableSpec] = ConcurrentStableList()
    for table_name, raw_keys in record.tables.items():
        table = Base.metadata.tables.get(table_name)
        if table is None:
            warnings.add(f"[种子] 目标表未在模型中登记，跳过统计：{record.name} → {table_name}")
            continue
        key_columns: ConcurrentStableFrozenList[str] = ConcurrentStableFrozenList(
            part.strip() for part in str(raw_keys).split(",") if part.strip()
        )
        value_columns: ConcurrentStableFrozenList[str] = ConcurrentStableFrozenList(
            column.name
            for column in table.columns
            if not column.primary_key and column.name not in key_columns and column.name not in _SYSTEM_COLUMNS
        )
        specs.add(_TableSpec(table=table_name, key_columns=key_columns, value_columns=value_columns))
    return specs


def register_seed_probes(registry: object, records: Iterable[SeedRecord]) -> ConcurrentStableList[str]:
    """按种子声明把统计探针登记进参与方（`op` → 探针）。

    **登记时机**：调用方须在**种子记录装载之后**、执行之前调用（本次实际执行的记录为准），
    否则产品种子尚未装载会漏登记（详设 §3.4.2）。

    Args:
        registry: 事务参与方（须具备 `register_stats_probe`；无此方法时静默跳过）。
        records: 本次编排选中的种子记录。

    Returns:
        ConcurrentStableList[str]: 警示（未知表名等；调用方并入编排报告，不阻断）。
    """
    warnings: ConcurrentStableList[str] = ConcurrentStableList()
    register = getattr(registry, "register_stats_probe", None)
    if not callable(register):
        return warnings
    _ensure_models()
    for record in records:
        specs = _specs_for(record, warnings)
        if not specs:
            continue
        register(record.op or record.name, SeedStatsProbe(specs))
    return warnings
