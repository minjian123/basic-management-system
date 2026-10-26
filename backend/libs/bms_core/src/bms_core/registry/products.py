"""产品登记清单（**产品仓自持 + 装载时注册**）。

口径（2026-10-23 拍板）：产品（如 mdm）的服务行 / 产品路由 / 数据源条目**不再写进基座常量**，
改由产品仓自持清单 `deploy/registry/<product_key>.json` 声明，基座读入后注册进运行期视图。
**机制与选项集注册同构**（`bms_core/optionset/base.py`）：装载时注册、运行期只读、不落库、
同键同值合并 / 同键异值即拒（产品不得覆盖基座）：

- **运行期**：产品服务装配时经应用工厂钩子注入本产品记录（与 `form_records()` 同口径）；
- **离线**：网关配置生成（`ops.gateway_config`）按 `[registry].product_manifests` 装载后合并；
- **缺省降级**：未配置清单 / 文件不存在时为空清单（平台路由照常生成），不静默使用旧值。

清单结构（键缺省为空列表）：

```json
{
  "product_key": "mdm",
  "products": [{"product_key": "mdm", "name": "主数据管理", "status": "enabled"}],
  "services": [{"module_key": "mdm", "service_key": "mdm", "name": "mdm 主数据服务",
                "table_prefix": "mdm_", "event_domain": "mdm", "errcode_segment": "33",
                "service_group": "product", "build_batch": 3, "product_key": "mdm",
                "service_version": "0.1.0", "contract_version": "0.1.0", "status": "enabled"}],
  "product_routes": [{"product_key": "mdm", "domain": "mdm", "service_key": "mdm", "description": ""}],
  "data_sources": [{"data_source_key": "mdm_dept", "name": "部门", "kind": "dict",
                    "data_source": "mdm.mdm.dept", "origin": "product", "product_key": "mdm",
                    "path": "/data-source/dept-tree", "allowlist": ["code", "label"],
                    "cascade": true, "strategies": ["select", "region", "match"], "status": "enabled"}]
}
```
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableFrozenList, ConcurrentStableList
from bms_core.core.exceptions import CatalogError
from bms_core.core.objects import BaseValueObject
from bms_core.core.paths import resolve_backend_root
from bms_core.datasource.registry import DataSourceRecord, register_data_source_records
from bms_core.services.module_registry import (
    ModuleRecord,
    ProductRecord,
    ProductRouteRecord,
    register_product_records,
    register_product_routes,
    register_service_records,
)

__all__ = [
    "ProductManifest",
    "load_product_manifest",
    "load_product_manifests",
    "register_manifest",
]

_MANIFEST_BASE = resolve_backend_root("alembic.ini", anchor=Path(__file__))
"""清单相对路径的解析基准（**后端工程根**，与 `[registry].product_manifests` 注释及
`ops.gateway_config` 的解析口径一致；不随进程工作目录变化）。"""

_SERVICE_STRING_FIELDS: ConcurrentStableFrozenList[str] = ConcurrentStableFrozenList(
    ("module_key", "name", "table_prefix", "event_domain")
)
_DATA_SOURCE_STRING_FIELDS: ConcurrentStableFrozenList[str] = ConcurrentStableFrozenList(
    ("data_source_key", "name", "data_source")
)


@dataclass(frozen=True)
class ProductManifest(BaseValueObject):
    """产品登记清单（三类记录 + 产品档案）。

    Attributes:
        product_key: 清单归属产品标识（文件中所有记录须与之一致）。
        products: 产品档案记录。
        services: 服务目录记录（产品服务行）。
        product_routes: 产品级路由映射记录。
        data_sources: 数据源登记记录。
    """

    product_key: str
    products: ConcurrentStableFrozenList[ProductRecord] = field(
        default_factory=lambda: ConcurrentStableFrozenList[ProductRecord]()
    )
    services: ConcurrentStableFrozenList[ModuleRecord] = field(
        default_factory=lambda: ConcurrentStableFrozenList[ModuleRecord]()
    )
    product_routes: ConcurrentStableFrozenList[ProductRouteRecord] = field(
        default_factory=lambda: ConcurrentStableFrozenList[ProductRouteRecord]()
    )
    data_sources: ConcurrentStableFrozenList[DataSourceRecord] = field(
        default_factory=lambda: ConcurrentStableFrozenList[DataSourceRecord]()
    )


def _as_mapping(value: object) -> ConcurrentStableDict[str, object]:
    """把 JSON 对象规整为基座键值映射（非对象即拒）。

    Args:
        value: 原始值。

    Returns:
        ConcurrentStableDict[str, object]: 键值映射。

    Raises:
        CatalogError: 非对象结构。
    """
    if not isinstance(value, Mapping):
        raise CatalogError("产品清单结构非法（记录须为对象）")
    source = cast("Mapping[object, object]", value)
    return ConcurrentStableDict((str(key), item) for key, item in source.items())


def _require(mapping: object, key: str, *, scope: str) -> object:
    """取必填字段。

    Args:
        mapping: 记录映射。
        key: 字段名。
        scope: 错误信息作用域（文件 / 记录标识）。

    Returns:
        object: 字段值。

    Raises:
        CatalogError: 字段缺失。
    """
    data = _as_mapping(mapping)
    if key not in data or data[key] in (None, ""):
        raise CatalogError(f"产品清单缺少必填字段：{scope} → {key}")
    return data[key]


def _strings(value: object) -> ConcurrentStableFrozenList[str]:
    """把 JSON 数组规整为字符串冻结列表（非数组视为空）。

    Args:
        value: 原始值。

    Returns:
        ConcurrentStableFrozenList[str]: 字符串序列。
    """
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return ConcurrentStableFrozenList()
    return ConcurrentStableFrozenList(str(item) for item in cast("Sequence[object]", value))


def _service_record(raw: object, *, product_key: str, scope: str) -> ModuleRecord:
    """构造服务目录记录。

    Args:
        raw: 原始映射。
        product_key: 清单归属产品。
        scope: 错误信息作用域。

    Returns:
        ModuleRecord: 服务登记记录。
    """
    data = _as_mapping(raw)
    for name in _SERVICE_STRING_FIELDS:
        _require(data, name, scope=scope)
    record = ModuleRecord(
        module_key=str(data["module_key"]),
        service_key=str(data["service_key"]) if data.get("service_key") else None,
        name=str(data["name"]),
        table_prefix=str(data["table_prefix"]),
        business_code=str(data["business_code"]) if data.get("business_code") else None,
        errcode_segment=str(data["errcode_segment"]) if data.get("errcode_segment") else None,
        event_domain=str(data["event_domain"]),
        service_group=str(data.get("service_group") or "product"),
        build_batch=int(cast("int", data.get("build_batch") or 0)),
        service_version=str(data.get("service_version") or "0.1.0"),
        contract_version=str(data.get("contract_version") or "0.1.0"),
        product_key=str(data.get("product_key") or product_key),
        status=str(data.get("status") or "enabled"),
    )
    if record.product_key != product_key:
        raise CatalogError(f"产品清单服务行产品归属不符：{scope} → {record.product_key!r}（应为 {product_key!r}）")
    return record


def _data_source_record(raw: object, *, product_key: str, scope: str) -> DataSourceRecord:
    """构造数据源登记记录。

    Args:
        raw: 原始映射。
        product_key: 清单归属产品。
        scope: 错误信息作用域。

    Returns:
        DataSourceRecord: 数据源登记记录。
    """
    data = _as_mapping(raw)
    for name in _DATA_SOURCE_STRING_FIELDS:
        _require(data, name, scope=scope)
    record = DataSourceRecord(
        data_source_key=str(data["data_source_key"]),
        name=str(data["name"]),
        data_source=str(data["data_source"]),
        kind=str(data.get("kind") or "dict"),
        origin=str(data.get("origin") or "product"),
        product_key=str(data.get("product_key") or product_key),
        path=str(data["path"]) if data.get("path") else None,
        allowlist=_strings(data.get("allowlist")),
        cascade=bool(data.get("cascade") or False),
        strategies=_strings(data.get("strategies")) or ConcurrentStableFrozenList(("select",)),
        status=str(data.get("status") or "enabled"),
    )
    if record.product_key != product_key:
        raise CatalogError(f"产品清单数据源产品归属不符：{scope} → {record.product_key!r}（应为 {product_key!r}）")
    return record


def _records(raw: object, *, scope: str) -> ConcurrentStableList[object]:
    """把 JSON 数组规整为对象序列（非数组 / 元素非对象即拒）。

    Args:
        raw: 原始值。
        scope: 错误信息作用域。

    Returns:
        ConcurrentStableList[object]: 记录映射。

    Raises:
        CatalogError: 结构非法。
    """
    if raw is None:
        return ConcurrentStableList()
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        raise CatalogError(f"产品清单结构非法（{scope} 须为数组）")
    items: ConcurrentStableList[object] = ConcurrentStableList()
    for item in cast("Sequence[object]", raw):
        items.add(_as_mapping(item))
    return items


def load_product_manifest(path: Path) -> ProductManifest:
    """读取并解析单个产品登记清单。

    Args:
        path: 清单文件路径。

    Returns:
        ProductManifest: 解析结果（已做产品归属与必填字段校验）。

    Raises:
        CatalogError: 文件不可读、JSON 非法或字段不合法。
    """
    try:
        payload: object = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise CatalogError(f"产品清单不可读：{path}（{exc}）") from exc
    except json.JSONDecodeError as exc:
        raise CatalogError(f"产品清单 JSON 非法：{path}（{exc}）") from exc
    root = _as_mapping(payload)
    product_key = str(_require(root, "product_key", scope=str(path)))

    products: ConcurrentStableList[ProductRecord] = ConcurrentStableList()
    for raw in _records(root.get("products"), scope="products"):
        data = _as_mapping(raw)
        key = str(_require(data, "product_key", scope="products"))
        if key != product_key:
            raise CatalogError(f"产品清单产品档案归属不符：{key!r}（应为 {product_key!r}）")
        products.add(
            ProductRecord(
                product_key=key,
                name=str(_require(data, "name", scope="products")),
                frontend_package_source=str(data["frontend_package_source"])
                if data.get("frontend_package_source")
                else None,
                status=str(data.get("status") or "enabled"),
            )
        )

    services: ConcurrentStableList[ModuleRecord] = ConcurrentStableList(
        _service_record(raw, product_key=product_key, scope="services")
        for raw in _records(root.get("services"), scope="services")
    )
    routes: ConcurrentStableList[ProductRouteRecord] = ConcurrentStableList()
    for raw in _records(root.get("product_routes"), scope="product_routes"):
        data = _as_mapping(raw)
        route_product = str(_require(data, "product_key", scope="product_routes"))
        if route_product != product_key:
            raise CatalogError(f"产品清单路由归属不符：{route_product!r}（应为 {product_key!r}）")
        routes.add(
            ProductRouteRecord(
                product_key=route_product,
                domain=str(_require(data, "domain", scope="product_routes")),
                service_key=str(_require(data, "service_key", scope="product_routes")),
                description=str(data.get("description") or ""),
            )
        )
    data_sources: ConcurrentStableList[DataSourceRecord] = ConcurrentStableList(
        _data_source_record(raw, product_key=product_key, scope="data_sources")
        for raw in _records(root.get("data_sources"), scope="data_sources")
    )
    return ProductManifest(
        product_key=product_key,
        products=ConcurrentStableFrozenList(products),
        services=ConcurrentStableFrozenList(services),
        product_routes=ConcurrentStableFrozenList(routes),
        data_sources=ConcurrentStableFrozenList(data_sources),
    )


def register_manifest(manifest: ProductManifest) -> None:
    """把清单记录注册进基座运行期视图（四类；幂等、同键异值即拒）。

    Args:
        manifest: 产品登记清单。
    """
    register_product_records(manifest.products)
    register_service_records(manifest.services)
    register_product_routes(manifest.product_routes)
    register_data_source_records(manifest.data_sources)


def _resolve_manifest_path(raw: str | Path) -> Path:
    """把清单路径规整为绝对路径（相对路径按**后端工程根**解析）。

    Args:
        raw: 配置里的清单路径（绝对或相对）。

    Returns:
        Path: 绝对路径（不校验存在性）。
    """
    path = Path(raw)
    return path if path.is_absolute() else _MANIFEST_BASE / path


def load_product_manifests(paths: Iterable[str | Path]) -> ConcurrentStableList[ProductManifest]:
    """按配置路径批量装载并注册产品清单（缺省空清单；不存在的路径跳过）。

    Args:
        paths: 清单文件路径序列（相对路径按**后端工程根** `backend/` 解析，不随工作目录变化）。

    Returns:
        ConcurrentStableList[ProductManifest]: 已装载清单（插入序）。
    """
    manifests: ConcurrentStableList[ProductManifest] = ConcurrentStableList()
    for raw_path in paths:
        path = _resolve_manifest_path(raw_path)
        if not path.is_file():
            continue
        manifest = load_product_manifest(path)
        register_manifest(manifest)
        manifests.add(manifest)
    return manifests
