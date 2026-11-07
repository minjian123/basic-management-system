"""扩展点声明与装配校验能力域（07D `02_01` ~ `02_05`）：产品声明「需要哪些扩展点」、基座核对。

**为什么需要**：四类标准扩展点（作用域校验 / 错误码映射 / 配额回显 / 审计字段）与资源级 ACL
都由产品在 `configure_plugins()` 内登记实现。登记是**代码调用**，缺实现时只会在「某次请求才解析」
那一刻暴露（`PluginError` 或 500）——运行期才发现的配置错配。本域把「产品需要什么」变成
**启动期可核对的声明**：必需项缺失即拒启，可选项按声明跳过。

口径：

- **不落库**：扩展点实现本身是代码（`register_plugin`），声明再落一份会形成「代码注册 + 数据库声明」
  两份事实源；跨产品治理看插件清单接口（`GET /api/v1/plugins`）。
- **有序**：声明列表顺序即同 `order` 下的稳定次序（规则链按 `(order, 声明序)` 排序）。
- **一次汇总**：必需项缺失时汇总全部缺失项再抛错，便于一次改完。
- **只做核对**：不解析实现、不实例化（解析仍由各能力域的 `resolve_plugin` 负责）。
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from bms_core.core.concurrent import (
    ConcurrentStableFrozenSet,
    ConcurrentStableList,
)
from bms_core.core.exceptions import PluginError
from bms_core.core.logging import get_logger
from bms_core.core.objects import BaseValueObject
from bms_core.core.plugin import PluginImpl, plugin_registry_snapshot

__all__ = [
    "AUDIT_EXTENSION_KEY",
    "DEFAULT_EXTENSION_ORDER",
    "ERROR_MAPPING_KEY",
    "EXTENSION_POINT_KEYS",
    "EXTENSION_REQUIREMENT_NAME_RE",
    "MAX_EXTENSION_ORDER",
    "MIN_EXTENSION_ORDER",
    "QUOTA_PROJECTION_KEY",
    "RESOURCE_ACL_KEY",
    "SCOPE_RULE_KEY",
    "ExtensionRequirement",
    "requirements_by_key",
    "verify_extension_requirements",
]

_LOGGER = get_logger("bms.extension")

SCOPE_RULE_KEY = "scope_rule"
"""作用域校验第四步规则（需求 02-1；端口 `resource_scope/rules.py::BaseScopeRule`）。"""

ERROR_MAPPING_KEY = "error_mapping"
"""错误码映射（需求 02-2；内建实现名 `declaration`，映射数据来自 `[[errcodes]].maps_from`）。"""

QUOTA_PROJECTION_KEY = "quota_projection"
"""配额只读回显（需求 02-3；内建实现名 `declaration`，投影数据来自 `kind=quota` 数据源）。"""

AUDIT_EXTENSION_KEY = "audit_extension"
"""审计字段扩展（需求 02-4；内建实现名 `declaration`，类别来自 `audit_classes()` 声明）。"""

RESOURCE_ACL_KEY = "resource_acl"
"""资源级 ACL（需求 02-5；**不是第五类标准扩展点**，仅共用同一装配登记机制）。"""

EXTENSION_POINT_KEYS: ConcurrentStableFrozenSet[str] = ConcurrentStableFrozenSet(
    (SCOPE_RULE_KEY, ERROR_MAPPING_KEY, QUOTA_PROJECTION_KEY, AUDIT_EXTENSION_KEY, RESOURCE_ACL_KEY)
)
"""扩展点键取值集合（声明里出现集合外的键即配置非法，装配期拒启）。"""

EXTENSION_REQUIREMENT_NAME_RE = re.compile(r"^[a-z][a-z0-9_.]*$")
"""实现名形态（与 `register_plugin` 登记名同口径；允许点分，如 `msg.namespace`）。"""

DEFAULT_EXTENSION_ORDER = 100
"""扩展点执行序缺省值（小者先）。"""

MIN_EXTENSION_ORDER = 0
"""执行序下限。"""

MAX_EXTENSION_ORDER = 999
"""执行序上限。"""


@dataclass(frozen=True)
class ExtensionRequirement(BaseValueObject):
    """一条扩展点需求声明：扩展点键 + 实现名 + 必需性 + 执行序。"""

    plugin_key: str
    """扩展点键（必须是 `EXTENSION_POINT_KEYS` 之一）。"""

    plugin_name: str
    """实现名（与 `register_plugin` 登记名一致；如 `msg.namespace` / `declaration`）。"""

    required: bool = True
    """必需（缺失即拒启）/ 可选（缺失按声明跳过）。"""

    order: int = DEFAULT_EXTENSION_ORDER
    """执行序（仅同键多实现时有意义；取值 `0~999`）。"""

    def __post_init__(self) -> None:
        """形态校验（声明是启动期输入，非法即拒，不做容错）。

        Raises:
            PluginError: 扩展点键未知 / 实现名形态非法 / 执行序越界。
        """
        if self.plugin_key not in EXTENSION_POINT_KEYS:
            known = "、".join(sorted(EXTENSION_POINT_KEYS))
            raise PluginError(f"扩展点键未知：{self.plugin_key!r}（合法取值：{known}）")
        if not EXTENSION_REQUIREMENT_NAME_RE.match(self.plugin_name):
            raise PluginError(f"扩展点实现名形态非法：{self.plugin_key}:{self.plugin_name!r}（须小写标识符）")
        if not MIN_EXTENSION_ORDER <= self.order <= MAX_EXTENSION_ORDER:
            raise PluginError(
                f"扩展点执行序越界：{self.plugin_key}:{self.plugin_name} → {self.order}"
                f"（须在 {MIN_EXTENSION_ORDER}~{MAX_EXTENSION_ORDER}）"
            )

    @property
    def label(self) -> str:
        """可读标识（错误信息与日志用）。

        Returns:
            str: `plugin_key:plugin_name`。
        """
        return f"{self.plugin_key}:{self.plugin_name}"


def _registered(  # bare-collections:allow（注册表只读快照入参）
    snapshot: Mapping[str, Mapping[str, PluginImpl]], requirement: ExtensionRequirement
) -> bool:
    """判定实现是否已登记（注册表只读快照）。

    Args:
        snapshot: 插件注册表快照（`plugin_key → {plugin_name → 实现}`）。
        requirement: 扩展点需求。

    Returns:
        bool: 已登记为 True。
    """
    bucket = snapshot.get(requirement.plugin_key)
    return bucket is not None and requirement.plugin_name in bucket


def verify_extension_requirements(
    requirements: Iterable[ExtensionRequirement],
    *,
    snapshot: Mapping[str, Mapping[str, PluginImpl]] | None = None,  # bare-collections:allow（只读快照入参）
    product_label: str = "",
) -> ConcurrentStableList[ExtensionRequirement]:
    """核对扩展点声明（注册表冻结后调用）：必需缺失即拒启，可选缺失按声明跳过。

    Args:
        requirements: 产品声明的扩展点需求（有序；同 `order` 下按声明序执行）。
        snapshot: 插件注册表快照；`None` 取默认注册表（须已 `build_plugin_registry()`）。
        product_label: 产品标识（错误信息定位用；空表示未提供）。

    Returns:
        ConcurrentStableList[ExtensionRequirement]: **生效清单**（必需项 + 已注册的可选项），顺序保持声明序。

    Raises:
        PluginError: 扩展点键非法、实现名非法、执行序越界，或必需实现未登记（一次性汇总）。
    """
    view = plugin_registry_snapshot() if snapshot is None else snapshot
    label = f"{product_label}｜" if product_label else ""
    effective: ConcurrentStableList[ExtensionRequirement] = ConcurrentStableList()
    missing_required: ConcurrentStableList[str] = ConcurrentStableList()
    skipped: ConcurrentStableList[str] = ConcurrentStableList()
    for requirement in requirements:
        if _registered(view, requirement):
            effective.add(requirement)
            continue
        if requirement.required:
            missing_required.add(requirement.label)
        else:
            skipped.add(requirement.label)
    if skipped:
        _LOGGER.info(
            "extension_skipped",
            product=product_label or None,
            entries="、".join(skipped),
        )
    if missing_required:
        raise PluginError(
            f"{label}必需扩展点未注册：{'、'.join(missing_required)}"
            "（在 `configure_plugins()` 内 `register_plugin(...)` 登记，或改为可选声明）"
        )
    return effective


def requirements_by_key(
    requirements: Iterable[ExtensionRequirement], plugin_key: str
) -> ConcurrentStableList[ExtensionRequirement]:
    """按扩展点键筛选并按 `(order, 声明序)` 排序。

    Args:
        requirements: 生效清单（`verify_extension_requirements()` 的返回值）。
        plugin_key: 扩展点键（如 `scope_rule`）。

    Returns:
        ConcurrentStableList[ExtensionRequirement]: 该键的声明（有序副本）。
    """
    selected: ConcurrentStableList[ExtensionRequirement] = ConcurrentStableList(
        item for item in requirements if item.plugin_key == plugin_key
    )
    # bare-collections:allow（局部排序缓冲，随即转入并发安全集合）
    ordered_items = sorted(selected, key=lambda item: item.order)
    return ConcurrentStableList(ordered_items)
