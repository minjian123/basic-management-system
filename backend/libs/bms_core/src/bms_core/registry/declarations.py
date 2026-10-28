"""产品声明注册的核心逻辑（07B `02_06`）：**内容指纹 + 整体对账 + 跨产品校验**。

本模块只做纯逻辑（无 IO、无进程级状态），供注册服务端与用例共用：

- `DeclarationPayload`：一个产品的**八类声明全集**（注册协议载荷）；
- `RegistrySnapshot`：注册表现状（八类，键 → 记录 + 指纹 + 状态）；
- `plan_declarations()`：整体对账 → `DeclarationPlan`（新增 / 覆盖 / 未变 / 退役）；
- `validate_declarations()`：跨产品一致性校验（对着注册表现状，而非「本次装载了哪些清单」）。

口径：

- **单次全量**：产品每次注册都提交自己八类声明的全集，未出现的记录退役（不删行）；
- **内容未变不写**：按 `content_hash` 判定，避免重启即写库；
- **跨产品撞键即拒**：同一业务键被其他产品占用属配置冲突，不静默覆盖。
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, cast

from bms_core.collaboration.base import WRITE_KINDS
from bms_core.collaboration.usage import DEGRADE_NONE, DEGRADE_STALE, CapabilityUsage
from bms_core.core.concurrent import (
    ConcurrentStableDict,
    ConcurrentStableFrozenDict,
    ConcurrentStableFrozenList,
    ConcurrentStableList,
    ConcurrentStableSet,
)
from bms_core.core.exceptions import CatalogError
from bms_core.core.objects import BaseValueObject
from bms_core.datasource.registry import DataSourceRecord
from bms_core.services.module_registry import (
    CollaborationRecord,
    ErrorCodeRecord,
    ModuleRecord,
    ProductRecord,
    ProductRouteRecord,
    SeedRecord,
)

__all__ = [
    "DECLARATION_KINDS",
    "DeclarationPayload",
    "DeclarationPlan",
    "DeclarationReport",
    "RegistrySnapshot",
    "content_hash_of",
    "declaration_key",
    "from_manifest",
    "plan_declarations",
    "record_from_wire",
    "validate_declarations",
]

DECLARATION_KINDS: ConcurrentStableFrozenList[str] = ConcurrentStableFrozenList(
    (
        "products",
        "services",
        "product_routes",
        "data_sources",
        "collaborations",
        "seeds",
        "errcodes",
        "usages",
    )
)
"""八类声明（顺序即注册协议与视图投影口径）。"""

_KIND_KEYS: ConcurrentStableDict[str, str] = ConcurrentStableDict(
    {
        "products": "product_key",
        "services": "module_key",
        "product_routes": "domain",
        "data_sources": "data_source_key",
        "collaborations": "name",
        "seeds": "name",
        "errcodes": "code",
        "usages": "name",
    }
)
"""各类声明的业务键字段名（跨产品唯一性判定用）。"""

_STATUS_RETIRED = "retired"
"""退役状态值（本次全量未声明）。"""


@dataclass(frozen=True)
class RegistrySnapshot(BaseValueObject):
    """注册表现状（按类别组织的记录全集，含指纹与状态）。"""

    records: ConcurrentStableDict[str, ConcurrentStableList[Any]] = field(
        default_factory=lambda: ConcurrentStableDict()
    )
    """`{类别: 记录列表}`（插入序；记录为各声明模型的值对象）。"""

    hashes: ConcurrentStableDict[str, ConcurrentStableDict[str, str]] = field(
        default_factory=lambda: ConcurrentStableDict()
    )
    """`{类别: {业务键: 内容指纹}}`。"""

    retired: ConcurrentStableDict[str, ConcurrentStableSet[str]] = field(default_factory=lambda: ConcurrentStableDict())
    """`{类别: {已退役业务键}}`（再次声明即恢复）。"""

    ids: ConcurrentStableDict[str, ConcurrentStableDict[str, int]] = field(
        default_factory=lambda: ConcurrentStableDict()
    )
    """`{类别: {业务键: 行主键}}`（落库更新 / 退役定位用）。"""

    owners: ConcurrentStableDict[str, ConcurrentStableDict[str, str]] = field(
        default_factory=lambda: ConcurrentStableDict()
    )
    """`{类别: {业务键: 声明方产品键}}`（共享表按声明方作用域对账用）。"""

    def owner_of(self, kind: str, key: str) -> str | None:
        """取某记录的声明方产品键。

        Args:
            kind: 声明类别。
            key: 业务键。

        Returns:
            str | None: 声明方产品键；不存在为 None。
        """
        return (self.owners.get(kind) or ConcurrentStableDict()).get(key)

    def of(self, kind: str) -> ConcurrentStableList[Any]:
        """取某类记录。

        Args:
            kind: 声明类别。

        Returns:
            ConcurrentStableList[Any]: 该类记录（未装载为空）。
        """
        return self.records.get(kind) or ConcurrentStableList()

    def hash_of(self, kind: str, key: str) -> str | None:
        """取某记录的内容指纹。

        Args:
            kind: 声明类别。
            key: 业务键。

        Returns:
            str | None: 指纹；不存在为 None。
        """
        return (self.hashes.get(kind) or ConcurrentStableDict()).get(key)

    def row_id(self, kind: str, key: str) -> int | None:
        """取某记录的行主键。

        Args:
            kind: 声明类别。
            key: 业务键。

        Returns:
            int | None: 行主键；不存在为 None。
        """
        return (self.ids.get(kind) or ConcurrentStableDict()).get(key)

    def is_retired(self, kind: str, key: str) -> bool:
        """某记录是否已退役。

        Args:
            kind: 声明类别。
            key: 业务键。

        Returns:
            bool: 已退役为 True。
        """
        return key in (self.retired.get(kind) or ConcurrentStableSet())


@dataclass(frozen=True)
class DeclarationPayload(BaseValueObject):
    """一个产品的八类声明全集（注册协议载荷）。"""

    product_key: str
    """声明方产品键（注册只能写自己名下记录）。"""

    service_key: str
    """注册方服务键（服务 JWT 的 `sub`；用于校验「声明与服务行归属一致」）。"""

    contract_version: str = "0.1.0"
    """声明随附的服务契约版本。"""

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
    errcodes: ConcurrentStableFrozenList[ErrorCodeRecord] = field(default_factory=lambda: ConcurrentStableFrozenList())
    usages: ConcurrentStableFrozenList[CapabilityUsage] = field(default_factory=lambda: ConcurrentStableFrozenList())

    def of(self, kind: str) -> ConcurrentStableList[Any]:
        """取某类声明。

        Args:
            kind: 声明类别。

        Returns:
            ConcurrentStableList[Any]: 该类记录（插入序）。
        """
        return ConcurrentStableList(cast("ConcurrentStableFrozenList[Any]", getattr(self, kind)))


@dataclass(frozen=True)
class DeclarationPlan(BaseValueObject):
    """整体对账结果（注册服务端据此落库）。"""

    created: ConcurrentStableDict[str, ConcurrentStableList[Any]] = field(
        default_factory=lambda: ConcurrentStableDict()
    )
    """`{类别: [待新增记录]}`。"""

    updated: ConcurrentStableDict[str, ConcurrentStableList[Any]] = field(
        default_factory=lambda: ConcurrentStableDict()
    )
    """`{类别: [待覆盖记录]}`（内容指纹变化）。"""

    unchanged: ConcurrentStableDict[str, ConcurrentStableList[Any]] = field(
        default_factory=lambda: ConcurrentStableDict()
    )
    """`{类别: [内容未变记录]}`（不写库）。"""

    retired: ConcurrentStableDict[str, ConcurrentStableList[str]] = field(
        default_factory=lambda: ConcurrentStableDict()
    )
    """`{类别: [待退役业务键]}`。"""

    def counts(self) -> ConcurrentStableDict[str, int]:
        """按类别汇总计数（响应体用）。

        Returns:
            ConcurrentStableDict[str, int]: `{类别: 变更条数}`（新增 + 覆盖 + 退役）。
        """
        counts: ConcurrentStableDict[str, int] = ConcurrentStableDict()
        for kind in DECLARATION_KINDS:
            total = (
                len(self.created.get(kind) or ())
                + len(self.updated.get(kind) or ())
                + len(self.retired.get(kind) or ())
            )
            counts.set(kind, total)
        return counts

    def is_empty(self) -> bool:
        """是否无需写库（全 `unchanged`）。

        Returns:
            bool: 无新增 / 覆盖 / 退役为 True。
        """
        return not any(self.counts().values())


@dataclass(frozen=True)
class DeclarationReport(BaseValueObject):
    """注册 / 拉取的对外报告。"""

    product_key: str
    """声明方产品键。"""

    created: ConcurrentStableDict[str, int] = field(default_factory=lambda: ConcurrentStableDict())
    """`{类别: 新增条数}`。"""

    updated: ConcurrentStableDict[str, int] = field(default_factory=lambda: ConcurrentStableDict())
    """`{类别: 覆盖条数}`。"""

    unchanged: ConcurrentStableDict[str, int] = field(default_factory=lambda: ConcurrentStableDict())
    """`{类别: 未变条数}`。"""

    retired: ConcurrentStableDict[str, int] = field(default_factory=lambda: ConcurrentStableDict())
    """`{类别: 退役条数}`。"""

    warnings: ConcurrentStableFrozenList[str] = field(default_factory=lambda: ConcurrentStableFrozenList())
    """装载期警示（不阻断，但必须可见）。"""

    snapshot_version: str = "0"
    """注册表版本（每次落库成功递增；消费方据此判定是否需刷新）。"""


def from_manifest(manifest: object) -> DeclarationPayload:
    """把产品清单（注册输入）转成注册载荷（八段一一对应）。

    清单自此只作**注册输入**：产品启动时读自己的清单 → 转载荷 → 上报平台；平台自身清单同样走这条路径。

    Args:
        manifest: `bms_core.registry.products.ProductManifest`（`02_01` 解析产物）。

    Returns:
        DeclarationPayload: 注册载荷（服务键取清单服务行，缺省回落产品键）。
    """
    data = cast("Any", manifest)
    services: ConcurrentStableList[ModuleRecord] = ConcurrentStableList(data.services)
    service_key = next(
        (record.service_key for record in services if record.service_key),
        str(data.product_key),
    )
    contract_version = str(services[0].contract_version) if services else "0.1.0"
    return DeclarationPayload(
        product_key=str(data.product_key),
        service_key=service_key,
        contract_version=contract_version,
        products=ConcurrentStableFrozenList(data.products),
        services=ConcurrentStableFrozenList(services),
        product_routes=ConcurrentStableFrozenList(data.product_routes),
        data_sources=ConcurrentStableFrozenList(data.data_sources),
        collaborations=ConcurrentStableFrozenList(data.collaborations),
        seeds=ConcurrentStableFrozenList(data.seeds),
        errcodes=ConcurrentStableFrozenList(data.error_codes),
        usages=ConcurrentStableFrozenList(data.usages),
    )


def record_from_wire(kind: str, data: ConcurrentStableDict[str, object]) -> object:
    """把**对外传输形态**的要素还原为声明记录（消费方拉取快照后重建视图用）。

    Args:
        kind: 声明类别。
        data: 要素映射（`declaration_wire()` 的输出）。

    Returns:
        object: 声明记录（各记录值对象）。

    Raises:
        CatalogError: 类别未知。
    """
    if kind == "products":
        return ProductRecord(
            product_key=str(data.get("product_key") or ""),
            name=str(data.get("name") or ""),
            frontend_package_source=_opt_str(data.get("frontend_package_source")),
            status=str(data.get("status") or "enabled"),
        )
    if kind == "services":
        return ModuleRecord(
            module_key=str(data.get("module_key") or ""),
            service_key=_opt_str(data.get("service_key")),
            name=str(data.get("name") or ""),
            table_prefix=str(data.get("table_prefix") or ""),
            business_code=_opt_str(data.get("business_code")),
            errcode_segment=_opt_str(data.get("errcode_segment")),
            event_domain=str(data.get("event_domain") or ""),
            service_group=str(data.get("service_group") or "product"),
            build_batch=int(cast("Any", data.get("build_batch") or 0)),
            service_version=str(data.get("service_version") or "0.1.0"),
            contract_version=str(data.get("contract_version") or "0.1.0"),
            product_key=_opt_str(data.get("product_key")),
            status=str(data.get("status") or "enabled"),
        )
    if kind == "product_routes":
        return ProductRouteRecord(
            product_key=str(data.get("product_key") or ""),
            domain=str(data.get("domain") or ""),
            service_key=str(data.get("service_key") or ""),
            description=str(data.get("description") or ""),
        )
    if kind == "data_sources":
        return DataSourceRecord(
            data_source_key=str(data.get("data_source_key") or ""),
            name=str(data.get("name") or ""),
            data_source=str(data.get("data_source") or ""),
            kind=str(data.get("kind") or "dict"),
            origin=str(data.get("origin") or "product"),
            product_key=str(data.get("product_key") or ""),
            path=_opt_str(data.get("path")),
            allowlist=ConcurrentStableFrozenList(str(item) for item in cast("Any", data.get("allowlist") or ())),
            cascade=bool(data.get("cascade")),
            strategies=ConcurrentStableFrozenList(str(item) for item in cast("Any", data.get("strategies") or ())),
            status=str(data.get("status") or "enabled"),
        )
    if kind == "collaborations":
        return CollaborationRecord(
            name=str(data.get("name") or ""),
            domain=str(data.get("domain") or ""),
            kind=str(data.get("kind") or "read"),
            contract_version=str(data.get("contract_version") or "0.1.0"),
            path=_opt_str(data.get("path")),
            product_key=_opt_str(data.get("product_key")),
            branch_id=_opt_str(data.get("branch_id")),
            branch_op=_opt_str(data.get("branch_op")),
            data_source_key=_opt_str(data.get("data_source_key")),
            permission_codes=ConcurrentStableFrozenList(
                str(item) for item in cast("Any", data.get("permission_codes") or ())
            ),
            frontend_prefix=_opt_str(data.get("frontend_prefix")),
            default_consumers=ConcurrentStableFrozenList(
                str(item) for item in cast("Any", data.get("default_consumers") or ())
            ),
            status=str(data.get("status") or "enabled"),
            replacement=_opt_str(data.get("replacement")),
        )
    if kind == "seeds":
        return SeedRecord(
            name=str(data.get("name") or ""),
            module=str(data.get("module") or ""),
            entry=str(data.get("entry") or ""),
            service=str(data.get("service") or ""),
            db_key=str(data.get("db_key") or ""),
            op=str(data.get("op") or ""),
            tables=ConcurrentStableFrozenDict(
                (str(key), str(value))
                for key, value in cast("Mapping[object, object]", data.get("tables") or {}).items()
            ),
            after=ConcurrentStableFrozenList(str(item) for item in cast("Any", data.get("after") or ())),
            description=str(data.get("description") or ""),
        )
    if kind == "errcodes":
        return ErrorCodeRecord(
            code=int(cast("Any", data.get("code") or 0)),
            domain=str(data.get("domain") or ""),
            http_status=int(cast("Any", data.get("http_status") or 500)),
            message_key=str(data.get("message_key") or ""),
            severity=str(data.get("severity") or "error"),
            description=str(data.get("description") or ""),
            product_key=str(data.get("product_key") or ""),
            segment=str(data.get("segment") or ""),
            status=str(data.get("status") or "enabled"),
        )
    if kind == "usages":
        return CapabilityUsage(
            name=str(data.get("name") or ""),
            degrade=str(data.get("degrade") or DEGRADE_NONE),
            reason=str(data.get("reason") or ""),
        )
    raise CatalogError(f"未知的声明类别：{kind}（取值 {'/'.join(DECLARATION_KINDS)}）")


def _opt_str(value: object) -> str | None:
    """取可选字符串（空串归一为 None）。

    Args:
        value: 原始值。

    Returns:
        str | None: 字符串或 None。
    """
    if value is None:
        return None
    text = str(value)
    return text or None


def declaration_wire(kind: str, record: object) -> ConcurrentStableDict[str, object]:
    """把声明记录转成**对外传输形态**（服务身份出口下发用）。

    Args:
        kind: 声明类别。
        record: 声明记录。

    Returns:
        ConcurrentStableDict[str, object]: 要素映射（只含声明要素，不含行主键与审计字段）。
    """
    return _record_payload(kind, record)


def declaration_key(kind: str, record: object) -> str:
    """取某条声明的业务键。

    Args:
        kind: 声明类别。
        record: 声明记录。

    Returns:
        str: 业务键（字符串化；用于对账与唯一性判定）。

    Raises:
        CatalogError: 类别未知（内部契约错误）。
    """
    name = _KIND_KEYS.get(kind)
    if name is None:
        raise CatalogError(f"未知的声明类别：{kind}（取值 {'/'.join(DECLARATION_KINDS)}）")
    value = getattr(record, name)
    return "" if value is None else str(value)


def content_hash_of(kind: str, record: object) -> str:
    """计算声明记录的内容指纹（要素稳定序列化后取 SHA-256）。

    Args:
        kind: 声明类别。
        record: 声明记录。

    Returns:
        str: 64 位十六进制指纹。
    """
    payload = {"kind": kind, **_record_payload(kind, record)}
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


_ELEMENT_FIELDS: ConcurrentStableDict[str, ConcurrentStableFrozenList[str]] = ConcurrentStableDict(
    {
        "products": ConcurrentStableFrozenList(("product_key", "name", "frontend_package_source", "status")),
        "services": ConcurrentStableFrozenList(
            (
                "module_key",
                "service_key",
                "name",
                "table_prefix",
                "business_code",
                "errcode_segment",
                "event_domain",
                "service_group",
                "build_batch",
                "service_version",
                "contract_version",
                "product_key",
                "status",
                "tenant_base",
            )
        ),
        "product_routes": ConcurrentStableFrozenList(("product_key", "domain", "service_key", "description")),
        "data_sources": ConcurrentStableFrozenList(
            (
                "data_source_key",
                "name",
                "kind",
                "data_source",
                "origin",
                "product_key",
                "path",
                "allowlist",
                "cascade",
                "strategies",
                "status",
            )
        ),
        "collaborations": ConcurrentStableFrozenList(
            (
                "name",
                "domain",
                "kind",
                "contract_version",
                "path",
                "product_key",
                "branch_id",
                "branch_op",
                "data_source_key",
                "permission_codes",
                "frontend_prefix",
                "default_consumers",
                "status",
                "replacement",
            )
        ),
        "seeds": ConcurrentStableFrozenList(
            (
                "name",
                "module",
                "entry",
                "service",
                "db_key",
                "op",
                "product_key",
                "after",
                "tables",
                "description",
                "status",
            )
        ),
        "errcodes": ConcurrentStableFrozenList(
            (
                "code",
                "domain",
                "http_status",
                "message_key",
                "severity",
                "description",
                "product_key",
                "segment",
                "status",
            )
        ),
        "usages": ConcurrentStableFrozenList(("name", "degrade", "reason")),
    }
)
"""各类声明的**指纹要素**（顺序稳定；只含声明要素，不含运行期派生字段）。"""


def _record_payload(kind: str, record: object) -> ConcurrentStableDict[str, object]:
    """把声明记录转成可序列化要素（按 `_ELEMENT_FIELDS` 逐字段取值）。

    Args:
        kind: 声明类别。
        record: 声明记录。

    Returns:
        ConcurrentStableDict[str, object]: 要素映射（供稳定序列化取指纹）。
    """
    fields: ConcurrentStableDict[str, object] = ConcurrentStableDict()
    for name in _ELEMENT_FIELDS.get(kind) or ConcurrentStableFrozenList():
        fields.set(name, _jsonable(cast("Any", getattr(record, name, None))))
    return fields


def _jsonable(value: object) -> object:
    """把声明要素转成可 JSON 序列化的值（集合类转列表 / 映射）。

    Args:
        value: 原始要素值。

    Returns:
        object: 可序列化值。
    """
    if isinstance(value, Enum):
        # 枚举取 `value`：同一语义在「清单解析（枚举）」与「库回读（字符串）」两侧指纹一致
        return _jsonable(value.value)
    if isinstance(value, Mapping):
        mapping = cast("Mapping[object, object]", value)
        return {str(key): _jsonable(item) for key, item in mapping.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_jsonable(item) for item in cast("Iterable[object]", value)]
    if hasattr(value, "to_list"):
        listed = cast("Any", value).to_list()
        return [_jsonable(item) for item in cast("Iterable[object]", listed)]
    return value


def plan_declarations(
    payload: DeclarationPayload, current: RegistrySnapshot
) -> tuple[DeclarationPlan, ConcurrentStableList[str]]:
    """整体对账：算出新增 / 覆盖 / 未变 / 退役（纯函数）。

    Args:
        payload: 本次全量声明。
        current: 注册表现状。

    Returns:
        tuple[DeclarationPlan, ConcurrentStableList[str]]: （对账计划, 冲突明细）。
            冲突明细非空表示跨产品撞键（调用方应拒绝本次注册）。
    """
    plan_created: ConcurrentStableDict[str, ConcurrentStableList[Any]] = ConcurrentStableDict()
    plan_updated: ConcurrentStableDict[str, ConcurrentStableList[Any]] = ConcurrentStableDict()
    plan_unchanged: ConcurrentStableDict[str, ConcurrentStableList[Any]] = ConcurrentStableDict()
    plan_retired: ConcurrentStableDict[str, ConcurrentStableList[str]] = ConcurrentStableDict()
    conflicts: ConcurrentStableList[str] = ConcurrentStableList()
    for kind in DECLARATION_KINDS:
        created: ConcurrentStableList[Any] = ConcurrentStableList()
        updated: ConcurrentStableList[Any] = ConcurrentStableList()
        unchanged: ConcurrentStableList[Any] = ConcurrentStableList()
        retired: ConcurrentStableList[str] = ConcurrentStableList()
        incoming: ConcurrentStableDict[str, Any] = ConcurrentStableDict()
        for record in payload.of(kind):
            key = declaration_key(kind, record)
            if key in incoming:
                conflicts.add(f"{kind}｜{key}：同一产品重复声明")
                continue
            incoming.set(key, record)
            existing_owner = current.owner_of(kind, key)
            if existing_owner is not None and existing_owner != payload.product_key:
                conflicts.add(f"{kind}｜{key}：已被产品 {existing_owner} 注册（跨产品撞键）")
                continue
            existing_hash = current.hash_of(kind, key)
            if existing_hash is None:
                created.add(record)
            elif current.is_retired(kind, key) or existing_hash != content_hash_of(kind, record):
                updated.add(record)
            else:
                unchanged.add(record)
        for record in current.of(kind):
            key = declaration_key(kind, record)
            if key in incoming or current.is_retired(kind, key):
                continue
            if current.owner_of(kind, key) != payload.product_key:
                # 声明方作用域：别的产品名下的行不属本次全量，不退役
                continue
            retired.add(key)
        plan_created.set(kind, created)
        plan_updated.set(kind, updated)
        plan_unchanged.set(kind, unchanged)
        plan_retired.set(kind, retired)
    return (
        DeclarationPlan(created=plan_created, updated=plan_updated, unchanged=plan_unchanged, retired=plan_retired),
        conflicts,
    )


def validate_declarations(
    payload: DeclarationPayload,
    current: RegistrySnapshot,
    *,
    domain_services: ConcurrentStableDict[str, str],
    consumer_keys: ConcurrentStableSet[str],
    warnings: ConcurrentStableList[str],
) -> ConcurrentStableList[str]:
    """跨产品一致性校验（对着注册表现状）。

    Args:
        payload: 本次全量声明。
        current: 注册表现状（含本产品上一版）。
        domain_services: 业务域 → 承载服务键（域布局登记）。
        consumer_keys: 可作默认消费方 / 使用声明方的标识集合（服务键 + 产品键）。
        warnings: 警示收集器。

    Returns:
        ConcurrentStableList[str]: 错误明细（非空即拒绝本次注册）。
    """
    errors: ConcurrentStableList[str] = ConcurrentStableList()
    label = f"产品 {payload.product_key}"
    registered_capabilities = _capability_kinds(payload, current)
    if (
        payload.service_key
        and payload.product_key != payload.service_key
        # 产品键与服务键允许不同（单服务产品通常相同），但服务行必须存在
        and not any(record.service_key == payload.service_key for record in payload.services)
        and not any(record.service_key == payload.service_key for record in current.of("services"))
    ):
        errors.add(f"{label}｜注册方服务 {payload.service_key} 未在服务行声明（注册方与服务行须一致）")
    for record in payload.collaborations:
        prefix = f"{label}｜能力 {record.name}"
        owner_domain = domain_services.get(record.domain)
        if owner_domain is None:
            errors.add(f"{prefix}：提供方业务域未登记（{record.domain}）")
        missing = _collaboration_missing(record)
        if missing:
            errors.add(f"{prefix}：{missing}")
        for consumer in record.default_consumers:
            if consumer not in consumer_keys:
                # 07B `03_01` 决策（§9 偏差 4，方案 A）：注册期只告警，不因「对端尚未注册」拒收。
                # 平台先起、产品后起是常态（平台自身清单就声明了 `mdm` 消费方），硬校验会让基座无法启动；
                # 可兑现性由运行期判定（取不到即按能力调用语义失败 / 降级）与 `04_02` 跨仓对账兜底。
                warnings.add(f"{prefix}：默认消费方尚未注册（{consumer}；注册期放行，运行期按授权记录判定）")
    for usage in payload.usages:
        prefix = f"{label}｜使用声明 {usage.name}"
        if usage.name not in registered_capabilities:
            # 同上（方案 A）：提供方可能尚未启动，注册期只记警示；降级策略本身仍照常登记，
            # 运行期取不到能力按该策略处理（未声明降级即失败上抛）。
            warnings.add(f"{prefix}：被消费能力尚未注册（提供方未注册；运行期取不到按降级策略处理）")
            continue
        if usage.degrade == DEGRADE_STALE:
            errors.add(f"{prefix}：降级模式暂不支持（stale 需本地投影来源，当前未落地）")
        if usage.degrade != "none" and not usage.reason.strip():
            errors.add(f"{prefix}：声明降级须给出理由（reason 不得为空）")
        if usage.degrade != "none" and registered_capabilities.get(usage.name) in WRITE_KINDS:
            errors.add(f"{prefix}：写 / 强一致能力不得声明降级（kind={registered_capabilities.get(usage.name)}）")
    _validate_errcodes(payload, current, warnings=warnings, errors=errors, label=label)
    return errors


def _collaboration_missing(record: CollaborationRecord) -> str | None:
    """按访问面类别检查必需要素。

    Args:
        record: 能力记录。

    Returns:
        str | None: 缺失说明；要素齐备为 None。
    """
    if record.kind == "codes":
        return None if record.permission_codes else "codes 类须声明业务码 / 权限码"
    if record.path is None:
        return f"访问面路径缺失（kind={record.kind}）"
    if record.kind == "txn-branch" and (record.branch_id is None or record.branch_op is None):
        return "txn-branch 类须声明 branch_id 与 branch_op"
    if record.kind == "dataset" and record.data_source_key is None:
        return "dataset 类须声明 data_source_key"
    return None


def _capability_kinds(payload: DeclarationPayload, current: RegistrySnapshot) -> ConcurrentStableDict[str, str]:
    """取「本次声明 + 注册表现状」的能力名 → 访问面类别。

    Args:
        payload: 本次声明。
        current: 注册表现状。

    Returns:
        ConcurrentStableDict[str, str]: 能力名 → 类别。
    """
    kinds: ConcurrentStableDict[str, str] = ConcurrentStableDict()
    for record in current.of("collaborations"):
        kinds.set(record.name, record.kind)
    for record in payload.collaborations:
        kinds.set(record.name, record.kind)
    return kinds


def _validate_errcodes(
    payload: DeclarationPayload,
    current: RegistrySnapshot,
    *,
    warnings: ConcurrentStableList[str],
    errors: ConcurrentStableList[str],
    label: str,
) -> None:
    """校验错误码段位与撞码。

    Args:
        payload: 本次声明。
        current: 注册表现状。
        warnings: 警示收集器。
        errors: 错误收集器。
        label: 错误定位前缀。
    """
    segments: ConcurrentStableDict[str, str] = ConcurrentStableDict()
    for record in payload.services:
        if record.errcode_segment:
            segments.set(record.module_key, record.errcode_segment)
    for record in current.of("services"):
        if record.errcode_segment:
            segments.setdefault(record.module_key, record.errcode_segment)
    platform_segments: ConcurrentStableSet[str] = ConcurrentStableSet(
        record.errcode_segment for record in current.of("services") if record.errcode_segment
    )
    taken: ConcurrentStableDict[int, str] = ConcurrentStableDict()
    for record in current.of("errcodes"):
        taken.set(int(record.code), str(record.product_key))
    for record in payload.errcodes:
        prefix = f"{label}｜错误码 {record.code}"
        segment = record.segment or ""
        if len(segment) != 2 or not segment.isdigit():
            errors.add(f"{prefix}：段位非法（{record.segment}）")
        elif not str(record.code).startswith(segment):
            errors.add(f"{prefix}：码与段位不一致（段 {segment}；平台段 {sorted(platform_segments)} 不得占用）")
        owner = taken.get(int(record.code))
        if owner is not None and owner != payload.product_key:
            errors.add(f"{prefix}：跨产品撞码（已被 {owner} 注册）")
    if payload.usages and not payload.collaborations:
        warnings.add(f"{label}：本次仅声明使用（消费）项，未声明本产品能力")
