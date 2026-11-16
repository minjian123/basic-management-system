"""审计事件暂存缓冲（06_02）：请求级「先暂存、收尾统一发射」。

- **用途**：显式留痕（三权分立拒绝、账号锁定处置等**不写库**的判定场景）经 `AuditCapturer.capture()`
  得到事件，但捕获发生在业务代码里、当时没有可用的事务边界——先暂存到本模块，由审计中间件在响应
  收尾统一发射（平台库短事务；失败只告警，不改变已定的业务结果）。
- **作用域**：`ContextVar` 按请求 / 任务上下文隔离，不跨请求泄漏；中间件排空后清空。
- **与字段级捕获的分工**：写库路径由 ORM 会话事件在**业务事务内**直接入发件箱（`field_capture.py`），
  不走本缓冲；本缓冲只服务「无实体变更」的显式留痕。
"""

from __future__ import annotations

from contextvars import ContextVar

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.events.base import EventEnvelope

__all__ = ["drain_staged", "reset_staged", "stage_event", "staged_count"]

_STAGED: ContextVar[ConcurrentStableList[EventEnvelope] | None] = ContextVar("bms_audit_staged", default=None)
"""当前上下文的暂存事件（懒建；排空后置空）。"""


def _buffer() -> ConcurrentStableList[EventEnvelope]:
    """取（懒建）当前上下文的事件缓冲。

    Returns:
        ConcurrentStableList[EventEnvelope]: 事件缓冲。
    """
    buffer = _STAGED.get()
    if buffer is None:
        buffer = ConcurrentStableList[EventEnvelope]()
        _STAGED.set(buffer)
    return buffer


def stage_event(event: EventEnvelope) -> None:
    """暂存一条审计事件（同上下文可多次调用）。

    Args:
        event: 审计事件信封。
    """
    _buffer().add(event)


def staged_count() -> int:
    """当前上下文暂存事件数（观测 / 测试用）。

    Returns:
        int: 暂存事件数。
    """
    buffer = _STAGED.get()
    return 0 if buffer is None else len(buffer)


def drain_staged() -> ConcurrentStableList[EventEnvelope]:
    """取出并清空当前上下文暂存事件。

    Returns:
        ConcurrentStableList[EventEnvelope]: 暂存事件（插入序；无则空列表）。
    """
    buffer = _STAGED.get()
    _STAGED.set(None)
    return ConcurrentStableList[EventEnvelope]() if buffer is None else ConcurrentStableList(buffer)


def reset_staged() -> None:
    """清空当前上下文暂存事件（**测试隔离用**，不发射）。"""
    _STAGED.set(None)
