"""跨产品协同能力寻址（07B `02_02`）：单点取用入口 + 两段解析 + 三档失败语义。

- `resolve_capability(name)`：**唯一**取用入口（能力名 → 访问面与解析目标；缺失 / 禁用即抛，不返回空值）；
- `CapabilityEndpoint` / `CapabilityTarget` / `CapabilityMode`：冻结返回模型与部署模式；
- `TopologyResolver` / `register_topology_resolver()`：第二段解析协议与替换点（真实实现归 07C `02_02`）；
- `CapabilityUsage` / `call_capability()`：消费方降级声明与统一执行入口（写 / 强一致路径不得声明降级）；
- `build_capability_request()`：由取用结果构造 `ServiceRequest`（消费方不自拼服务键与路径）；
- `find_undeclared_degradations()`：无声明降级的护栏扫描（`03_01` 收编后对消费方零命中）。
"""

from bms_core.collaboration.base import (
    WRITE_KINDS,
    CapabilityEndpoint,
    CapabilityMode,
    CapabilityTarget,
)
from bms_core.collaboration.guard import find_undeclared_degradations
from bms_core.collaboration.request import build_capability_request
from bms_core.collaboration.resolver import resolve_capability
from bms_core.collaboration.topology import (
    DomainLayoutTopologyResolver,
    TopologyResolver,
    register_topology_resolver,
    reset_topology_resolver,
    resolve_topology,
)
from bms_core.collaboration.usage import (
    DEGRADE_EMPTY,
    DEGRADE_MODES,
    DEGRADE_NONE,
    DEGRADE_STALE,
    METRIC_CAPABILITY_DEGRADE,
    METRIC_CAPABILITY_RESOLVE_ERROR,
    CapabilityUsage,
    call_capability,
    capability_usage_view,
    capability_usages,
    find_capability_usage,
    inspect_capability_usages,
    register_capability_usages,
    reset_capability_usages,
    validate_capability_usages,
)

__all__ = [
    "DEGRADE_EMPTY",
    "DEGRADE_MODES",
    "DEGRADE_NONE",
    "DEGRADE_STALE",
    "METRIC_CAPABILITY_DEGRADE",
    "METRIC_CAPABILITY_RESOLVE_ERROR",
    "WRITE_KINDS",
    "CapabilityEndpoint",
    "CapabilityMode",
    "CapabilityTarget",
    "CapabilityUsage",
    "DomainLayoutTopologyResolver",
    "TopologyResolver",
    "build_capability_request",
    "call_capability",
    "capability_usage_view",
    "capability_usages",
    "find_capability_usage",
    "find_undeclared_degradations",
    "inspect_capability_usages",
    "register_capability_usages",
    "register_topology_resolver",
    "reset_capability_usages",
    "reset_topology_resolver",
    "resolve_capability",
    "resolve_topology",
    "validate_capability_usages",
]
