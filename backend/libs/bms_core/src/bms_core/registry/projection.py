"""注册表投影（07B `02_06`）：把**注册表快照**整体投影进进程内视图族。

投影采用「先复位、再登记」的整表重建而不是逐条增量，原因是声明会**演进**（同键换内容）与**退役**：

- 逐条增量在内容变化时会被「同键异值即拒」拦下（视图层的安全口径，不能为了投影而放宽）；
- 整表重建让进程内视图始终等于「注册表里 status=enabled 的行」，不残留旧值与退役项。

调用时机：平台进程在每次注册落库后、产品进程在启动期拉到快照后（同一函数、同一结果）。

> 视图层仍是**只读权威副本**：谁都不直接改视图，只从注册表重建。
"""

from collections.abc import Iterable
from typing import cast

from bms_core.collaboration.usage import (
    CapabilityUsage,
    register_capability_usages,
    reset_capability_usages,
)
from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList, ConcurrentStableSet
from bms_core.datasource.registry import (
    DataSourceRecord,
    register_data_source_records,
    reset_data_source_records,
)
from bms_core.registry.declarations import RegistrySnapshot, declaration_key
from bms_core.services.module_registry import (
    PRODUCT_CATALOG,
    SEED_CATALOG,
    SERVICE_CATALOG,
    CollaborationRecord,
    ErrorCodeRecord,
    ModuleRecord,
    ProductRecord,
    ProductRouteRecord,
    SeedRecord,
    register_collaboration_records,
    register_error_code_records,
    register_product_records,
    register_product_routes,
    register_seed_records,
    register_service_records,
    reset_collaboration_records,
    reset_error_code_records,
    reset_product_records,
    reset_product_routes,
    reset_seed_records,
    reset_service_records,
)

__all__ = ["project_registry"]


def project_registry(view: RegistrySnapshot) -> None:
    """把注册表快照整体投影进进程内视图族（仅 `enabled` 记录）。

    Args:
        view: 注册表快照（八类记录 + 退役标记 + 声明方）。
    """
    reset_product_records()
    reset_service_records()
    reset_product_routes()
    reset_data_source_records()
    reset_collaboration_records()
    reset_seed_records()
    reset_error_code_records()
    reset_capability_usages()
    register_product_records(
        cast("Iterable[ProductRecord]", _without_constants(view, "products", _constant_product_keys()))
    )
    register_service_records(
        cast("Iterable[ModuleRecord]", _without_constants(view, "services", _constant_service_keys()))
    )
    register_product_routes(cast("Iterable[ProductRouteRecord]", _enabled(view, "product_routes")))
    register_data_source_records(cast("Iterable[DataSourceRecord]", _enabled(view, "data_sources")))
    register_collaboration_records(cast("Iterable[CollaborationRecord]", _enabled(view, "collaborations")))
    register_seed_records(cast("Iterable[SeedRecord]", _without_constants(view, "seeds", _constant_seed_names())))
    register_error_code_records(cast("Iterable[ErrorCodeRecord]", _enabled(view, "errcodes")))
    _project_usages(view)


def _constant_product_keys() -> ConcurrentStableSet[str]:
    """平台内建产品档案常量（`PRODUCT_CATALOG`）的产品键集合。

    Returns:
        ConcurrentStableSet[str]: 产品键集合（常量已承载，投影不重复登记）。
    """
    return ConcurrentStableSet(record.product_key for record in PRODUCT_CATALOG)


def _constant_service_keys() -> ConcurrentStableSet[str]:
    """平台自身服务行常量（`SERVICE_CATALOG`）的模块键集合。

    Returns:
        ConcurrentStableSet[str]: 模块键集合（这些行由代码常量承载，投影时不重复登记）。
    """
    return ConcurrentStableSet(record.module_key for record in SERVICE_CATALOG)


def _constant_seed_names() -> ConcurrentStableSet[str]:
    """平台自身种子常量（`SEED_CATALOG`）的种子名集合。

    Returns:
        ConcurrentStableSet[str]: 种子名集合（同上，代码常量优先）。
    """
    return ConcurrentStableSet(record.name for record in SEED_CATALOG)


def _without_constants(
    view: RegistrySnapshot, kind: str, constant_keys: ConcurrentStableSet[str]
) -> ConcurrentStableList[object]:
    """取某类未退役、且不由代码常量承载的记录。

    Args:
        view: 注册表快照。
        kind: 声明类别。
        constant_keys: 平台常量已承载的业务键。

    Returns:
        ConcurrentStableList[object]: 记录（插入序）。
    """
    return ConcurrentStableList(
        record for record in _enabled(view, kind) if declaration_key(kind, record) not in constant_keys
    )


def _enabled(view: RegistrySnapshot, kind: str) -> ConcurrentStableList[object]:
    """取某类「未退役」记录。

    Args:
        view: 注册表快照。
        kind: 声明类别。

    Returns:
        ConcurrentStableList[object]: 未退役记录（插入序）。
    """
    return ConcurrentStableList(
        record for record in view.of(kind) if not view.is_retired(kind, declaration_key(kind, record))
    )


def _project_usages(view: RegistrySnapshot) -> None:
    """按声明方分组投影使用声明（声明方即消费方，键取 `owners`）。

    Args:
        view: 注册表快照。
    """
    grouped: ConcurrentStableDict[str, ConcurrentStableList[CapabilityUsage]] = ConcurrentStableDict()
    for record in _enabled(view, "usages"):
        usage = record if isinstance(record, CapabilityUsage) else None
        if usage is None:
            continue
        owner = view.owner_of("usages", usage.name) or ""
        if not owner:
            continue
        if owner not in grouped:
            grouped.set(owner, ConcurrentStableList())
        cast("ConcurrentStableList[CapabilityUsage]", grouped.get(owner)).add(usage)
    for declarer, usages in grouped.items():
        # 消费者视图（`capability_usage_view()`）是「声明方 → 声明列表」的登记位；
        # 注册表是权威来源，这里按声明方覆盖登记（退役项已在 `_enabled` 过滤）
        register_capability_usages(declarer, usages)
