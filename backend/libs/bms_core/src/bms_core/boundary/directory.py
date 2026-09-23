"""表前缀归属：以服务目录 `SERVICE_CATALOG` 为单一来源（仅标准库 + 服务目录，供精简 CI 与运行时同源复用）。

- `SHARED_TABLE_PREFIXES`：平台域共享前缀（内建例外，任何实现服务可读，不判跨服务越界）。
- `table_prefix_of`：取表名前缀（首个 `_` 前段 + `_`；无 `_` 返回原表名）。
- `prefix_owner_map` / `prefix_owner`：前缀 → 归属（`service_key` 优先，缺省回落 `module_key`）。
- `owned_prefixes_for`：某服务名下全部前缀。
- `known_prefixes` / `known_services`：服务目录登记前缀 / 服务标识集合（例外白名单校验用）。
"""

from bms_core.services.module_registry import SERVICE_CATALOG, ModuleRecord

__all__ = [
    "SHARED_TABLE_PREFIXES",
    "is_shared_prefix",
    "known_prefixes",
    "known_services",
    "owned_prefixes_for",
    "prefix_owner",
    "prefix_owner_map",
    "table_prefix_of",
]

SHARED_TABLE_PREFIXES: tuple[str, ...] = ("sys_",)
"""平台域共享前缀：平台元数据表（`sys_*`）由各实现服务共享读取，不判跨服务越界（沿用规则 5 口径）。"""


def table_prefix_of(table: str) -> str:
    """取表名前缀（首个 `_` 前段 + `_`；无 `_` 返回原表名）。

    Args:
        table: 表名。

    Returns:
        str: 表前缀（如 `sys_` / `pur_`；无下划线时返回原表名）。
    """
    return table.split("_", 1)[0] + "_" if "_" in table else table


def _owner_label(record: ModuleRecord) -> str:
    """登记行归属标签（`service_key` 优先，缺省回落 `module_key`）。

    Args:
        record: 服务目录登记行。

    Returns:
        str: 归属标签。
    """
    return record.service_key or record.module_key


def prefix_owner_map() -> dict[str, str]:
    """前缀 → 归属标签（服务目录单一来源）。

    Returns:
        dict[str, str]: 前缀到归属（`service_key` 优先，缺省 `module_key`）。
    """
    return {record.table_prefix: _owner_label(record) for record in SERVICE_CATALOG}


def prefix_owner(prefix: str) -> str | None:
    """前缀归属标签（未登记前缀返回 None）。

    Args:
        prefix: 表前缀。

    Returns:
        str | None: 归属标签；未登记返回 None。
    """
    return prefix_owner_map().get(prefix)


def owned_prefixes_for(service: str) -> frozenset[str]:
    """某服务名下全部前缀（按归属标签匹配）。

    Args:
        service: 服务标识（`service_key` / 模块标识）。

    Returns:
        frozenset[str]: 该服务拥有的表前缀集合。
    """
    return frozenset(record.table_prefix for record in SERVICE_CATALOG if _owner_label(record) == service)


def is_shared_prefix(prefix: str) -> bool:
    """是否为平台域共享前缀（`sys_` 等）。

    Args:
        prefix: 表前缀。

    Returns:
        bool: 共享前缀返回 True。
    """
    return prefix in SHARED_TABLE_PREFIXES


def known_prefixes() -> frozenset[str]:
    """服务目录登记的全部表前缀。

    Returns:
        frozenset[str]: 已登记前缀集合。
    """
    return frozenset(record.table_prefix for record in SERVICE_CATALOG)


def known_services() -> frozenset[str]:
    """服务目录登记的服务标识（`service_key` 非空者）与模块标识并集。

    Returns:
        frozenset[str]: 可作为归属标签的标识集合。
    """
    return frozenset(_owner_label(record) for record in SERVICE_CATALOG)
