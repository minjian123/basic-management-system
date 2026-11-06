"""消息平台端口适配层（07B `06_01` 步 2）：`BaseServiceClient` / `EventPublisher` 的 `msg` 实现。

**为什么单独一层**：协议包（`bms_core.msgclient`）只承诺「帧 + 一元/流式调用 + 韧性」，不认识
bms 的端口契约；端口域（`servicecall` / `events`）只承诺语义，不认识帧。翻译放在这里，
协议包不因端口调整而改、端口不因协议升级而改。

**依赖方向**：`adapter` → `msgclient` + `servicecall` / `events` / `circuit` / `ratelimit` / `oauth`；
没有任何一条反向边。回滚到 `http` 只需删本包与 `core/assembly.py` 的两行登记。
"""

from bms_core.msgclient.adapter.event_publisher import MsgEventPublisher
from bms_core.msgclient.adapter.mapping import method_of, query_headers, request_payload, to_bms_error
from bms_core.msgclient.adapter.policy import (
    PolicyCircuitBreaker,
    circuit_scope,
    deadline_ms_of,
    default_circuit,
    release_circuit,
    retry_policy_of,
)
from bms_core.msgclient.adapter.service_client import MsgServiceClient

__all__ = [
    "MsgEventPublisher",
    "MsgServiceClient",
    "PolicyCircuitBreaker",
    "circuit_scope",
    "deadline_ms_of",
    "default_circuit",
    "method_of",
    "query_headers",
    "release_circuit",
    "request_payload",
    "retry_policy_of",
    "to_bms_error",
]
