"""服务目录与契约登记：服务清单（单一来源）与注册要素唯一性 / 格式校验。

- `SERVICE_CATALOG` 是种子、启动 / CI 校验与只读接口的**单一来源**（服务与模块同源登记）。
- 离线校验：`ModuleRegistry.validate()`（清单四要素唯一与格式、分组 / 批次 / 版本 / 产品维度
  ——含**产品归属**：产品分组模块的 `product_key` 须在 `PRODUCT_CATALOG` 登记）。
- 接库校验：`validate_catalog()`（启动 / CI 共用）——库内查重与格式 + 与清单双向对账 +
  运行服务登记行与契约版本主版本兼容（需求 03-2）。
- `PRODUCT_CATALOG` 是**产品档案**（`sys_product`）的种子与产品级注册校验**单一来源**（需求 12-1）；
  离线校验 `ProductRegistry.validate()`，接库对账 `validate_products()`（CI `ops.check_modules`）。
- `known_event_domains()`：已登记事件域集合（事件契约命名校验的域来源，需求 05-4）。
"""

import re
from collections import Counter
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, cast

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList, ConcurrentStableSet
from bms_core.core.objects import BaseFrameworkObject, BaseRegistryRecordContract
from bms_core.core.version import CONTRACT_VERSION_RE, contract_major

_PREFIX_RE = re.compile(r"^[a-z][a-z0-9]*_$")
_SEGMENT_RE = re.compile(r"^\d{2}$")
_DOMAIN_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_KEY_RE = re.compile(r"^[a-z][a-z0-9]*$")
_SERVICE_KEY_RE = re.compile(r"^[a-z][a-z0-9_-]*$")


class ModuleStatus(StrEnum):
    """登记状态（`sys_module.status`）。"""

    ENABLED = "enabled"
    DISABLED = "disabled"
    PLANNED = "planned"


class ServiceGroup(StrEnum):
    """服务归属分组（`sys_module.service_group`）。"""

    FOUNDATION = "foundation"
    CAPABILITY = "capability"
    PRODUCT = "product"


class ProductStatus(StrEnum):
    """产品状态（`sys_product.status`）。"""

    ENABLED = "enabled"
    DISABLED = "disabled"
    PLANNED = "planned"
    """已注册、尚未建代码 / 建表（先注册后建表的预登记态）。"""

    RETIRED = "retired"
    """下线保留登记（不物理删除、不回收注册段位，架构 11「模块契约与产品下线」节）。"""


@dataclass(frozen=True)
class ModuleRecord(BaseRegistryRecordContract):
    """服务 / 模块登记记录（字段与 `sys_module` 对齐）。"""

    module_key: str
    name: str
    table_prefix: str
    event_domain: str
    errcode_segment: str | None = None
    service_key: str | None = None
    business_code: str | None = None
    service_group: str = ServiceGroup.FOUNDATION
    build_batch: int = 0
    service_version: str = "0.1.0"
    contract_version: str = "0.1.0"
    product_key: str | None = None
    status: str = ModuleStatus.ENABLED

    @classmethod
    def from_row(cls, row: object) -> ModuleRecord:
        """按目录字段从 ORM 行（或任意同构对象）构造记录（接库校验用）。

        Args:
            row: 具备目录字段的对象（如 `SysModule` 行）。

        Returns:
            ModuleRecord: 登记记录。
        """
        data = cast("Any", row)
        return cls(
            module_key=cast("str", data.module_key),
            name=cast("str", data.name),
            table_prefix=cast("str", data.table_prefix),
            event_domain=cast("str", data.event_domain),
            errcode_segment=cast("str | None", data.errcode_segment),
            service_key=cast("str | None", data.service_key),
            business_code=cast("str | None", data.business_code),
            service_group=cast("str", data.service_group),
            build_batch=cast("int", data.build_batch),
            service_version=cast("str", data.service_version),
            contract_version=cast("str", data.contract_version),
            product_key=cast("str | None", data.product_key),
            status=cast("str", data.status),
        )


@dataclass(frozen=True)
class ProductRecord(BaseRegistryRecordContract):
    """产品档案登记记录（字段与 `sys_product` 对齐）。"""

    product_key: str
    name: str
    frontend_package_source: str | None = None
    status: str = ProductStatus.ENABLED

    @classmethod
    def from_row(cls, row: object) -> ProductRecord:
        """按档案字段从 ORM 行（或任意同构对象）构造记录（接库对账用）。

        Args:
            row: 具备档案字段的对象（如 `SysProduct` 行）。

        Returns:
            ProductRecord: 产品档案记录。
        """
        data = cast("Any", row)
        return cls(
            product_key=cast("str", data.product_key),
            name=cast("str", data.name),
            frontend_package_source=cast("str | None", data.frontend_package_source),
            status=cast("str", data.status),
        )


SERVICE_CATALOG: tuple[ModuleRecord, ...] = (
    ModuleRecord(
        module_key="sys",
        service_key="platform",
        name="平台地基与配置服务",
        table_prefix="sys_",
        business_code=None,
        errcode_segment="01",
        event_domain="sys",
        service_group=ServiceGroup.FOUNDATION,
        build_batch=0,
        contract_version="0.2.0",
        status=ModuleStatus.ENABLED,
    ),
    ModuleRecord(
        module_key="identity",
        service_key="identity",
        name="认证与身份服务",
        table_prefix="identity_",
        errcode_segment=None,
        event_domain="identity",
        service_group=ServiceGroup.FOUNDATION,
        build_batch=0,
        status=ModuleStatus.ENABLED,
    ),
    ModuleRecord(
        module_key="tenant",
        service_key="tenant",
        name="租户与配置服务",
        table_prefix="tenant_",
        errcode_segment=None,
        event_domain="tenant",
        service_group=ServiceGroup.FOUNDATION,
        build_batch=0,
        status=ModuleStatus.ENABLED,
    ),
    ModuleRecord(
        module_key="org",
        service_key="org",
        name="组织主数据服务",
        table_prefix="org_",
        errcode_segment=None,
        event_domain="org",
        service_group=ServiceGroup.CAPABILITY,
        build_batch=2,
        status=ModuleStatus.ENABLED,
    ),
    ModuleRecord(
        module_key="file",
        service_key="file",
        name="文件服务",
        table_prefix="file_",
        errcode_segment=None,
        event_domain="file",
        service_group=ServiceGroup.CAPABILITY,
        build_batch=1,
        status=ModuleStatus.ENABLED,
    ),
    ModuleRecord(
        module_key="notification",
        service_key="notification",
        name="通知服务",
        table_prefix="notification_",
        errcode_segment=None,
        event_domain="notification",
        service_group=ServiceGroup.CAPABILITY,
        build_batch=1,
        status=ModuleStatus.ENABLED,
    ),
    ModuleRecord(
        module_key="search",
        service_key="search",
        name="全文检索服务",
        table_prefix="search_",
        errcode_segment=None,
        event_domain="search",
        service_group=ServiceGroup.CAPABILITY,
        build_batch=1,
        status=ModuleStatus.ENABLED,
    ),
    ModuleRecord(
        module_key="ai",
        service_key="ai",
        name="AI 服务",
        table_prefix="ai_",
        errcode_segment="04",
        event_domain="ai",
        service_group=ServiceGroup.CAPABILITY,
        build_batch=1,
        status=ModuleStatus.ENABLED,
    ),
    ModuleRecord(
        module_key="rpt",
        service_key="report",
        name="报表打印服务",
        table_prefix="rpt_",
        errcode_segment="03",
        event_domain="rpt",
        service_group=ServiceGroup.CAPABILITY,
        build_batch=1,
        status=ModuleStatus.ENABLED,
    ),
    ModuleRecord(
        module_key="wf",
        service_key="workflow",
        name="工作流服务",
        table_prefix="wf_",
        errcode_segment="02",
        event_domain="wf",
        service_group=ServiceGroup.CAPABILITY,
        build_batch=2,
        status=ModuleStatus.PLANNED,
    ),
    ModuleRecord(
        module_key="pur",
        name="采购",
        table_prefix="pur_",
        business_code="pur",
        errcode_segment="10",
        event_domain="pur",
        service_group=ServiceGroup.PRODUCT,
        build_batch=3,
        product_key="biz",
        status=ModuleStatus.PLANNED,
    ),
    ModuleRecord(
        module_key="pay",
        name="收付款",
        table_prefix="pay_",
        business_code="pay",
        errcode_segment="11",
        event_domain="pay",
        service_group=ServiceGroup.PRODUCT,
        build_batch=3,
        product_key="biz",
        status=ModuleStatus.PLANNED,
    ),
    ModuleRecord(
        module_key="sale",
        name="销售",
        table_prefix="sale_",
        business_code="sale",
        errcode_segment="12",
        event_domain="sale",
        service_group=ServiceGroup.PRODUCT,
        build_batch=3,
        product_key="biz",
        status=ModuleStatus.PLANNED,
    ),
    ModuleRecord(
        module_key="wh",
        name="仓储",
        table_prefix="wh_",
        business_code="wh",
        errcode_segment="13",
        event_domain="wh",
        service_group=ServiceGroup.PRODUCT,
        build_batch=3,
        product_key="biz",
        status=ModuleStatus.PLANNED,
    ),
    ModuleRecord(
        module_key="sup",
        name="供应商",
        table_prefix="sup_",
        business_code="sup",
        errcode_segment="14",
        event_domain="sup",
        service_group=ServiceGroup.PRODUCT,
        build_batch=3,
        product_key="biz",
        status=ModuleStatus.PLANNED,
    ),
    ModuleRecord(
        module_key="cw",
        name="创作",
        table_prefix="cw_",
        business_code="cw",
        errcode_segment="15",
        event_domain="cw",
        service_group=ServiceGroup.PRODUCT,
        build_batch=3,
        product_key="cw",
        status=ModuleStatus.PLANNED,
    ),
)
"""服务目录与注册要素（单一来源，16 行：平台服务 10 + 业务模块 6）。"""

PRODUCT_CATALOG: tuple[ProductRecord, ...] = (
    ProductRecord(product_key="biz", name="企业运营管理", status=ProductStatus.ENABLED),
    ProductRecord(product_key="cw", name="创作系统", status=ProductStatus.ENABLED),
    ProductRecord(product_key="mdm", name="主数据管理", status=ProductStatus.PLANNED),
)
"""产品档案（单一来源，3 行：`biz` / `cw` 已建 + `mdm` 预登记）。

- **先注册后建表**：产品可先于其模块登记（`mdm` 随产品接入补登记各域模块行），不要求产品必有模块；
- `frontend_package_source` 本期留空——产品前端产物来源随 R4.3 前端多包合并定稿后回填（详设 12_01 §9）；
- 注册要素（表前缀 / 业务码 / 错误码段 / 事件域）仍只在 `SERVICE_CATALOG`，本清单只承载产品级属性。
"""


def product_keys() -> ConcurrentStableSet[str]:
    """已登记产品标识集合（`PRODUCT_CATALOG`，插入序）。

    供模块产品归属校验使用（产品分组模块的 `product_key` 必须在本集合内）。

    Returns:
        ConcurrentStableSet[str]: 产品标识集合。
    """
    return ConcurrentStableSet(record.product_key for record in PRODUCT_CATALOG)


_PLATFORM_DOMAIN_KEYS: tuple[str, ...] = ("sys", "wf", "rpt", "ai")
"""既有平台域模块标识（段位 01~04 的平台域）。"""

PLATFORM_MODULES: tuple[ModuleRecord, ...] = tuple(
    module for key in _PLATFORM_DOMAIN_KEYS for module in SERVICE_CATALOG if module.module_key == key
)
"""平台域模块视图（`sys` / `wf` / `rpt` / `ai`，保持既有引用兼容）。"""


def known_event_domains() -> ConcurrentStableSet[str]:
    """取服务目录已登记事件域集合（事件契约命名校验的域来源）。

    事件名首段必须是本集合中的事件域（《命名规范》「事件总线/Webhook 事件」行口径）。

    Returns:
        ConcurrentStableSet[str]: 去重后的事件域集合（插入序）。
    """
    return ConcurrentStableSet(record.event_domain for record in SERVICE_CATALOG)


def enabled_service_keys() -> tuple[str, ...]:
    """已启用服务标识集合（`service_key` 非空且 `status = enabled`，保持目录顺序）。

    用于「按服务×租户建库」的服务维度（06_01）：只对已建设服务建库，`planned` 服务与
    无 `service_key` 的产品模块不建库（产品模块随产品仓库接入）。

    Returns:
        tuple[str, ...]: 服务标识元组。
    """
    return tuple(
        record.service_key for record in SERVICE_CATALOG if record.service_key and record.status == ModuleStatus.ENABLED
    )


def _duplicates(values: ConcurrentStableList[str]) -> ConcurrentStableList[str]:
    """取重复值（保持首次出现顺序）。

    Args:
        values: 待检查值列表（插入序）。

    Returns:
        ConcurrentStableList[str]: 重复出现的值（插入序）。
    """
    counter = Counter(values)
    seen: ConcurrentStableSet[str] = ConcurrentStableSet()
    result: ConcurrentStableList[str] = ConcurrentStableList()
    for value in values:
        if counter[value] > 1 and value not in seen:
            seen.add(value)
            result.add(value)
    return result


class ModuleRegistry(BaseFrameworkObject):
    """服务目录与注册要素校验 / 清单查询（离线）。"""

    def __init__(
        self,
        modules: ConcurrentStableList[ModuleRecord] | None = None,
        products: ConcurrentStableList[ProductRecord] | None = None,
    ) -> None:
        """初始化。

        Args:
            modules: 注册清单（插入序）；默认全量服务目录 `SERVICE_CATALOG`。
            products: 产品档案清单（插入序）；默认 `PRODUCT_CATALOG`（产品归属校验基准）。
        """
        self._modules: ConcurrentStableList[ModuleRecord] = (
            ConcurrentStableList(SERVICE_CATALOG) if modules is None else ConcurrentStableList(modules)
        )
        self._product_keys: ConcurrentStableSet[str] = ConcurrentStableSet(
            record.product_key for record in (PRODUCT_CATALOG if products is None else products)
        )

    def list_modules(
        self, *, status: str | None = None, group: str | None = None
    ) -> ConcurrentStableList[ModuleRecord]:
        """返回注册清单（可按状态 / 归属分组筛选）。

        Args:
            status: 状态筛选（`enabled` / `disabled` / `planned`）；None 返回全部。
            group: 归属分组筛选（`foundation` / `capability` / `product`）；None 返回全部。

        Returns:
            ConcurrentStableList[ModuleRecord]: 注册记录列表（插入序）。
        """
        result = self._modules
        if status is not None:
            result = ConcurrentStableList(module for module in result if module.status == status)
        if group is not None:
            result = ConcurrentStableList(module for module in result if module.service_group == group)
        return ConcurrentStableList(result)

    def validate(self) -> ConcurrentStableList[str]:
        """校验注册清单：注册要素唯一 + 格式 + 分组 / 版本 / 产品维度一致。

        Returns:
            ConcurrentStableList[str]: 冲突 / 非法明细；空列表表示通过。
        """
        errors: ConcurrentStableList[str] = ConcurrentStableList()
        for module in self._modules:
            errors.update(self._validate_record(module))
        errors.update(self._validate_duplicates())
        return errors

    def _validate_record(self, module: ModuleRecord) -> ConcurrentStableList[str]:
        """校验单条记录（格式 / 分组 / 版本 / 产品维度）。

        Args:
            module: 注册记录。

        Returns:
            ConcurrentStableList[str]: 非法明细。
        """
        errors: ConcurrentStableList[str] = ConcurrentStableList()
        key = module.module_key
        if not _KEY_RE.match(key):
            errors.add(f"{key}：module_key 非法")
        if module.service_key is not None and not _SERVICE_KEY_RE.match(module.service_key):
            errors.add(f"{key}：service_key 非法（{module.service_key}）")
        if not _PREFIX_RE.match(module.table_prefix):
            errors.add(f"{key}：table_prefix 非法（{module.table_prefix}）")
        elif not module.table_prefix.startswith(f"{key}_"):
            errors.add(f"{key}：table_prefix 首段与 module_key 不一致（{module.table_prefix}）")
        if module.errcode_segment is not None and (
            not _SEGMENT_RE.match(module.errcode_segment) or int(module.errcode_segment) < 1
        ):
            errors.add(f"{key}：errcode_segment 非法（{module.errcode_segment}）")
        if not _DOMAIN_RE.match(module.event_domain):
            errors.add(f"{key}：event_domain 非法（{module.event_domain}）")
        if module.service_group not in tuple(ServiceGroup):
            errors.add(f"{key}：service_group 非法（{module.service_group}）")
        if not 0 <= module.build_batch <= 3:
            errors.add(f"{key}：build_batch 越界（{module.build_batch}）")
        for field, value in (
            ("service_version", module.service_version),
            ("contract_version", module.contract_version),
        ):
            if not CONTRACT_VERSION_RE.fullmatch(value):
                errors.add(f"{key}：{field} 非 semver（{value}）")
        if module.service_group == ServiceGroup.PRODUCT and not module.product_key:
            errors.add(f"{key}：产品分组缺 product_key")
        elif module.service_group == ServiceGroup.PRODUCT and module.product_key not in self._product_keys:
            errors.add(f"{key}：product_key 未登记（{module.product_key}）")
        elif module.service_group != ServiceGroup.PRODUCT and module.product_key:
            errors.add(f"{key}：非产品分组不应有 product_key（{module.product_key}）")
        return errors

    def _validate_duplicates(self) -> ConcurrentStableList[str]:
        """校验注册要素唯一性（服务键 / 段位仅非空去重）。

        Returns:
            ConcurrentStableList[str]: 重复明细。
        """
        errors: ConcurrentStableList[str] = ConcurrentStableList()
        for field in ("module_key", "table_prefix", "event_domain"):
            values = ConcurrentStableList(str(getattr(module, field)) for module in self._modules)
            for duplicate in _duplicates(values):
                errors.add(f"{field} 重复：{duplicate}")
        for optional in ("service_key", "errcode_segment"):
            optional_values = ConcurrentStableList(
                value for module in self._modules if (value := getattr(module, optional)) is not None
            )
            for duplicate in _duplicates(optional_values):
                errors.add(f"{optional} 重复：{duplicate}")
        return errors


class ProductRegistry(BaseFrameworkObject):
    """产品档案校验 / 清单查询（离线，与服务目录校验同源模式）。"""

    def __init__(self, products: ConcurrentStableList[ProductRecord] | None = None) -> None:
        """初始化。

        Args:
            products: 产品档案清单（插入序）；默认全量 `PRODUCT_CATALOG`。
        """
        self._products: ConcurrentStableList[ProductRecord] = (
            ConcurrentStableList(PRODUCT_CATALOG) if products is None else ConcurrentStableList(products)
        )

    def list_products(self, *, status: str | None = None) -> ConcurrentStableList[ProductRecord]:
        """返回产品档案清单（可按状态筛选）。

        Args:
            status: 状态筛选（`enabled` / `disabled` / `planned` / `retired`）；None 返回全部。

        Returns:
            ConcurrentStableList[ProductRecord]: 产品档案记录列表（插入序）。
        """
        if status is None:
            return ConcurrentStableList(self._products)
        return ConcurrentStableList(record for record in self._products if record.status == status)

    def validate(self) -> ConcurrentStableList[str]:
        """校验产品档案清单：标识 / 名称 / 来源 / 状态合法 + 产品标识唯一。

        Returns:
            ConcurrentStableList[str]: 非法明细；空列表表示通过。
        """
        errors: ConcurrentStableList[str] = ConcurrentStableList()
        for record in self._products:
            errors.update(self._validate_record(record))
        keys = ConcurrentStableList(record.product_key for record in self._products)
        for duplicate in _duplicates(keys):
            errors.add(f"product_key 重复：{duplicate}")
        return errors

    def _validate_record(self, record: ProductRecord) -> ConcurrentStableList[str]:
        """校验单条产品档案（标识 / 名称 / 来源 / 状态）。

        Args:
            record: 产品档案记录。

        Returns:
            ConcurrentStableList[str]: 非法明细。
        """
        errors: ConcurrentStableList[str] = ConcurrentStableList()
        key = record.product_key
        if not _KEY_RE.match(key):
            errors.add(f"{key}：product_key 非法")
        if not record.name.strip():
            errors.add(f"{key}：name 为空")
        if record.status not in tuple(ProductStatus):
            errors.add(f"{key}：status 非法（{record.status}）")
        source = record.frontend_package_source
        if source is not None and not source.strip():
            errors.add(f"{key}：frontend_package_source 为空串（须留空或填产品前端来源）")
        return errors


_PRODUCT_COMPARE_FIELDS: tuple[str, ...] = ("name", "frontend_package_source", "status")
"""产品档案双向对账的严格一致字段。"""


def validate_products(
    products: ConcurrentStableList[ProductRecord],
    records: ConcurrentStableList[ProductRecord],
) -> ConcurrentStableList[str]:
    """接库产品档案校验（CI 共用）：库内查重与格式 + 与清单双向对账。

    Args:
        products: 产品档案清单（`PRODUCT_CATALOG`）。
        records: 库中未软删行转换结果（`ProductRecord.from_row`）。

    Returns:
        ConcurrentStableList[str]: 冲突 / 漂移明细；空列表表示通过。
    """
    errors = ProductRegistry(records).validate()
    errors.update(_diff_products(products, records))
    return errors


def _diff_products(
    products: ConcurrentStableList[ProductRecord], records: ConcurrentStableList[ProductRecord]
) -> ConcurrentStableList[str]:
    """产品清单与库记录双向对账（缺行 / 清单外行 / 字段不符）。

    Args:
        products: 产品档案清单（插入序）。
        records: 库中未软删行转换结果（插入序）。

    Returns:
        ConcurrentStableList[str]: 对账明细。
    """
    errors: ConcurrentStableList[str] = ConcurrentStableList()
    expected_by_key = ConcurrentStableDict((record.product_key, record) for record in products)
    actual_by_key = ConcurrentStableDict((record.product_key, record) for record in records)
    for key in sorted(actual_by_key.keys() - expected_by_key.keys()):
        errors.add(f"产品档案库中登记行不在清单：{key}")
    for key in sorted(expected_by_key.keys() - actual_by_key.keys()):
        errors.add(f"产品档案库中缺登记行：{key}")
    for key in sorted(expected_by_key.keys() & actual_by_key.keys()):
        expected = expected_by_key[key]
        actual = actual_by_key[key]
        for field in _PRODUCT_COMPARE_FIELDS:
            expected_value = getattr(expected, field)
            actual_value = getattr(actual, field)
            if expected_value != actual_value:
                errors.add(f"产品档案 {key}：{field} 与清单不一致（库 {actual_value!r}，清单 {expected_value!r}）")
    return errors


_COMPARE_FIELDS: tuple[str, ...] = (
    "service_key",
    "name",
    "table_prefix",
    "business_code",
    "errcode_segment",
    "event_domain",
    "service_group",
    "build_batch",
    "product_key",
    "status",
)
"""双向对账的严格一致字段（不含 `contract_version`：按主版本兼容；不含 `service_version`：归发布环节）。"""


def validate_catalog(
    catalog: ConcurrentStableList[ModuleRecord],
    records: ConcurrentStableList[ModuleRecord],
    *,
    service_key: str | None = None,
    contract_version: str | None = None,
) -> ConcurrentStableList[str]:
    """接库服务目录校验（启动 / CI 共用）：库内查重与格式 + 与清单双向对账 + 运行服务契约版本。

    Args:
        catalog: 服务目录清单（`SERVICE_CATALOG`）。
        records: 库中未软删行转换结果（`ModuleRecord.from_row`）。
        service_key: 运行服务标识（启动校验传入；CI 传 None 跳过运行服务项）。
        contract_version: 运行服务自报契约版本（`ServiceIdentity.contract_version`）。

    Returns:
        ConcurrentStableList[str]: 冲突 / 非法明细；空列表表示通过。
    """
    errors = ModuleRegistry(records).validate()
    errors.update(_diff_catalog(catalog, records))
    if service_key is not None:
        errors.update(_check_running_service(records, service_key=service_key, contract_version=contract_version or ""))
    return errors


def _diff_catalog(
    catalog: ConcurrentStableList[ModuleRecord], records: ConcurrentStableList[ModuleRecord]
) -> ConcurrentStableList[str]:
    """清单与库记录双向对账（缺行 / 清单外行 / 字段不符 / 契约主版本不兼容）。

    Args:
        catalog: 服务目录清单（插入序）。
        records: 库中未软删行转换结果（插入序）。

    Returns:
        ConcurrentStableList[str]: 对账明细。
    """
    errors: ConcurrentStableList[str] = ConcurrentStableList()
    expected_by_key = ConcurrentStableDict((module.module_key, module) for module in catalog)
    actual_by_key = ConcurrentStableDict((record.module_key, record) for record in records)
    for key in sorted(actual_by_key.keys() - expected_by_key.keys()):
        errors.add(f"库中登记行不在清单：{key}")
    for key in sorted(expected_by_key.keys() - actual_by_key.keys()):
        errors.add(f"库中缺登记行：{key}")
    for key in sorted(expected_by_key.keys() & actual_by_key.keys()):
        expected = expected_by_key[key]
        actual = actual_by_key[key]
        for field in _COMPARE_FIELDS:
            expected_value = getattr(expected, field)
            actual_value = getattr(actual, field)
            if expected_value != actual_value:
                errors.add(f"{key}：{field} 与清单不一致（库 {actual_value!r}，清单 {expected_value!r}）")
        if not _contract_compatible(expected.contract_version, actual.contract_version):
            errors.add(f"{key}：契约版本主版本不兼容（库 {actual.contract_version}，清单 {expected.contract_version}）")
    return errors


def _check_running_service(
    records: ConcurrentStableList[ModuleRecord],
    *,
    service_key: str,
    contract_version: str,
) -> ConcurrentStableList[str]:
    """运行服务项：登记行存在 + 契约版本主版本兼容。

    Args:
        records: 库中未软删行转换结果（插入序）。
        service_key: 运行服务标识（微服务工程名）。
        contract_version: 运行服务自报契约版本。

    Returns:
        ConcurrentStableList[str]: 冲突 / 非法明细。
    """
    expected_major = contract_major(contract_version)
    if expected_major is None:
        return ConcurrentStableList([f"运行服务契约版本非法：{service_key} → {contract_version!r}（应为 X.Y.Z）"])
    actual = next((record for record in records if record.service_key == service_key), None)
    if actual is None:
        return ConcurrentStableList([f"运行服务未登记：{service_key}"])
    actual_major = contract_major(actual.contract_version)
    if actual_major is None:
        return ConcurrentStableList([f"{actual.module_key}：登记契约版本非法（{actual.contract_version!r}）"])
    if actual_major != expected_major:
        return ConcurrentStableList(
            [
                f"运行服务契约版本主版本不兼容：{service_key} 自报 {contract_version}（主版本 {expected_major}）"
                f" vs 登记 {actual.contract_version}（主版本 {actual_major}）"
            ]
        )
    return ConcurrentStableList()


def _contract_compatible(expected_version: str, actual_version: str) -> bool:
    """契约版本主版本兼容判定。

    Args:
        expected_version: 期望契约版本（清单登记值）。
        actual_version: 实际契约版本（库中登记值）。

    Returns:
        bool: 主版本一致且格式合法 True。
    """
    expected_major = contract_major(expected_version)
    return expected_major is not None and expected_major == contract_major(actual_version)
