"""RPC 调用值对象（07B 06_01 步 1 上移）：客户端与服务端共用的数据契约。

`RpcRegistry` 与其 Handler 协议留在产品仓服务端（装配态），本模块只承载**数据形状**，
使基座客户端与产品服务端共用同一类型，不产生第二份定义。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from bms_core.core.concurrent import ConcurrentStableDict
from bms_core.core.roots import BaseValueObject

__all__ = ["RpcCall", "RpcReply"]


@dataclass(frozen=True)
class RpcCall(BaseValueObject):
    """一次调用的入参（handler 侧契约；冻结实例，handler 改不动它）。"""

    service: str
    """服务标识（取自路径 `{service}`）。"""

    method: str
    """方法名（取自路径 `{method}`）。"""

    payload: bytes
    """调用参数原始字节（broker 不解析、不解压）。"""

    headers: ConcurrentStableDict[str, str]
    """结构化头（透传给 handler；handler 可据此做业务分支）。"""

    tenant: str
    """租户编码（已由数据面解析链判定；本任务只透传，不做授权）。"""

    trace_id: str | None = None
    """链路标识（透传进 handler 与日志）。"""

    caller: str | None = None
    """调用方服务标识（HTTP 头优先，见详细设计 §9.2；非鉴权字段）。"""

    deadline_ms: int | None = None
    """向下游传播的剩余预算（毫秒；任务 04-2）。

    已扣本跳服务端耗时并减去返回余量（`RPC_RETURN_RESERVE_MS`），即详细设计 §6 的 `downstream`：
    handler 若要继续调下游，应把这个值原样放进下一次调用的 `deadline_ms`。`None` 表示「未给预算」
    （只有直接构造 `RpcCall` 的单元场景会出现；运行期两形态恒给值）。

    **流式下每帧重算**（04-3-1）：处理器若在迭代中途继续调下游，取到的必须是当下剩余预算，
    否则一条跑了两分钟的长流会把「开局时的剩余」当成还能用两分钟。
    """

    retry_budget: int | None = None
    """调用链剩余可重试次数（04-4）：从请求帧头 `retry_budget` 透传。

    handler 继续调下游时应把它原样放进下一次 `call(retry_budget=...)`，与 `deadline_ms` 的
    逐跳扣减同构——每跳都受同一上限约束，A→B→C 不会各重试 2 次凑成 8 次。
    """

    idempotency_key: str | None = None
    """本次调用的幂等键业务部分（04-4；服务端已按作用域拼接去重，handler 只读）。"""


def _empty_headers() -> ConcurrentStableDict[str, str]:
    """空结果头（dataclass 默认工厂；显式标注泛型，避免 strict 模式下退化成 Unknown）。"""

    return ConcurrentStableDict()


@dataclass(frozen=True)
class RpcReply(BaseValueObject):
    """一次调用的结果 / 流式的一帧结果（handler 侧契约）。"""

    payload: bytes = b""
    """结果原始字节（帧形态直接进 payload 段，JSON 形态转 base64）。"""

    headers: ConcurrentStableDict[str, str] = field(default_factory=_empty_headers)
    """结果结构化头（回显给调用方 / 逐帧回显）。"""
