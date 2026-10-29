"""两段解析的第二段：业务域 → 部署单元与库（协议 + 过渡默认实现 + 租户拓扑实现）。

- **协议**：`TopologyResolver.resolve(domain) -> CapabilityTarget`——接口由 07B `02_02` 定义。
- **过渡默认实现**（`DomainLayoutTopologyResolver`）：业务域 → **该域的承载服务键**，取值来自
  「域 → 服务键」登记视图（装载期由各域声明派生，见 `bms_core.services.module_registry.service_key_for_domain`）；
  基址取「已登记端点覆盖 → 基址模板派生」两段（与服务间调用同口径，见 `bms_core.core.service_endpoints`），
  `mode` 恒 `remote`，`db_keys` 为空集（租户上下文归 07C）。
- **租户拓扑实现**（`TenantTopologyResolver`，07C `02_01`）：业务域 → 租户拓扑登记的部署单元；
  租户取自 `current_tenant_id` 上下文（缺失按默认拓扑），亦可经 `resolve_for(tenant_id, domain)` 显式指定。
  快照按 `(租户, 版本)` 常驻进程内（拓扑只在发布时变化，协议是同步签名）；`db_keys` 只含**平台库键**
  `platform_{unit}`——租户库键 `tenant_{unit}_{db_basis}` 由调用方以自身 `db_basis` 派生（跨域读被 D1/D3 拦截）。
- **失败语义**：统一抛 `CatalogError`（`40003`），`data.reason` 区分 `not_loaded` / `not_registered` / `not_enabled`。
"""

from dataclasses import dataclass
from dataclasses import field as dataclass_field
from typing import Protocol

from bms_core.collaboration.base import CapabilityMode, CapabilityTarget
from bms_core.core.concurrent import (
    ConcurrentStableDict,
    ConcurrentStableFrozenDict,
    ConcurrentStableFrozenList,
)
from bms_core.core.context import current_tenant_id
from bms_core.core.exceptions import CatalogError
from bms_core.core.objects import BaseFrameworkObject, BaseValueObject
from bms_core.db.keys import build_platform_db_key
from bms_core.servicecall.base import DEFAULT_BASE_URL_TEMPLATE, service_base_url
from bms_core.services.module_registry import service_key_for_domain

__all__ = [
    "DEFAULT_TOPOLOGY_TENANT",
    "TOPOLOGY_ENTRY_DISABLED",
    "TOPOLOGY_ENTRY_ENABLED",
    "TOPOLOGY_SNAPSHOT_LIMIT",
    "DomainLayoutTopologyResolver",
    "TenantTopologyResolver",
    "TopologyEntry",
    "TopologyResolver",
    "TopologySnapshot",
    "register_topology_resolver",
    "register_topology_snapshot",
    "reset_topology_resolver",
    "reset_topology_snapshots",
    "resolve_for",
    "resolve_topology",
    "topology_snapshot",
]

DEFAULT_TOPOLOGY_TENANT = 0
"""平台级默认拓扑的租户主键（未单独配置的租户沿用其行集合）。"""

TOPOLOGY_ENTRY_ENABLED = "enabled"
"""拓扑条目状态：本租户启用该业务域（参与解析）。"""

TOPOLOGY_ENTRY_DISABLED = "disabled"
"""拓扑条目状态：本租户停用该业务域（解析报 `not_enabled`，业务态而非配置缺失）。"""

TOPOLOGY_SNAPSHOT_LIMIT = 16
"""进程内快照容量上限（按「租户 × 版本」计；超限淘汰最早登记者，避免无限增长）。"""


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
            base_url_template: 基址模板（占位 `{service}`；缺省沿用既有服务间调用模板；
                该服务已登记端点覆盖时优先取覆盖）。
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
            base_url=service_base_url(service_key, self._base_url_template),
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


@dataclass(frozen=True)
class TopologyEntry(BaseValueObject):
    """一条拓扑条目：某业务域在某租户下由哪个部署单元承载。

    `status` 用协作层自己的词表（与数据模型常量解耦，映射在平台服务内完成）。
    """

    unit_key: str
    """部署单元标识（库名与基址由它派生）。"""

    status: str = TOPOLOGY_ENTRY_ENABLED
    """启用状态（`enabled` / `disabled`）。"""

    @property
    def enabled(self) -> bool:
        """是否启用。

        Returns:
            bool: 启用为 True。
        """
        return self.status == TOPOLOGY_ENTRY_ENABLED


@dataclass(frozen=True)
class TopologySnapshot(BaseValueObject):
    """某租户某一版本的拓扑快照：域 → 条目。"""

    tenant_id: int
    """租户主键（`0` 为默认拓扑）。"""

    version: int
    """拓扑版本（解析取该租户最大版本）。"""

    entries: ConcurrentStableFrozenDict[str, TopologyEntry] = dataclass_field(
        default_factory=lambda: ConcurrentStableFrozenDict[str, TopologyEntry]()
    )
    """`{domain_key: TopologyEntry}`（同一快照内域唯一）。"""


_SNAPSHOTS: ConcurrentStableDict[tuple[int, int], TopologySnapshot] = ConcurrentStableDict()
"""进程内拓扑快照（键为 `(租户, 版本)`；写入即替换该租户的当前版本）。"""

_CURRENT_VERSIONS: ConcurrentStableDict[int, int] = ConcurrentStableDict()
"""各租户当前生效的拓扑版本（`{租户: 版本}`；无记录表示该租户未配置）。"""


def register_topology_snapshot(snapshot: TopologySnapshot) -> None:
    """登记一份拓扑快照（同租户高版本覆盖当前版本；超容量淘汰最早登记）。

    Args:
        snapshot: 拓扑快照。
    """
    _SNAPSHOTS.set((snapshot.tenant_id, snapshot.version), snapshot)
    _CURRENT_VERSIONS.set(snapshot.tenant_id, snapshot.version)
    items = _SNAPSHOTS.to_list()
    while len(items) > TOPOLOGY_SNAPSHOT_LIMIT:
        oldest, _ = items[0]
        _SNAPSHOTS.delete(oldest)
        items = _SNAPSHOTS.to_list()


def reset_topology_snapshots() -> None:
    """清空全部快照（测试隔离用；生产路径不调用）。"""
    _SNAPSHOTS.clear()
    _CURRENT_VERSIONS.clear()


def topology_snapshot(tenant_id: int) -> TopologySnapshot | None:
    """取某租户当前版本的快照（无则回退默认拓扑的快照）。

    Args:
        tenant_id: 租户主键（`0` 为默认拓扑）。

    Returns:
        TopologySnapshot | None: 快照；租户与默认拓扑都没有时返回 None。
    """
    version = _CURRENT_VERSIONS.get(tenant_id)
    if version is not None:
        snapshot = _SNAPSHOTS.get((tenant_id, version))
        if snapshot is not None:
            return snapshot
    if tenant_id == DEFAULT_TOPOLOGY_TENANT:
        return None
    default_version = _CURRENT_VERSIONS.get(DEFAULT_TOPOLOGY_TENANT)
    if default_version is None:
        return None
    return _SNAPSHOTS.get((DEFAULT_TOPOLOGY_TENANT, default_version))


def resolve_for(tenant_id: int, domain: str, *, base_url_template: str = DEFAULT_BASE_URL_TEMPLATE) -> CapabilityTarget:
    """按显式租户解析业务域的部署目标（部署编排 / 运维 / 测试用；协议入口见 `TenantTopologyResolver`）。

    Args:
        tenant_id: 租户主键（`0` 为默认拓扑）。
        domain: 业务域标识。
        base_url_template: 基址模板（占位 `{service}`；取部署单元标识填充）。

    Returns:
        CapabilityTarget: 解析目标（`mode=remote`；`db_keys` 只含平台库键 `platform_{unit}`）。

    Raises:
        CatalogError: 快照未装载（`not_loaded`）/ 域未登记（`not_registered`）/ 域已停用（`not_enabled`）。
    """
    snapshot = topology_snapshot(tenant_id)
    if snapshot is None:
        raise CatalogError(
            f"部署拓扑未装载：租户 {tenant_id}（请检查启动装配是否登记拓扑快照）",
            data={"reason": "not_loaded", "tenant_id": tenant_id, "domain": domain},
        )
    entry = snapshot.entries.get(domain)
    if entry is None:
        raise CatalogError(
            f"业务域未在当前租户的部署拓扑登记：{domain}（租户 {snapshot.tenant_id}）",
            data={"reason": "not_registered", "tenant_id": snapshot.tenant_id, "domain": domain},
        )
    if not entry.enabled:
        raise CatalogError(
            f"业务域未在当前租户启用：{domain}（租户 {snapshot.tenant_id}）",
            data={"reason": "not_enabled", "tenant_id": snapshot.tenant_id, "domain": domain},
        )
    service_key = service_key_for_domain(domain)
    if service_key is None:
        raise CatalogError(
            f"业务域未登记承载服务：{domain}（请检查域声明与清单装载）",
            data={"reason": "not_registered", "tenant_id": snapshot.tenant_id, "domain": domain},
        )
    return CapabilityTarget(
        mode=CapabilityMode.REMOTE,
        unit_key=entry.unit_key,
        service_key=service_key,
        base_url=service_base_url(entry.unit_key, base_url_template),
        db_keys=ConcurrentStableFrozenList([build_platform_db_key(entry.unit_key)]),
    )


class TenantTopologyResolver(BaseFrameworkObject):
    """租户拓扑实现：`resolve(domain)` 取 `current_tenant_id` 上下文，缺失按默认拓扑。

    实现 `TopologyResolver` 协议（结构化契约，不继承——同 `DomainLayoutTopologyResolver`）。
    """

    def __init__(self, base_url_template: str = DEFAULT_BASE_URL_TEMPLATE) -> None:
        """初始化解析器。

        Args:
            base_url_template: 基址模板（占位 `{service}`，按部署单元标识填充）。
        """
        self._base_url_template = base_url_template

    def resolve(self, domain: str) -> CapabilityTarget:
        """解析业务域的部署目标（租户取当前请求上下文）。

        Args:
            domain: 提供方业务域标识。

        Returns:
            CapabilityTarget: 解析目标。

        Raises:
            CatalogError: 快照未装载 / 域未登记 / 域已停用（`data.reason` 区分）。
        """
        return resolve_for(self.tenant_id(), domain, base_url_template=self._base_url_template)

    @staticmethod
    def tenant_id() -> int:
        """取当前租户主键（上下文缺失或非法按默认拓扑）。

        Returns:
            int: 租户主键（`0` 表示默认拓扑）。
        """
        raw = current_tenant_id.get()
        if raw is None:
            return DEFAULT_TOPOLOGY_TENANT
        try:
            return int(raw)
        except TypeError, ValueError:
            return DEFAULT_TOPOLOGY_TENANT
