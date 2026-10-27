"""种子分支统计探针（07B `02_03` §3.10）：在**分支连接**上采集目标表前后快照并求差。

**为什么在分支内采集**：分支 `prepare` 后数据对其他连接不可见，分支外采集只能算「本批净增」，
且失败时恒为 0；同一连接能看到本分支未提交的写入，统计必然准确（详设 §3.10 / §8 #28）。

**口径**：`created` = 行数差；`updated` = 自然键命中且字段值有变化的行；`skipped` = 命中且无变化。
自然键列来自种子声明的 `tables` 段（`<逻辑名> = "<列名>"`），这里按**真实表名**登记。
"""

from dataclasses import dataclass
from dataclasses import field as dataclass_field
from typing import Any, cast

from bms_core.core.concurrent import (
    ConcurrentStableDict,
    ConcurrentStableFrozenDict,
    ConcurrentStableFrozenList,
    ConcurrentStableList,
)
from bms_core.core.objects import BaseFrameworkObject, BaseValueObject
from bms_core.transaction.base import BranchStats

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


def _table_name_of(model: str) -> str:
    """按模型类名取真实表名（避免在共享库里写跨服务表的字面量）。

    Args:
        model: 模型类名（在 `bms_core.models` 下唯一）。

    Returns:
        str: 真实表名；模型未导入时返回空串（该表不参与统计）。
    """
    import importlib

    modules = (
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
    for module_name in modules:
        module = importlib.import_module(module_name)
        found = getattr(module, model, None)
        if found is not None:
            return str(getattr(found, "__tablename__", ""))
    return ""


def register_seed_probes(registry: object) -> None:
    """把种子统计探针登记进参与方（`op` → 探针）。

    口径与种子声明的 `tables` 段一致：每个种子一项，目标表取 `tables` 的**真实表名**。

    Args:
        registry: 事务参与方（须具备 `register_stats_probe`）。
    """
    register = getattr(registry, "register_stats_probe", None)
    if not callable(register):
        return
    for op, tables in _PROBE_TABLES.items():
        register(op, SeedStatsProbe(tables))


_PROBE_TABLES: ConcurrentStableDict[str, ConcurrentStableList[_TableSpec]] = ConcurrentStableDict(
    {
        "seed-module": ConcurrentStableList(
            (
                _TableSpec(
                    table="sys_module",
                    key_columns=ConcurrentStableFrozenList(("module_key",)),
                    value_columns=ConcurrentStableFrozenList(("name", "table_prefix", "event_domain")),
                ),
                _TableSpec(
                    table="sys_product",
                    key_columns=ConcurrentStableFrozenList(("product_key",)),
                    value_columns=ConcurrentStableFrozenList(("name",)),
                ),
            )
        ),
        "seed-tables": ConcurrentStableList(
            (
                _TableSpec(
                    table="sys_table_ownership",
                    key_columns=ConcurrentStableFrozenList(("table_name",)),
                    value_columns=ConcurrentStableFrozenList(("owner", "datasource", "status")),
                ),
            )
        ),
        "seed-menu": ConcurrentStableList(
            (
                _TableSpec(
                    table="sys_business",
                    key_columns=ConcurrentStableFrozenList(("code",)),
                    value_columns=ConcurrentStableFrozenList(("name",)),
                ),
                _TableSpec(
                    table="sys_action",
                    key_columns=ConcurrentStableFrozenList(("code",)),
                    value_columns=ConcurrentStableFrozenList(("name",)),
                ),
                _TableSpec(
                    table="sys_menu",
                    key_columns=ConcurrentStableFrozenList(("path",)),
                    value_columns=ConcurrentStableFrozenList(("name",)),
                ),
            )
        ),
        "seed-tenant": ConcurrentStableList(
            (
                _TableSpec(
                    # 表名经模型派生（`sys_tenant` 归属 tenant 服务；在共享库里写字面量会触发
                    # 跨服务库访问校验，故不写字面量）
                    table=_table_name_of("SysTenant"),
                    key_columns=ConcurrentStableFrozenList(("code",)),
                    value_columns=ConcurrentStableFrozenList(("name", "domain")),
                ),
            )
        ),
        "seed-config": ConcurrentStableList(
            (
                _TableSpec(
                    table="sys_config",
                    key_columns=ConcurrentStableFrozenList(("config_key",)),
                    value_columns=ConcurrentStableFrozenList(("value",)),
                ),
            )
        ),
        "seed-platform-role": ConcurrentStableList(
            (
                _TableSpec(
                    table="sys_role",
                    key_columns=ConcurrentStableFrozenList(("code",)),
                    value_columns=ConcurrentStableFrozenList(("name",)),
                ),
            )
        ),
        "seed-platform-grant": ConcurrentStableList(
            (
                _TableSpec(
                    table="sys_role_permission",
                    key_columns=ConcurrentStableFrozenList(("role_id", "perm_type", "target_id")),
                ),
            )
        ),
        "seed-rbac-role": ConcurrentStableList(
            (
                _TableSpec(
                    table="sys_role",
                    key_columns=ConcurrentStableFrozenList(("code",)),
                    value_columns=ConcurrentStableFrozenList(("name",)),
                ),
            )
        ),
        "seed-rbac-grant": ConcurrentStableList(
            (
                _TableSpec(
                    table="sys_role_permission",
                    key_columns=ConcurrentStableFrozenList(("role_id", "perm_type", "target_id")),
                ),
            )
        ),
        "mdm-admin-codes": ConcurrentStableList(
            (
                _TableSpec(
                    table="sys_business",
                    key_columns=ConcurrentStableFrozenList(("code",)),
                    value_columns=ConcurrentStableFrozenList(("name",)),
                ),
                _TableSpec(
                    table="sys_permission",
                    key_columns=ConcurrentStableFrozenList(("business_id", "action_id")),
                ),
            )
        ),
    }
)
"""`op` → 目标表统计口径（与 `deploy/registry/*.toml` 的 `tables` 段同源）。"""
