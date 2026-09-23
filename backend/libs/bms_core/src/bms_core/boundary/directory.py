"""表归属查询：以表归属登记（`services/table_registry.py`）为单一来源（06_03）。

- `table_owner` / `table_owners_map`：表名 → 归属服务（基础设施表返回 `*`；未登记返回 None）。
- `is_infrastructure`：每服务自有基础设施表（发件箱三表，不参与跨服务归属判定）。
- `owned_tables_for` / `known_tables` / `known_services` / `known_prefixes`：清单查询
  （静态校验、例外白名单校验与运行时守卫同源）。
- `table_prefix_of`：取表名前缀（例外匹配与文案用）。

口径：**不再有「共享前缀」概念**——`sys_` 表按表级归属判定；未登记表名无归属可判（声明场景由静态校验拦截）。
"""

from bms_core.services.module_registry import SERVICE_CATALOG
from bms_core.services.table_registry import (
    OWNER_EVERY_SERVICE,
    TABLE_OWNERSHIP,
    TableRecord,
    infrastructure_tables,
    known_service_keys,
    table_names,
    table_record,
)
from bms_core.services.table_registry import (
    owned_tables_for as _owned_tables_for,
)
from bms_core.services.table_registry import (
    table_owner as _table_owner,
)

__all__ = [
    "OWNER_EVERY_SERVICE",
    "is_infrastructure",
    "known_prefixes",
    "known_services",
    "known_tables",
    "owned_tables_for",
    "table_owner",
    "table_owners_map",
    "table_prefix_of",
    "table_record",
    "table_records",
]


def table_prefix_of(table: str) -> str:
    """取表名前缀（首个 `_` 前段 + `_`；无 `_` 返回原表名）。

    Args:
        table: 表名。

    Returns:
        str: 表前缀（如 `sys_` / `pur_`；无下划线时返回原表名）。
    """
    return table.split("_", 1)[0] + "_" if "_" in table else table


def table_owner(table: str) -> str | None:
    """表名归属（未登记返回 None；基础设施表返回 `*`）。

    Args:
        table: 表名。

    Returns:
        str | None: 归属标签。
    """
    return _table_owner(table)


def table_owners_map() -> dict[str, str]:
    """表名 → 归属标签映射（单一来源快照）。

    Returns:
        dict[str, str]: 表名到归属标签。
    """
    return {record.table_name: record.owner for record in TABLE_OWNERSHIP}


def table_records() -> tuple[TableRecord, ...]:
    """归属登记记录快照。

    Returns:
        tuple[TableRecord, ...]: 归属记录。
    """
    return TABLE_OWNERSHIP


def is_infrastructure(table: str) -> bool:
    """是否基础设施表（每服务自有，不参与跨服务归属判定）。

    Args:
        table: 表名。

    Returns:
        bool: 基础设施表 True。
    """
    return table in infrastructure_tables()


def owned_tables_for(service: str, *, datasource: str | None = None, include_planned: bool = True) -> frozenset[str]:
    """某服务名下全部表（按归属标签匹配）。

    Args:
        service: 服务标识（`service_key` / 模块标识）。
        datasource: 库类别过滤；None 取全部。
        include_planned: 是否含预留归属（`planned`）。

    Returns:
        frozenset[str]: 该服务拥有的表名集合。
    """
    return _owned_tables_for(service, datasource=datasource, include_planned=include_planned)


def known_tables() -> frozenset[str]:
    """归属登记的全部表名。

    Returns:
        frozenset[str]: 已登记表名集合。
    """
    return table_names()


def known_prefixes() -> frozenset[str]:
    """可作为例外登记目标的表前缀集合（服务目录前缀 ∪ 归属登记表名前缀）。

    Returns:
        frozenset[str]: 前缀集合。
    """
    catalog_prefixes = {record.table_prefix for record in SERVICE_CATALOG}
    owned_prefixes = {table_prefix_of(record.table_name) for record in TABLE_OWNERSHIP}
    return frozenset(catalog_prefixes | owned_prefixes)


def known_services() -> frozenset[str]:
    """可作为归属 / 消费方的服务标识（服务目录标签 ∪ 预留服务标识）。

    Returns:
        frozenset[str]: 标识集合。
    """
    return known_service_keys()
