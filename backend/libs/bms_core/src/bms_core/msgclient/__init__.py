"""调用方侧出口（任务 04-1 / 04-2 / 04-3-2）：RPC 客户端（一元 + 流式句柄）。

**基座通用能力**（07B 06_01）：本包自持帧编解码、值对象、预算判据与传输层，不 import 任何产品仓
模块；各产品仓经路径依赖天然获得客户端，无需额外部署或跨仓装配，协议实现只有一份。

**流式从本包出口给 `RpcStream`**：`RpcClient.stream()` 的返回类型与入口同处一层，产品侧适配
（8B_03）只需依赖 `bms_core.msgclient`。
"""

from bms_core.msgclient.circuit import InProcessCircuitBreaker
from bms_core.msgclient.errors import ErrorCategory, Outcome
from bms_core.msgclient.instances import (
    InstanceLease,
    InstanceOutcome,
    InstancePolicy,
    InstanceProvider,
    InstanceSelector,
    InstanceSnapshot,
    InstanceStrategy,
    StaticInstanceProvider,
    StaticInstanceSelector,
    selector_for,
)
from bms_core.msgclient.retry import CircuitPolicy, RetryBudget, RetryPolicy
from bms_core.msgclient.rpc import (
    InstanceUnavailableError,
    RpcCallError,
    RpcCallTimeoutError,
    RpcClient,
)
from bms_core.msgclient.stream import RpcStream

__all__ = [
    "CircuitPolicy",
    "ErrorCategory",
    "InProcessCircuitBreaker",
    "InstanceLease",
    "InstanceOutcome",
    "InstancePolicy",
    "InstanceProvider",
    "InstanceSelector",
    "InstanceSnapshot",
    "InstanceStrategy",
    "InstanceUnavailableError",
    "Outcome",
    "RetryBudget",
    "RetryPolicy",
    "RpcCallError",
    "RpcCallTimeoutError",
    "RpcClient",
    "RpcStream",
    "StaticInstanceProvider",
    "StaticInstanceSelector",
    "selector_for",
]
