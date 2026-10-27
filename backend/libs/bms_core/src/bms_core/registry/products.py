"""产品登记清单（**产品仓自持 + 装载时注册**）。

口径（2026-10-23 拍板；2026-10-26 07B `02_01` 修订）：产品（如 mdm）的服务行 / 产品路由 / 数据源 /
能力 / 种子条目**不再写进基座常量**，改由产品仓自持清单 `deploy/registry/<product_key>.toml` 声明，
基座读入后注册进运行期视图。**机制与选项集注册同构**（`bms_core/optionset/base.py`）：装载时注册、
运行期只读、不落库、同键同值合并 / 同键异值即拒（产品不得覆盖基座）：

- **运行期**：产品服务装配时经应用工厂钩子注入本产品记录（与 `form_records()` 同口径）；
- **离线**：网关配置生成（`ops.gateway_config`）按 `[registry].product_manifests` 装载后合并；
- **缺省降级**：未配置清单 / 文件不存在时为空清单（平台路由照常生成），不静默使用旧值。

清单格式为 **toml**（直接切换，**不留 json 兼容分支**），七段并列（除 `product_key` 外均可缺省）：

```toml
product_key = "demo"

[[products]]          # 产品档案
[[services]]          # 服务行
[[product_routes]]    # 产品级路由
[[data_sources]]      # 数据源
[[collaborations]]    # 能力（第五类记录）
[[seeds]]             # 默认数据种子（第六类记录）
[[errcodes]]          # 错误码（第七类记录，07B `02_05`）
```

**装载期七类校验**（载体 `inspect_product_manifests()`，任一不满足即拒启）：能力重名 / 提供方业务域
未登记 / 归属不符 / 访问面不在对端契约 / 契约版本不兼容 / 种子入口不可解析 / 错误码段位与撞码；
另有 `kind` 要素匹配、`branch_id` 长度与业务域一致性、`default_consumers` 登记、错误码契约反向
对账（两档）等补充校验。校验实现唯一——装配期（`load_product_manifests()`）与离线门禁
（`ops.check_modules`）复用同一函数，不新增并行校验入口。
"""

from __future__ import annotations

import importlib
import json
import os
import re
import tomllib
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import cast

from bms_core.collaboration.usage import DEGRADE_MODES, DEGRADE_NONE, CapabilityUsage
from bms_core.core.concurrent import (
    ConcurrentStableDict,
    ConcurrentStableFrozenDict,
    ConcurrentStableFrozenList,
    ConcurrentStableFrozenSet,
    ConcurrentStableList,
    ConcurrentStableSet,
)
from bms_core.core.error_codes import ErrorCode
from bms_core.core.exceptions import CatalogError
from bms_core.core.logging import get_logger
from bms_core.core.objects import BaseValueObject
from bms_core.core.paths import resolve_backend_root
from bms_core.core.version import CONTRACT_VERSION_RE, contract_major
from bms_core.datasource.registry import DataSourceRecord, register_data_source_records
from bms_core.services.module_registry import (
    PRODUCT_CATALOG,
    SERVICE_CATALOG,
    CollaborationKind,
    CollaborationRecord,
    CollaborationStatus,
    ErrorCodeRecord,
    ModuleRecord,
    ProductRecord,
    ProductRouteRecord,
    SeedRecord,
    normalize_capability_path,
    register_collaboration_records,
    register_domain_services,
    register_error_code_records,
    register_product_records,
    register_product_routes,
    register_seed_records,
    register_service_records,
)
from bms_core.transaction.base import MAX_BRANCH_ID_LENGTH

__all__ = [
    "SKIP_CONTRACT_ENV",
    "ManifestInspection",
    "ProductManifest",
    "inspect_product_manifests",
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
_ERROR_CODE_DOMAIN_RE = re.compile(r"^[a-z][a-z0-9_]*$")
"""错误码业务域形态（仅形态校验，不要求域布局登记，07B `02_05` 拍板）。"""
_ERROR_CODE_SEVERITIES: ConcurrentStableFrozenSet[str] = ConcurrentStableFrozenSet(("info", "warning", "error"))
"""错误码严重级别取值（本期仅登记与导出）。"""
_ERROR_CODE_STATUSES: ConcurrentStableFrozenSet[str] = ConcurrentStableFrozenSet(("enabled", "disabled"))
"""错误码状态取值（`disabled` 仅影响手册口径，渲染仍参与）。"""
_ERROR_CODE_HTTP_RANGE = (100, 599)
"""传输层状态允许区间（含端点）。"""
CONTRACT_ERROR_CODES_KEY = "x-error-codes"
"""契约扩展键：端点可能返回的错误码（整数数组，operation 级；07B `02_05`）。"""

CONTRACTS_DIR_NAME = "contracts"
"""研发仓契约目录名（`deploy/contracts/<product_key>.json`）。"""

REGISTRY_DIR_NAME = "registry"
"""研发仓清单目录名（`deploy/registry/<product_key>.toml`）。"""

DOMAIN_LAYOUT_RELATIVE = Path("boundaries/domain_layout.json")
"""域布局相对 `deploy/` 的路径（域基准来源，与 07C 域布局同口径）。"""

SKIP_CONTRACT_ENV = "BMS_REGISTRY__SKIP_CONTRACT_CHECK"
"""显式跳过「访问面 ↔ 对端契约」定位校验的开关（非空且非 `0/false/no` 即跳过并警示）。"""

_FALSY_ENV = ConcurrentStableFrozenSet(("", "0", "false", "no", "off"))


@dataclass(frozen=True)
class ProductManifest(BaseValueObject):
    """产品登记清单（六类记录 + 产品档案）。

    Attributes:
        product_key: 清单归属产品标识（文件中所有记录须与之一致）。
        products: 产品档案记录。
        services: 服务目录记录（产品服务行）。
        product_routes: 产品级路由映射记录。
        data_sources: 数据源登记记录。
        collaborations: 能力记录（第五类）。
        seeds: 默认数据种子记录（第六类）。
        error_codes: 错误码记录（第七类；`product_key` / `segment` 装载期注入）。
    """

    product_key: str
    products: ConcurrentStableFrozenList[ProductRecord] = field(default_factory=lambda: ConcurrentStableFrozenList())
    services: ConcurrentStableFrozenList[ModuleRecord] = field(default_factory=lambda: ConcurrentStableFrozenList())
    product_routes: ConcurrentStableFrozenList[ProductRouteRecord] = field(
        default_factory=lambda: ConcurrentStableFrozenList()
    )
    data_sources: ConcurrentStableFrozenList[DataSourceRecord] = field(
        default_factory=lambda: ConcurrentStableFrozenList()
    )
    collaborations: ConcurrentStableFrozenList[CollaborationRecord] = field(
        default_factory=lambda: ConcurrentStableFrozenList()
    )
    seeds: ConcurrentStableFrozenList[SeedRecord] = field(default_factory=lambda: ConcurrentStableFrozenList())
    error_codes: ConcurrentStableFrozenList[ErrorCodeRecord] = field(
        default_factory=lambda: ConcurrentStableFrozenList()
    )
    usages: ConcurrentStableFrozenList[CapabilityUsage] = field(default_factory=lambda: ConcurrentStableFrozenList())
    """消费方使用声明（第八类记录；声明方即消费方，07B `02_06` 起为注册输入的一段）。"""


@dataclass(frozen=True)
class ManifestInspection(BaseValueObject):
    """清单装载检查结果（离线门禁与装配期共用；不注册、不抛错）。

    Attributes:
        manifests: 解析成功的清单（插入序）。
        sources: 与 `manifests` 逐一对应的清单绝对路径。
        errors: 阻断性问题（拒启 / 门禁失败）。
        warnings: 跳过项与降级提示（不得静默，须输出）。
        domain_services: 业务域 → 承载服务键（域布局派生，供能力寻址第二段）。
    """

    manifests: ConcurrentStableFrozenList[ProductManifest] = field(default_factory=lambda: ConcurrentStableFrozenList())
    sources: ConcurrentStableFrozenList[Path] = field(default_factory=lambda: ConcurrentStableFrozenList())
    errors: ConcurrentStableFrozenList[str] = field(default_factory=lambda: ConcurrentStableFrozenList())
    warnings: ConcurrentStableFrozenList[str] = field(default_factory=lambda: ConcurrentStableFrozenList())
    domain_services: ConcurrentStableFrozenDict[str, str] = field(
        default_factory=lambda: ConcurrentStableFrozenDict[str, str]()
    )


def _as_mapping(value: object) -> ConcurrentStableDict[str, object]:
    """把清单对象规整为基座键值映射（非对象即拒）。

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


def _strings(value: object, *, scope: str, key: str) -> ConcurrentStableFrozenList[str]:
    """把字符串数组规整为冻结列表（非数组视为空；**数组内含非字符串即拒**）。

    Args:
        value: 原始值。
        scope: 错误信息作用域。
        key: 字段名。

    Returns:
        ConcurrentStableFrozenList[str]: 字符串序列。

    Raises:
        CatalogError: 数组内含非字符串项（`02_01` 类型收紧：不静默转换）。
    """
    if value is None:
        return ConcurrentStableFrozenList()
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return ConcurrentStableFrozenList()
    items: ConcurrentStableList[str] = ConcurrentStableList()
    for item in cast("Sequence[object]", value):
        if not isinstance(item, str):
            raise CatalogError(f"产品清单结构非法：{scope} → {key} 须为字符串数组（含 {type(item).__name__}）")
        items.add(item)
    return ConcurrentStableFrozenList(items)


def _int_value(data: object, key: str, *, scope: str) -> int:
    """取整数字段（缺省 0；非整数即拒，`bool` 不算整数）。

    Args:
        data: 记录映射。
        key: 字段名。
        scope: 错误信息作用域。

    Returns:
        int: 字段值。

    Raises:
        CatalogError: 非整数（toml / json 类型差异不再静默转换）。
    """
    value = _as_mapping(data).get(key)
    if value is None:
        return 0
    if isinstance(value, bool) or not isinstance(value, int):
        raise CatalogError(f"产品清单结构非法：{scope} → {key} 须为整数（现 {type(value).__name__}）")
    return value


def _bool_value(data: object, key: str, *, scope: str) -> bool:
    """取布尔字段（缺省 False；非布尔即拒）。

    Args:
        data: 记录映射。
        key: 字段名。
        scope: 错误信息作用域。

    Returns:
        bool: 字段值。

    Raises:
        CatalogError: 非布尔。
    """
    value = _as_mapping(data).get(key)
    if value is None:
        return False
    if not isinstance(value, bool):
        raise CatalogError(f"产品清单结构非法：{scope} → {key} 须为布尔（现 {type(value).__name__}）")
    return value


def _optional_str(data: object, key: str) -> str | None:
    """取可选字符串字段（空串与缺省同义）。

    Args:
        data: 记录映射。
        key: 字段名。

    Returns:
        str | None: 字段值；未声明返回 None。
    """
    value = _as_mapping(data).get(key)
    return str(value) if value else None


def _service_record(raw: object, *, product_key: str, scope: str) -> ModuleRecord:
    """构造服务目录记录。

    Args:
        raw: 原始映射。
        product_key: 清单归属产品。
        scope: 错误信息作用域。

    Returns:
        ModuleRecord: 服务登记记录。

    Raises:
        CatalogError: 必填缺失 / 类型非法 / 产品归属不符。
    """
    data = _as_mapping(raw)
    for name in _SERVICE_STRING_FIELDS:
        _require(data, name, scope=scope)
    record = ModuleRecord(
        module_key=str(data["module_key"]),
        service_key=_optional_str(data, "service_key"),
        name=str(data["name"]),
        table_prefix=str(data["table_prefix"]),
        business_code=_optional_str(data, "business_code"),
        errcode_segment=_optional_str(data, "errcode_segment"),
        event_domain=str(data["event_domain"]),
        service_group=str(data.get("service_group") or "product"),
        build_batch=_int_value(data, "build_batch", scope=scope),
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

    Raises:
        CatalogError: 必填缺失 / 类型非法 / 产品归属不符。
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
        path=_optional_str(data, "path"),
        allowlist=_strings(data.get("allowlist"), scope=scope, key="allowlist"),
        cascade=_bool_value(data, "cascade", scope=scope),
        strategies=_strings(data.get("strategies"), scope=scope, key="strategies")
        or ConcurrentStableFrozenList(("select",)),
        status=str(data.get("status") or "enabled"),
    )
    if record.product_key != product_key:
        raise CatalogError(f"产品清单数据源产品归属不符：{scope} → {record.product_key!r}（应为 {product_key!r}）")
    return record


def _require_collaboration_elements(
    *,
    kind: str,
    path: str | None,
    branch_id: str | None,
    branch_op: str | None,
    data_source_key: str | None,
    permission_codes: ConcurrentStableFrozenList[str],
    status: str,
    replacement: str | None,
    scope: str,
) -> None:
    """校验访问面类别与业务语义要素的匹配（`kind` 条件必填）。

    Args:
        kind: 访问面类别。
        path: 访问面路径模板。
        branch_id: XA 分支标识。
        branch_op: 分支动作名。
        data_source_key: 关联数据源键。
        permission_codes: 业务码 / 权限码集合。
        status: 能力状态。
        replacement: 替代能力名。
        scope: 错误信息作用域。

    Raises:
        CatalogError: 要素与类别不匹配。
    """
    if kind == CollaborationKind.CODES:
        if not permission_codes:
            raise CatalogError(f"产品清单能力要素缺失：{scope} → codes 类须声明 permission_codes")
        if path is not None:
            raise CatalogError(f"产品清单能力要素冲突：{scope} → codes 类不得声明访问面 path")
    else:
        if path is None:
            raise CatalogError(f"产品清单能力要素缺失：{scope} → {kind} 类须声明访问面 path")
        if kind == CollaborationKind.TXN_BRANCH and branch_id is None:
            raise CatalogError(f"产品清单能力要素缺失：{scope} → txn-branch 类须声明 branch_id")
        if kind == CollaborationKind.TXN_BRANCH and branch_op is None:
            raise CatalogError(f"产品清单能力要素缺失：{scope} → txn-branch 类须声明 branch_op")
        if kind == CollaborationKind.DATASET and data_source_key is None:
            raise CatalogError(f"产品清单能力要素缺失：{scope} → dataset 类须声明 data_source_key")
    if status == CollaborationStatus.DEPRECATED and replacement is None:
        raise CatalogError(f"产品清单能力要素缺失：{scope} → deprecated 状态须声明 replacement")


def _collaboration_record(raw: object, *, product_key: str, scope: str) -> CollaborationRecord:
    """构造能力登记记录（第五类记录）。

    Args:
        raw: 原始映射。
        product_key: 清单归属产品。
        scope: 错误信息作用域。

    Returns:
        CollaborationRecord: 能力登记记录。

    Raises:
        CatalogError: 必填缺失 / 类别与要素不匹配 / 归属不符 / branch_id 超长。
    """
    data = _as_mapping(raw)
    name = str(_require(data, "name", scope=scope))
    record_scope = f"{scope}｜能力 {name}"
    domain = str(_require(data, "domain", scope=record_scope))
    kind = str(_require(data, "kind", scope=record_scope))
    if kind not in tuple(CollaborationKind):
        raise CatalogError(f"产品清单结构非法：{record_scope} → kind 非法（{kind}）")
    contract_version = str(_require(data, "contract_version", scope=record_scope))
    if not CONTRACT_VERSION_RE.fullmatch(contract_version):
        raise CatalogError(f"产品清单结构非法：{record_scope} → contract_version 非 semver（{contract_version}）")
    owner = str(data.get("product_key") or product_key)
    if owner != product_key:
        raise CatalogError(f"产品清单能力产品归属不符：{record_scope} → {owner!r}（应为 {product_key!r}）")
    status = str(data.get("status") or CollaborationStatus.ENABLED)
    if status not in tuple(CollaborationStatus):
        raise CatalogError(f"产品清单结构非法：{record_scope} → status 非法（{status}）")
    branch_id = _optional_str(data, "branch_id")
    if branch_id is not None and len(branch_id) > MAX_BRANCH_ID_LENGTH:
        raise CatalogError(
            f"产品清单结构非法：{record_scope} → branch_id 超过 {MAX_BRANCH_ID_LENGTH} 字符（{branch_id}）"
        )
    path = _optional_str(data, "path")
    branch_op = _optional_str(data, "branch_op")
    data_source_key = _optional_str(data, "data_source_key")
    permission_codes = _strings(data.get("permission_codes"), scope=record_scope, key="permission_codes")
    replacement = _optional_str(data, "replacement")
    _require_collaboration_elements(
        kind=kind,
        path=path,
        branch_id=branch_id,
        branch_op=branch_op,
        data_source_key=data_source_key,
        permission_codes=permission_codes,
        status=status,
        replacement=replacement,
        scope=record_scope,
    )
    return CollaborationRecord(
        name=name,
        domain=domain,
        kind=kind,
        contract_version=contract_version,
        path=path,
        product_key=owner,
        branch_id=branch_id,
        branch_op=branch_op,
        data_source_key=data_source_key,
        permission_codes=permission_codes,
        frontend_prefix=_optional_str(data, "frontend_prefix"),
        default_consumers=_strings(data.get("default_consumers"), scope=record_scope, key="default_consumers"),
        status=status,
        replacement=replacement,
    )


def _fill_frontend_prefix(
    records: ConcurrentStableList[CollaborationRecord], routes: ConcurrentStableList[ProductRouteRecord]
) -> ConcurrentStableList[CollaborationRecord]:
    """装载期补齐前端命名空间域段（清单未声明时按本清单**唯一**的路由域段填实）。

    推导规则与装载校验同源（`_validate_manifest_entries`「路由域段须唯一」）：路由域段不唯一时不补齐
    （保留 None），由校验报「前端命名空间不可推导」；`codes` 类无前端面，不补齐。

    Args:
        records: 能力记录（插入序）。
        routes: 本清单的产品路由记录。

    Returns:
        ConcurrentStableList[CollaborationRecord]: 补齐后的记录（插入序）。
    """
    domains = ConcurrentStableSet(route.domain for route in routes)
    if len(domains) != 1:
        return records
    prefix = next(iter(domains))
    filled: ConcurrentStableList[CollaborationRecord] = ConcurrentStableList()
    for record in records:
        needs_fill = record.frontend_prefix is None and record.kind != CollaborationKind.CODES
        filled.add(replace(record, frontend_prefix=prefix) if needs_fill else record)
    return filled


def _seed_record(raw: object, *, scope: str, product_key: str = "") -> SeedRecord:
    """构造种子登记记录（第六类记录）。

    Args:
        raw: 原始映射。
        scope: 错误信息作用域。
        product_key: 该清单归属的产品键（**注入为 `source`**，声明文件不写本字段）。

    Returns:
        SeedRecord: 种子登记记录。

    Raises:
        CatalogError: 必填缺失 / 状态非法。
    """
    data = _as_mapping(raw)
    name = str(_require(data, "name", scope=scope))
    record_scope = f"{scope}｜种子 {name}"
    module = str(_require(data, "module", scope=record_scope))
    entry = str(_require(data, "entry", scope=record_scope))
    status = str(data.get("status") or CollaborationStatus.ENABLED)
    if status not in tuple(CollaborationStatus):
        raise CatalogError(f"产品清单结构非法：{record_scope} → status 非法（{status}）")
    return SeedRecord(
        name=name,
        module=module,
        entry=entry,
        service=str(data.get("service") or ""),
        db_key=str(data.get("db_key") or ""),
        op=str(data.get("op") or name),
        tables=_seed_tables(data.get("tables"), scope=record_scope),
        after=_strings(data.get("after"), scope=record_scope, key="after"),
        description=str(data.get("description") or ""),
        status=status,
        source=product_key,
    )


def _seed_tables(raw: object, *, scope: str) -> ConcurrentStableFrozenDict[str, str]:
    """解析种子目标表声明（`[seeds.tables]` 段：表名 → 自然键）。

    Args:
        raw: 原始映射（可为 None，表示未声明）。
        scope: 错误信息作用域。

    Returns:
        ConcurrentStableFrozenDict[str, str]: 表名 → 自然键。

    Raises:
        CatalogError: 结构非法（非映射 / 值非字符串）。
    """
    if raw is None:
        return ConcurrentStableFrozenDict()
    data = _as_mapping(raw)
    result: ConcurrentStableDict[str, str] = ConcurrentStableDict()
    for table, key in data.items():
        if not isinstance(key, str) or not key:
            raise CatalogError(f"产品清单结构非法：{scope} → tables 项须为「表名: 自然键」字符串对（{table!r}）")
        result.set(table, key)
    return ConcurrentStableFrozenDict(result)


def _manifest_segment(services: ConcurrentStableList[ModuleRecord], *, product_key: str) -> str | None:
    """取本清单服务行声明的错误码段位（唯一非空段；多段视为非法）。

    Args:
        services: 本清单服务行。
        product_key: 清单归属产品（错误定位用）。

    Returns:
        str | None: 段位；服务行均未声明返回 None。

    Raises:
        CatalogError: 多个不同段位无法确定错误码归属段。
    """
    segments = {service.errcode_segment for service in services if service.errcode_segment}
    if len(segments) > 1:
        raise CatalogError(
            f"产品清单 {product_key}：声明 `[[errcodes]]` 时服务行段位须唯一（现 {'、'.join(sorted(segments))}）"
        )
    return next(iter(segments), None)


def _error_code_record(raw: object, *, product_key: str, segment: str, scope: str) -> ErrorCodeRecord:
    """构造错误码登记记录（第七类记录；结构级校验，跨清单校验见 `_validate_error_codes`）。

    Args:
        raw: 原始映射。
        product_key: 清单归属产品（注入为提供方）。
        segment: 本清单服务行段位（注入）。
        scope: 错误信息作用域。

    Returns:
        ErrorCodeRecord: 错误码登记记录。

    Raises:
        CatalogError: 必填缺失 / 类型非法 / 形态非法 / 码位形态不符。
    """
    data = _as_mapping(raw)
    raw_code = _require(data, "code", scope=scope)
    if isinstance(raw_code, bool) or not isinstance(raw_code, int):
        raise CatalogError(f"产品清单结构非法：{scope} → code 须为整数（现 {type(raw_code).__name__}）")
    code = int(raw_code)
    record_scope = f"{scope}｜错误码 {code}"
    segment_text = str(code)
    if len(segment_text) != 6:
        raise CatalogError(f"{record_scope}：产品码须为 6 位（2 位段 + 4 位序号；5 位属平台码区，产品不得声明）")
    if segment_text[:2] != segment:
        raise CatalogError(f"{record_scope}：段位不符（码前两位 {segment_text[:2]}，声明段 {segment}）")
    domain = str(_require(data, "domain", scope=record_scope))
    if not _ERROR_CODE_DOMAIN_RE.match(domain):
        raise CatalogError(f"{record_scope}：domain 形态非法（{domain}；须为小写标识符）")
    raw_status = _require(data, "http_status", scope=record_scope)
    if isinstance(raw_status, bool) or not isinstance(raw_status, int):
        raise CatalogError(f"{record_scope}：http_status 须为整数（现 {type(raw_status).__name__}）")
    low, high = _ERROR_CODE_HTTP_RANGE
    if not low <= int(raw_status) <= high:
        raise CatalogError(f"{record_scope}：http_status 越界（{raw_status}；须在 {low}~{high}）")
    message_key = str(_require(data, "message_key", scope=record_scope))
    expected_prefix = f"{product_key}.error."
    if not message_key.startswith(expected_prefix) or not re.fullmatch(
        r"[a-z][a-z0-9_]*", message_key[len(expected_prefix) :]
    ):
        raise CatalogError(
            f"{record_scope}：message_key 须为 `<product>.error.<snake_case>`（{message_key}；产品段 {product_key}）"
        )
    severity = str(_require(data, "severity", scope=record_scope))
    if severity not in _ERROR_CODE_SEVERITIES:
        raise CatalogError(f"{record_scope}：severity 非法（{severity}；须为 info / warning / error）")
    status = str(data.get("status") or CollaborationStatus.ENABLED)
    if status not in _ERROR_CODE_STATUSES:
        raise CatalogError(f"{record_scope}：status 非法（{status}；须为 enabled / disabled）")
    return ErrorCodeRecord(
        code=code,
        domain=domain,
        http_status=int(raw_status),
        message_key=message_key,
        severity=severity,
        description=str(_require(data, "description", scope=record_scope)),
        product_key=product_key,
        segment=segment,
        status=status,
    )


def _records(raw: object, *, scope: str) -> ConcurrentStableList[object]:
    """把清单数组规整为对象序列（非数组 / 元素非对象即拒）。

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
    """读取并解析单个产品登记清单（**结构级校验**，不含跨清单 / 契约等外部校验）。

    Args:
        path: 清单文件路径（**只接受 `.toml`**）。

    Returns:
        ProductManifest: 解析结果（已做产品归属与必填字段校验）。

    Raises:
        CatalogError: 扩展名非 toml、文件不可读、TOML 非法或字段不合法。
    """
    if path.suffix != ".toml":
        raise CatalogError(f"产品清单须为 toml 自持声明：{path}（请改用 .toml，不再支持 json 兼容分支）")
    try:
        payload: object = tomllib.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise CatalogError(f"产品清单不可读：{path}（{exc}）") from exc
    except tomllib.TOMLDecodeError as exc:
        raise CatalogError(f"产品清单 TOML 非法：{path}（{exc}）") from exc
    return _build_manifest(_as_mapping(payload), path=path)


def parse_manifest_text(text: str, *, source: str = "<remote>") -> ProductManifest:
    """解析**清单文本**为产品声明（注册通道的输入解析，与文件装载同一实现）。

    Args:
        text: 清单 TOML 文本（产品启动上报时携带自身清单内容）。
        source: 来源标识（错误定位用）。

    Returns:
        ProductManifest: 清单记录（八段）。

    Raises:
        CatalogError: TOML 非法或结构不合法。
    """
    try:
        payload: object = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise CatalogError(f"产品清单 TOML 非法：{source}（{exc}）") from exc
    return _build_manifest(_as_mapping(payload), path=Path(source))


def _build_manifest(root: ConcurrentStableDict[str, object], *, path: Path) -> ProductManifest:
    """由已解析的清单映射构造产品声明（文件装载与文本解析共用）。

    Args:
        root: 清单映射。
        path: 来源路径（错误定位与契约定位用）。

    Returns:
        ProductManifest: 清单记录（八段）。

    Raises:
        CatalogError: 结构不合法。
    """
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
                frontend_package_source=_optional_str(data, "frontend_package_source"),
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
    collaborations: ConcurrentStableList[CollaborationRecord] = _fill_frontend_prefix(
        ConcurrentStableList(
            _collaboration_record(raw, product_key=product_key, scope="collaborations")
            for raw in _records(root.get("collaborations"), scope="collaborations")
        ),
        routes,
    )
    seeds: ConcurrentStableList[SeedRecord] = ConcurrentStableList(
        _seed_record(raw, scope="seeds", product_key=product_key) for raw in _records(root.get("seeds"), scope="seeds")
    )
    error_codes: ConcurrentStableList[ErrorCodeRecord] = _error_code_records(
        root.get("errcodes"), product_key=product_key, services=services, path=path
    )
    usages: ConcurrentStableList[CapabilityUsage] = ConcurrentStableList(
        _usage_record(raw, scope="usages") for raw in _records(root.get("usages"), scope="usages")
    )
    return ProductManifest(
        product_key=product_key,
        products=ConcurrentStableFrozenList(products),
        services=ConcurrentStableFrozenList(services),
        product_routes=ConcurrentStableFrozenList(routes),
        data_sources=ConcurrentStableFrozenList(data_sources),
        collaborations=ConcurrentStableFrozenList(collaborations),
        seeds=ConcurrentStableFrozenList(seeds),
        error_codes=ConcurrentStableFrozenList(error_codes),
        usages=ConcurrentStableFrozenList(usages),
    )


def _usage_record(raw: object, *, scope: str) -> CapabilityUsage:
    """构造消费方使用声明（第八类记录）。

    Args:
        raw: 原始映射。
        scope: 错误信息作用域。

    Returns:
        CapabilityUsage: 使用声明（`degrade` / `reason` 的可兑现性由注册校验判定）。

    Raises:
        CatalogError: 必填缺失或降级模式非法。
    """
    data = _as_mapping(raw)
    name = str(_require(data, "name", scope=scope))
    degrade = str(data.get("degrade") or DEGRADE_NONE)
    if degrade not in DEGRADE_MODES:
        raise CatalogError(
            f"产品清单结构非法：{scope}｜使用声明 {name} → degrade 非法（{degrade}；取值 {'/'.join(DEGRADE_MODES)}）"
        )
    return CapabilityUsage(name=name, degrade=degrade, reason=str(data.get("reason") or ""))


def _error_code_records(
    raw: object,
    *,
    product_key: str,
    services: ConcurrentStableList[ModuleRecord],
    path: Path,
) -> ConcurrentStableList[ErrorCodeRecord]:
    """解析 `[[errcodes]]` 段（段位取自本清单服务行；重复声明即拒）。

    Args:
        raw: `errcodes` 数组原值。
        product_key: 清单归属产品。
        services: 本清单服务行（段位来源）。
        path: 清单路径（错误定位用）。

    Returns:
        ConcurrentStableList[ErrorCodeRecord]: 错误码记录（插入序）。

    Raises:
        CatalogError: 有错误码但服务行无段位 / 同清单重复声明 / 字段非法。
    """
    entries = _records(raw, scope="errcodes")
    records: ConcurrentStableList[ErrorCodeRecord] = ConcurrentStableList()
    if not entries:
        return records
    segment = _manifest_segment(services, product_key=product_key)
    if segment is None:
        raise CatalogError(
            f"产品清单 {path}：声明 `[[errcodes]]` 时服务行须声明 `errcode_segment`（错误码段位取自服务行）"
        )
    seen: ConcurrentStableSet[int] = ConcurrentStableSet()
    for entry in entries:
        record = _error_code_record(entry, product_key=product_key, segment=segment, scope="errcodes")
        if record.code in seen:
            raise CatalogError(f"产品清单 {path}：错误码重复声明（{record.code}）")
        seen.add(record.code)
        records.add(record)
    return records


def _skip_contract_check() -> bool:
    """是否显式跳过「访问面 ↔ 对端契约」定位校验。

    Returns:
        bool: 环境变量非空且不在假值集合内为 True。
    """
    raw = os.environ.get(SKIP_CONTRACT_ENV, "").strip().lower()
    return raw not in _FALSY_ENV


def _contract_path(source: Path, product_key: str) -> Path | None:
    """定位对端公开契约文件（清单同仓优先，回退本仓后端工程根）。

    Args:
        source: 清单文件绝对路径（`<仓根>/deploy/registry/<产品>.toml`）。
        product_key: 清单归属产品标识（契约文件名取其 `<product_key>.json`）。

    Returns:
        Path | None: 契约文件路径；两处都不存在返回 None。
    """
    same_repo = source.parent.parent / CONTRACTS_DIR_NAME / f"{product_key}.json"
    if same_repo.is_file():
        return same_repo
    fallback = _MANIFEST_BASE.parent / "deploy" / CONTRACTS_DIR_NAME / f"{product_key}.json"
    return fallback if fallback.is_file() else None


def _contract_spec(
    path: Path,
) -> tuple[ConcurrentStableFrozenSet[str], ConcurrentStableFrozenDict[str, ConcurrentStableFrozenList[int]]]:
    """读取契约文件：归一化路径集合 + 端点声明的错误码（`x-error-codes`，operation 级）。

    Args:
        path: 契约文件路径。

    Returns:
        tuple: `(归一化路径集合, {归一化路径: 声明的错误码})`；未声明的路径不入映射。

    Raises:
        CatalogError: 契约不可读 / JSON 非法 / 错误码声明形态非法。
    """
    try:
        payload: object = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise CatalogError(f"对端契约不可读：{path}（{exc}）") from exc
    except json.JSONDecodeError as exc:
        raise CatalogError(f"对端契约 JSON 非法：{path}（{exc}）") from exc
    root = _as_mapping(payload)
    raw = root.get("paths")
    paths: ConcurrentStableSet[str] = ConcurrentStableSet()
    declared: ConcurrentStableDict[str, ConcurrentStableFrozenList[int]] = ConcurrentStableDict()
    if isinstance(raw, Mapping):
        for key, operations in cast("Mapping[object, object]", raw).items():
            normalized = normalize_capability_path(str(key))
            paths.add(normalized)
            codes = _declared_error_codes(operations, path=normalized)
            if codes:
                declared.set(normalized, codes)
    return ConcurrentStableFrozenSet(paths), ConcurrentStableFrozenDict(declared)


def _declared_error_codes(operations: object, *, path: str) -> ConcurrentStableFrozenList[int]:
    """取单个端点各方法声明的 `x-error-codes`（去重，插入序）。

    Args:
        operations: 契约 `paths.<path>` 下的方法映射。
        path: 归一化路径（错误定位用）。

    Returns:
        ConcurrentStableFrozenList[int]: 声明的错误码（空表示未声明）。

    Raises:
        CatalogError: 声明非整数数组（不静默转换）。
    """
    codes: ConcurrentStableList[int] = ConcurrentStableList()
    for method, operation in _as_mapping(operations).items():
        raw = _as_mapping(operation).get(CONTRACT_ERROR_CODES_KEY)
        if raw is None:
            continue
        if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
            raise CatalogError(
                f"对端契约错误码声明非法（{method.upper()} {path}：{CONTRACT_ERROR_CODES_KEY} 须为整数数组）"
            )
        for item in cast("Sequence[object]", raw):
            if isinstance(item, bool) or not isinstance(item, int):
                raise CatalogError(
                    f"对端契约错误码声明非法（{method.upper()} {path}：元素须为整数，现 {type(item).__name__}）"
                )
            if int(item) not in codes:
                codes.add(int(item))
    return ConcurrentStableFrozenList(codes)


def _layout_registry(path: Path, warnings: ConcurrentStableList[str]) -> ConcurrentStableDict[str, str]:
    """读取域布局文件的 `domain_key → service_key` 映射（不可读 / 非法即警示并返回空）。

    Args:
        path: 域布局文件路径。
        warnings: 警示收集器。

    Returns:
        ConcurrentStableDict[str, str]: `{domain: service_key}`（未声明承载服务时值为空串）。
    """
    registry: ConcurrentStableDict[str, str] = ConcurrentStableDict()
    try:
        payload: object = json.loads(path.read_text(encoding="utf-8"))
        root = _as_mapping(payload)
        raw = root.get("domains")
        if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
            warnings.add(f"[能力] 域布局结构非法（缺 domains 数组）：{path}")
            return registry
        for item in cast("Sequence[object]", raw):
            entry = _as_mapping(item)
            key = entry.get("domain_key")
            if not key:
                continue
            service = entry.get("service_key")
            registry.set(str(key), str(service) if service else "")
    except OSError as exc:
        warnings.add(f"[能力] 域布局不可读：{path}（{exc}）")
    except json.JSONDecodeError as exc:
        warnings.add(f"[能力] 域布局 JSON 非法：{path}（{exc}）")
    except CatalogError as exc:
        warnings.add(f"[能力] 域布局结构非法：{path}（{exc}）")
    return registry


def _layout_registry_map(
    sources: ConcurrentStableList[Path], warnings: ConcurrentStableList[str]
) -> ConcurrentStableDict[str, str]:
    """取域布局登记映射（本仓布局 ∪ 各清单同仓布局；同域取先出现的非空承载服务）。

    Args:
        sources: 清单文件绝对路径（插入序）。
        warnings: 警示收集器（两处都缺时记录，不得静默）。

    Returns:
        ConcurrentStableDict[str, str]: `{domain: service_key}`（未声明承载服务时值为空串）。
    """
    candidates: ConcurrentStableSet[Path] = ConcurrentStableSet()
    candidates.add(_MANIFEST_BASE.parent / "deploy" / DOMAIN_LAYOUT_RELATIVE)
    for source in sources:
        candidates.add(source.parent.parent / DOMAIN_LAYOUT_RELATIVE)
    merged: ConcurrentStableDict[str, str] = ConcurrentStableDict()
    found = False
    for path in candidates:
        if not path.is_file():
            continue
        found = True
        for domain, service in _layout_registry(path, warnings).items():
            if merged.get(domain):
                continue
            merged.set(domain, service)
    if not found:
        warnings.add("[能力] 域布局不可用：业务域只做标识形态校验（deploy/boundaries/domain_layout.json 缺失）")
    return merged


def _consumer_keys(manifests: ConcurrentStableList[ProductManifest]) -> ConcurrentStableSet[str]:
    """取可作默认消费方的标识集合（已登记服务键 + 产品键；前端应用不入此列）。

    Args:
        manifests: 本次装载的清单（插入序）。

    Returns:
        ConcurrentStableSet[str]: 服务键与产品键集合。
    """
    keys: ConcurrentStableSet[str] = ConcurrentStableSet()
    for module in SERVICE_CATALOG:
        if module.service_key:
            keys.add(module.service_key)
        if module.product_key:
            keys.add(module.product_key)
    for product in PRODUCT_CATALOG:
        keys.add(product.product_key)
    for manifest in manifests:
        keys.add(manifest.product_key)
        for product in manifest.products:
            keys.add(product.product_key)
        for service in manifest.services:
            if service.service_key:
                keys.add(service.service_key)
    return keys


def _check_seed_entry(
    record: SeedRecord, *, label: str, warnings: ConcurrentStableList[str]
) -> ConcurrentStableList[str]:
    """校验种子入口可解析（提供方包不可导入时跳过并警示）。

    Args:
        record: 种子记录。
        label: 清单标识（错误定位用）。
        warnings: 警示收集器。

    Returns:
        ConcurrentStableList[str]: 错误明细（空列表表示可解析或已跳过）。
    """
    errors: ConcurrentStableList[str] = ConcurrentStableList()
    top_level = record.module.split(".")[0]
    try:
        importlib.import_module(top_level)
    except ImportError:
        warnings.add(f"[种子] 跳过入口校验（{top_level} 不可导入）：{record.name} → {record.module}:{record.entry}")
        return errors
    try:
        module = importlib.import_module(record.module)
    except ImportError:
        errors.add(f"{label}｜种子 {record.name}：入口不可解析（{record.module}:{record.entry}）")
        return errors
    if not callable(getattr(module, record.entry, None)):
        errors.add(f"{label}｜种子 {record.name}：入口不可解析（{record.module}:{record.entry}）")
    return errors


def _check_seed_declaration(record: SeedRecord, *, manifest: ProductManifest, label: str) -> ConcurrentStableList[str]:
    """校验种子声明的新增字段（07B `02_03`）：`service` / `db_key` / 名称前缀。

    Args:
        record: 种子记录。
        manifest: 该种子所属清单（取 `product_key` 判定前缀）。
        label: 清单标识（错误定位用）。

    Returns:
        ConcurrentStableList[str]: 错误明细。
    """
    errors: ConcurrentStableList[str] = ConcurrentStableList()
    prefix = f"{label}｜种子 {record.name}"
    if not record.service:
        errors.add(f"{prefix}：缺少执行服务声明（service）")
    if not record.db_key:
        errors.add(f"{prefix}：缺少分支目标库声明（db_key）")
    elif not (record.db_key.startswith("platform_") or record.db_key.startswith("tenant_")):
        errors.add(f"{prefix}：db_key 形态非法（{record.db_key}；须以 platform_ / tenant_ 开头）")
    product_key = manifest.product_key
    if product_key and product_key != "platform" and not record.name.startswith(f"{product_key}-"):
        errors.add(f'{prefix}：产品种子名须以 "{product_key}-" 开头')
    return errors


def _validate_collaboration_names(
    manifests: ConcurrentStableList[ProductManifest], sources: ConcurrentStableList[Path]
) -> ConcurrentStableList[str]:
    """校验能力名全局唯一（同值合并放行、异值即拒）。

    Args:
        manifests: 本次装载的清单（插入序）。
        sources: 与 `manifests` 对应的清单路径。

    Returns:
        ConcurrentStableList[str]: 重名明细。
    """
    errors: ConcurrentStableList[str] = ConcurrentStableList()
    seen: ConcurrentStableDict[str, tuple[CollaborationRecord, Path]] = ConcurrentStableDict()
    for manifest, source in zip(manifests, sources, strict=True):
        for record in manifest.collaborations:
            existing = seen.get(record.name)
            if existing is None:
                seen.set(record.name, (record, source))
                continue
            other, other_source = existing
            if other != record:
                errors.add(f"产品清单能力重名：{record.name}（清单 {other_source} 与 {source}）")
    return errors


def _validate_manifest_entries(
    manifest: ProductManifest,
    source: Path,
    *,
    domain_keys: ConcurrentStableSet[str],
    domain_services: ConcurrentStableDict[str, str],
    consumer_keys: ConcurrentStableSet[str],
    branch_domains: ConcurrentStableDict[str, str],
    warnings: ConcurrentStableList[str],
) -> ConcurrentStableList[str]:
    """校验单份清单的能力 / 种子 / 错误码段（域 / 契约 / 版本 / 分支 / 消费方 / 入口 / 码段）。

    Args:
        manifest: 清单。
        source: 清单文件绝对路径。
        domain_keys: 域基准（空集表示不可用，只做形态校验）。
        domain_services: 业务域 → 承载服务键（空集表示域布局未提供该信息，跳过承载校验）。
        consumer_keys: 可作默认消费方的标识集合。
        branch_domains: 全局 `branch_id` → 业务域（跨清单一致性）。
        warnings: 警示收集器。

    Returns:
        ConcurrentStableList[str]: 错误明细。
    """
    errors: ConcurrentStableList[str] = ConcurrentStableList()
    label = str(source)
    route_domains = ConcurrentStableSet(route.domain for route in manifest.product_routes)
    service_versions = ConcurrentStableList(service.contract_version for service in manifest.services)
    service_majors: ConcurrentStableSet[int] = ConcurrentStableSet(
        major for version in service_versions if (major := contract_major(version)) is not None
    )
    contract_paths: ConcurrentStableFrozenSet[str] = ConcurrentStableFrozenSet()
    contract_error_codes: ConcurrentStableFrozenDict[str, ConcurrentStableFrozenList[int]] = (
        ConcurrentStableFrozenDict()
    )
    contract_ready = False
    if manifest.collaborations or manifest.error_codes:
        contract_path = _contract_path(source, manifest.product_key)
        if contract_path is None:
            if _skip_contract_check():
                warnings.add(f"[清单] 跳过契约定位（契约缺失且已显式跳过）：{label} → {manifest.product_key}.json")
            else:
                errors.add(
                    f"{label}｜清单：对端契约文件缺失"
                    f"（deploy/contracts/{manifest.product_key}.json；如属极简环境请设 {SKIP_CONTRACT_ENV}）"
                )
        else:
            try:
                contract_paths, contract_error_codes = _contract_spec(contract_path)
                contract_ready = True
            except CatalogError as exc:
                errors.add(str(exc))
    for record in manifest.collaborations:
        prefix = f"{label}｜能力 {record.name}"
        if domain_keys and record.domain not in domain_keys:
            errors.add(f"{prefix}：提供方业务域未登记（{record.domain}）")
        elif domain_services and not domain_services.get(record.domain):
            errors.add(
                f"{prefix}：提供方业务域未登记承载服务（{record.domain}；"
                "域布局须为该域声明 service_key，能力寻址第二段据此解析）"
            )
        if record.branch_id is not None:
            owner_domain = branch_domains.get(record.branch_id)
            if owner_domain is None:
                branch_domains.set(record.branch_id, record.domain)
            elif owner_domain != record.domain:
                errors.add(f"{prefix}：分支标识跨业务域混用（{record.branch_id} 已被 {owner_domain} 使用）")
        if contract_ready and record.kind != CollaborationKind.CODES and record.normalized_path() not in contract_paths:
            errors.add(f"{prefix}：访问面不在对端契约（{record.path}）")
        capability_major = contract_major(record.contract_version)
        if service_majors and (capability_major is None or capability_major not in service_majors):
            errors.add(
                f"{prefix}：契约版本不兼容（能力 {record.contract_version} / 服务 {', '.join(service_versions)}）"
            )
        if record.kind != CollaborationKind.CODES and record.frontend_prefix is None and len(route_domains) != 1:
            errors.add(
                f"{prefix}：前端命名空间不可推导"
                f"（清单 product_routes 域段须唯一，现 {len(route_domains)} 个；或显式声明 frontend_prefix）"
            )
        for consumer in record.default_consumers:
            if consumer not in consumer_keys:
                errors.add(f"{prefix}：默认消费方未登记（{consumer}）")
    for record in manifest.seeds:
        errors.update(_check_seed_entry(record, label=label, warnings=warnings))
        errors.update(_check_seed_declaration(record, manifest=manifest, label=label))
    if manifest.error_codes:
        errors.update(
            _check_contract_error_codes(
                manifest,
                label=label,
                contract_codes=contract_error_codes,
                contract_ready=contract_ready,
                contract_paths=contract_paths,
                warnings=warnings,
            )
        )
    return errors


def _check_contract_error_codes(
    manifest: ProductManifest,
    *,
    label: str,
    contract_codes: ConcurrentStableFrozenDict[str, ConcurrentStableFrozenList[int]],
    contract_ready: bool,
    contract_paths: ConcurrentStableFrozenSet[str],
    warnings: ConcurrentStableList[str],
) -> ConcurrentStableList[str]:
    """契约反向对账（两档）：已声明强校验，未声明端点只统计（软提示）。

    Args:
        manifest: 清单（含已登记错误码）。
        label: 清单标识（错误定位用）。
        contract_codes: 契约中声明的 `路径 → 错误码`。
        contract_ready: 契约是否可用（缺失 / 跳过时为 False，此时不重复报错）。
        contract_paths: 契约归一化路径集合。
        warnings: 警示收集器。

    Returns:
        ConcurrentStableList[str]: 错误明细（已声明但未登记）。
    """
    errors: ConcurrentStableList[str] = ConcurrentStableList()
    if not contract_ready:
        return errors
    registered = {record.code for record in manifest.error_codes}
    for path, codes in contract_codes.items():
        for code in codes:
            if code not in registered:
                errors.add(f"{label}｜错误码：契约声明的码未登记（{path} → {code}）")
    undeclared = sorted(path for path in contract_paths if path not in contract_codes)
    if undeclared:
        sample = "、".join(undeclared[:3])
        warnings.add(f"[错误码] {label}：{len(undeclared)} 个端点未声明 {CONTRACT_ERROR_CODES_KEY}（例：{sample}）")
    return errors


def _validate_error_codes(
    manifests: ConcurrentStableList[ProductManifest], sources: ConcurrentStableList[Path]
) -> ConcurrentStableList[str]:
    """跨清单校验错误码：与平台码撞码 / 跨产品撞码 / 段位跨产品复用。

    Args:
        manifests: 本次装载的清单（插入序）。
        sources: 与 `manifests` 对应的清单路径。

    Returns:
        ConcurrentStableList[str]: 冲突明细。
    """
    errors: ConcurrentStableList[str] = ConcurrentStableList()
    platform_codes: ConcurrentStableSet[int] = ConcurrentStableSet(int(member) for member in ErrorCode)
    segments: ConcurrentStableDict[str, str] = ConcurrentStableDict()
    for module in SERVICE_CATALOG:
        if module.errcode_segment:
            segments.setdefault(module.errcode_segment, module.product_key or module.service_key or "platform")
    seen: ConcurrentStableDict[int, tuple[ErrorCodeRecord, Path]] = ConcurrentStableDict()
    for manifest, source in zip(manifests, sources, strict=True):
        for record in manifest.error_codes:
            if record.code in platform_codes:
                errors.add(f"{source}｜错误码 {record.code}：与平台错误码撞码")
            existing = seen.get(record.code)
            if existing is None:
                seen.set(record.code, (record, source))
            else:
                other, other_source = existing
                if other != record:
                    errors.add(
                        f"产品清单错误码撞码：{record.code}"
                        f"（{other.product_key}@{other_source} 与 {record.product_key}@{source}）"
                    )
            owner = segments.get(record.segment)
            if owner is None:
                segments.set(record.segment, record.product_key)
            elif owner != record.product_key:
                errors.add(f"{source}｜错误码 {record.code}：段位跨产品复用（段 {record.segment} 已被 {owner} 使用）")
    return errors


def inspect_product_manifests(paths: Iterable[str | Path]) -> ManifestInspection:
    """按路径解析并**校验**产品清单（不注册、不抛错；装配期与离线门禁共用）。

    Args:
        paths: 清单文件路径序列（相对路径按后端工程根解析；不存在的路径跳过）。

    Returns:
        ManifestInspection: 解析结果 + 错误 + 警示。
    """
    manifests: ConcurrentStableList[ProductManifest] = ConcurrentStableList()
    sources: ConcurrentStableList[Path] = ConcurrentStableList()
    errors: ConcurrentStableList[str] = ConcurrentStableList()
    warnings: ConcurrentStableList[str] = ConcurrentStableList()
    for raw_path in paths:
        path = _resolve_manifest_path(raw_path)
        if not path.is_file():
            continue
        try:
            manifests.add(load_product_manifest(path))
        except CatalogError as exc:
            errors.add(str(exc))
            continue
        sources.add(path)
    if errors:
        return ManifestInspection(
            manifests=ConcurrentStableFrozenList(manifests),
            sources=ConcurrentStableFrozenList(sources),
            errors=ConcurrentStableFrozenList(errors),
            warnings=ConcurrentStableFrozenList(warnings),
        )
    errors.update(_validate_collaboration_names(manifests, sources))
    errors.update(_validate_error_codes(manifests, sources))
    has_collaborations = any(manifest.collaborations for manifest in manifests)
    layout: ConcurrentStableDict[str, str] = (
        _layout_registry_map(sources, warnings) if has_collaborations else ConcurrentStableDict()
    )
    domain_keys: ConcurrentStableSet[str] = ConcurrentStableSet(layout.keys())
    domain_services: ConcurrentStableDict[str, str] = ConcurrentStableDict(
        (domain, service) for domain, service in layout.items() if service
    )
    consumer_keys = _consumer_keys(manifests)
    branch_domains: ConcurrentStableDict[str, str] = ConcurrentStableDict()
    for manifest, source in zip(manifests, sources, strict=True):
        errors.update(
            _validate_manifest_entries(
                manifest,
                source,
                domain_keys=domain_keys,
                domain_services=domain_services,
                consumer_keys=consumer_keys,
                branch_domains=branch_domains,
                warnings=warnings,
            )
        )
    return ManifestInspection(
        manifests=ConcurrentStableFrozenList(manifests),
        sources=ConcurrentStableFrozenList(sources),
        errors=ConcurrentStableFrozenList(errors),
        warnings=ConcurrentStableFrozenList(warnings),
        domain_services=ConcurrentStableFrozenDict(domain_services),
    )


def register_manifest(manifest: ProductManifest) -> None:
    """把清单记录注册进基座运行期视图（七类；幂等、同键异值即拒）。

    Args:
        manifest: 产品登记清单。
    """
    register_product_records(manifest.products)
    register_service_records(manifest.services)
    register_product_routes(manifest.product_routes)
    register_data_source_records(manifest.data_sources)
    register_collaboration_records(manifest.collaborations)
    register_seed_records(manifest.seeds)
    register_error_code_records(manifest.error_codes)


LOCAL_REGISTRY_DIR = "deploy/registry"
"""本仓自持声明目录（相对工程根的父级：仓根）。"""


def local_manifest_paths() -> ConcurrentStableList[Path]:
    """本仓自持声明路径（`deploy/registry/*.toml`，按文件名排序）。

    平台自注册（`02_06`）与单仓自检共用同一发现规则：只读**本仓**清单，不读别的产品仓。

    Returns:
        ConcurrentStableList[Path]: 清单路径（目录不存在为空）。
    """
    return _local_manifest_paths()


def _local_manifest_paths() -> ConcurrentStableList[Path]:
    """发现**本仓**自持声明（`<仓根>/deploy/registry/*.toml`，按文件名排序）。

    07B `02_03`：平台种子与产品种子同一形态——平台声明 `deploy/registry/platform.toml`
    与产品声明走同一扫描规则，无需逐个配置。目录不存在时返回空（极简环境 / CI 单包）。

    Returns:
        ConcurrentStableList[Path]: 本仓声明路径（排序稳定）。
    """
    directory = _MANIFEST_BASE.parent / LOCAL_REGISTRY_DIR
    if not directory.is_dir():
        return ConcurrentStableList()
    return ConcurrentStableList(sorted(directory.glob("*.toml")))


def _with_local_manifests(paths: Iterable[str | Path]) -> ConcurrentStableList[str | Path]:
    """把本仓声明**排在配置路径之前**（平台在前、外部产品在后）。

    Args:
        paths: 配置注入的清单路径序列。

    Returns:
        ConcurrentStableList[str | Path]: 合并后的路径序列（本仓在前）。
    """
    merged: ConcurrentStableList[str | Path] = ConcurrentStableList(_local_manifest_paths())
    merged.update(paths)
    return merged


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
    """按配置路径批量装载、校验并注册产品清单（缺省空清单；不存在的路径跳过）。

    **装载即校验**：六类校验任一不满足即抛 `CatalogError` 拒启（聚合全部错误一次报出）；
    跳过项与降级提示以 `WARNING` 日志输出，不静默。

    Args:
        paths: 清单文件路径序列（相对路径按**后端工程根** `backend/` 解析，不随工作目录变化）。

    Returns:
        ConcurrentStableList[ProductManifest]: 已装载清单（插入序）。

    Raises:
        CatalogError: 清单非法或校验不通过（拒启）。
    """
    inspection = inspect_product_manifests(_with_local_manifests(paths))
    logger = get_logger("bms")
    for warning in inspection.warnings:
        logger.warning("product_manifest_warning", detail=warning)
    if inspection.errors:
        raise CatalogError("产品清单装载失败：" + "；".join(inspection.errors))
    for manifest in inspection.manifests:
        register_manifest(manifest)
    # 业务域 → 承载服务键（能力寻址第二段过渡实现的取数来源；派生视图，不是第二份声明）
    register_domain_services(inspection.domain_services)
    return ConcurrentStableList(inspection.manifests)
