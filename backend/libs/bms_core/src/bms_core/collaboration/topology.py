"""两段解析的第二段：业务域 → 部署单元与库（协议 + 过渡默认实现）。

- **协议**：`TopologyResolver.resolve(domain) -> CapabilityTarget`——接口由本任务定义，
  真实实现（租户拓扑 + `local` / `colocated` 判定）归 07C `02_02`，以 `register_topology_resolver()`
  替换即可，**消费方代码不改**。
- **过渡默认实现**（`DomainLayoutTopologyResolver`）：业务域 → **该域的承载服务键**，取值来自
  「域 → 服务键」登记视图（装载期由各仓 `deploy/boundaries/domain_layout.json` 派生，
  见 `bms_core.services.module_registry.service_key_for_domain`）；基址按既有模板
  （`DEFAULT_BASE_URL_TEMPLATE`），`mode` 恒 `remote`，`db_keys` 为空集（租户上下文归 07C）。
- **失败语义**：域未登记 → 抛 `CatalogError`（装载期已校验，运行期属配置漂移，同属拒启级）。
"""

from typing import Protocol

from bms_core.collaboration.base import CapabilityMode, CapabilityTarget
from bms_core.core.exceptions import CatalogError
from bms_core.core.objects import BaseFrameworkObject
from bms_core.servicecall.base import DEFAULT_BASE_URL_TEMPLATE
from bms_core.services.module_registry import service_key_for_domain

__all__ = [
    "DomainLayoutTopologyResolver",
    "TopologyResolver",
    "register_topology_resolver",
    "reset_topology_resolver",
    "resolve_topology",
]


class TopologyResolver(Protocol):
    """第二段解析协议：业务域 → 部署单元与库（实现可替换，消费方零改动）。"""

    def resolve(self, domain: str) -> CapabilityTarget:
        """解析业务域的部署目标。

        Args:
            domain: 提供方业务域标识。

        Returns:
            CapabilityTarget: 解析目标。

        Raises:
            CatalogError: 业务域未在部署拓扑登记（配置缺失，拒启级）。
        """
        ...


class DomainLayoutTopologyResolver(BaseFrameworkObject):
    """过渡默认实现：业务域 → 域布局登记的承载服务键（行为与改造前等价）。"""

    def __init__(self, base_url_template: str = DEFAULT_BASE_URL_TEMPLATE) -> None:
        """初始化解析器。

        Args:
            base_url_template: 基址模板（占位 `{service}`；缺省沿用既有服务间调用模板）。
        """
        self._base_url_template = base_url_template

    def resolve(self, domain: str) -> CapabilityTarget:
        """解析业务域的部署目标（服务键取域布局登记）。

        Args:
            domain: 提供方业务域标识。

        Returns:
            CapabilityTarget: 解析目标（`mode=remote`、`unit_key` 取业务域、`db_keys` 空集）。

        Raises:
            CatalogError: 业务域未登记承载服务（配置缺失，拒启级）。
        """
        service_key = service_key_for_domain(domain)
        if service_key is None:
            raise CatalogError(
                f"业务域未在部署拓扑登记：{domain}"
                "（请检查 deploy/boundaries/domain_layout.json 的 service_key 与产品清单装载）"
            )
        return CapabilityTarget(
            mode=CapabilityMode.REMOTE,
            unit_key=domain,
            service_key=service_key,
            base_url=self._base_url_template.format(service=service_key).rstrip("/"),
        )


_active_resolver: TopologyResolver | None = None
"""已替换的第二段解析实现（None 表示使用过渡默认实现；07C `02_02` 装配期登记）。"""


def register_topology_resolver(resolver: TopologyResolver) -> None:
    """登记第二段解析实现（替换过渡默认实现；重复登记以后者为准）。

    Args:
        resolver: 实现 `TopologyResolver` 协议的对象。
    """
    global _active_resolver
    _active_resolver = resolver


def reset_topology_resolver() -> None:
    """复位为过渡默认实现（测试隔离用；生产路径不调用）。"""
    global _active_resolver
    _active_resolver = None


def resolve_topology() -> TopologyResolver:
    """取当前生效的第二段解析实现。

    Returns:
        TopologyResolver: 已登记实现；未登记时为过渡默认实现。
    """
    return _active_resolver if _active_resolver is not None else DomainLayoutTopologyResolver()
