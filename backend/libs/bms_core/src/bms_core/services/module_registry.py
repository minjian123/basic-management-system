"""服务目录与契约登记：服务清单（单一来源）与注册要素唯一性 / 格式校验。

- `SERVICE_CATALOG` 是种子、启动 / CI 校验与只读接口的**单一来源**（服务与模块同源登记）。
- 本模块为**离线校验**（`validate()`）；接库查重与契约版本兼容校验归需求 03-2。
"""

import re
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from bms_core.core.base import BaseObject

_PREFIX_RE = re.compile(r"^[a-z][a-z0-9]*_$")
_SEGMENT_RE = re.compile(r"^\d{2}$")
_DOMAIN_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_KEY_RE = re.compile(r"^[a-z][a-z0-9]*$")
_SERVICE_KEY_RE = re.compile(r"^[a-z][a-z0-9_-]*$")
_SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")


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


@dataclass(frozen=True)
class ModuleRecord(BaseObject):
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

_PLATFORM_DOMAIN_KEYS: tuple[str, ...] = ("sys", "wf", "rpt", "ai")
"""既有平台域模块标识（段位 01~04 的平台域）。"""

PLATFORM_MODULES: tuple[ModuleRecord, ...] = tuple(
    module for key in _PLATFORM_DOMAIN_KEYS for module in SERVICE_CATALOG if module.module_key == key
)
"""平台域模块视图（`sys` / `wf` / `rpt` / `ai`，保持既有引用兼容）。"""


def _duplicates(values: list[str]) -> list[str]:
    """取重复值（保持首次出现顺序）。

    Args:
        values: 待检查值列表。

    Returns:
        list[str]: 重复出现的值。
    """
    counter = Counter(values)
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if counter[value] > 1 and value not in seen:
            seen.add(value)
            result.append(value)
    return result


class ModuleRegistry(BaseObject):
    """服务目录与注册要素校验 / 清单查询（离线）。"""

    def __init__(self, modules: Sequence[ModuleRecord] = SERVICE_CATALOG) -> None:
        """初始化。

        Args:
            modules: 注册清单；默认全量服务目录 `SERVICE_CATALOG`。
        """
        self._modules = list(modules)

    def list_modules(self, *, status: str | None = None, group: str | None = None) -> list[ModuleRecord]:
        """返回注册清单（可按状态 / 归属分组筛选）。

        Args:
            status: 状态筛选（`enabled` / `disabled` / `planned`）；None 返回全部。
            group: 归属分组筛选（`foundation` / `capability` / `product`）；None 返回全部。

        Returns:
            list[ModuleRecord]: 注册记录列表。
        """
        result = self._modules
        if status is not None:
            result = [module for module in result if module.status == status]
        if group is not None:
            result = [module for module in result if module.service_group == group]
        return list(result)

    def validate(self) -> list[str]:
        """校验注册清单：注册要素唯一 + 格式 + 分组 / 版本 / 产品维度一致。

        Returns:
            list[str]: 冲突 / 非法明细；空列表表示通过。
        """
        errors: list[str] = []
        for module in self._modules:
            errors.extend(self._validate_record(module))
        errors.extend(self._validate_duplicates())
        return errors

    def _validate_record(self, module: ModuleRecord) -> list[str]:
        """校验单条记录（格式 / 分组 / 版本 / 产品维度）。

        Args:
            module: 注册记录。

        Returns:
            list[str]: 非法明细。
        """
        errors: list[str] = []
        key = module.module_key
        if not _KEY_RE.match(key):
            errors.append(f"{key}：module_key 非法")
        if module.service_key is not None and not _SERVICE_KEY_RE.match(module.service_key):
            errors.append(f"{key}：service_key 非法（{module.service_key}）")
        if not _PREFIX_RE.match(module.table_prefix):
            errors.append(f"{key}：table_prefix 非法（{module.table_prefix}）")
        elif not module.table_prefix.startswith(f"{key}_"):
            errors.append(f"{key}：table_prefix 首段与 module_key 不一致（{module.table_prefix}）")
        if module.errcode_segment is not None and (
            not _SEGMENT_RE.match(module.errcode_segment) or int(module.errcode_segment) < 1
        ):
            errors.append(f"{key}：errcode_segment 非法（{module.errcode_segment}）")
        if not _DOMAIN_RE.match(module.event_domain):
            errors.append(f"{key}：event_domain 非法（{module.event_domain}）")
        if module.service_group not in tuple(ServiceGroup):
            errors.append(f"{key}：service_group 非法（{module.service_group}）")
        if not 0 <= module.build_batch <= 3:
            errors.append(f"{key}：build_batch 越界（{module.build_batch}）")
        for field, value in (
            ("service_version", module.service_version),
            ("contract_version", module.contract_version),
        ):
            if not _SEMVER_RE.match(value):
                errors.append(f"{key}：{field} 非 semver（{value}）")
        if module.service_group == ServiceGroup.PRODUCT and not module.product_key:
            errors.append(f"{key}：产品分组缺 product_key")
        if module.service_group != ServiceGroup.PRODUCT and module.product_key:
            errors.append(f"{key}：非产品分组不应有 product_key（{module.product_key}）")
        return errors

    def _validate_duplicates(self) -> list[str]:
        """校验注册要素唯一性（服务键 / 段位仅非空去重）。

        Returns:
            list[str]: 重复明细。
        """
        errors: list[str] = []
        for field in ("module_key", "table_prefix", "event_domain"):
            for duplicate in _duplicates([str(getattr(module, field)) for module in self._modules]):
                errors.append(f"{field} 重复：{duplicate}")
        for optional in ("service_key", "errcode_segment"):
            values = [value for module in self._modules if (value := getattr(module, optional)) is not None]
            for duplicate in _duplicates(values):
                errors.append(f"{optional} 重复：{duplicate}")
        return errors
