"""批量消费契约护栏：缺省逐条实现、单条失败隔离、链键派生声明。

依据《详细设计 · 01_05 审计链消费性能优化》§4.3：批量契约只在处理器需要时覆盖，
既有处理器不改；单条失败不得连坐整批。
"""

from __future__ import annotations

import pytest

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.events.base import BatchConsumeOutcome, EventConsumer, EventEnvelope

pytestmark = pytest.mark.kiwi_id(2370)


def _event(event_id: str) -> EventEnvelope:
    """构造最小事件信封。

    Args:
        event_id: 事件 ID。

    Returns:
        EventEnvelope: 事件信封。
    """
    return EventEnvelope(event_type="sys.operation.logged", payload=ConcurrentStableDict(), event_id=event_id)


class _Handler(EventConsumer):
    """按事件 ID 决定成功 / 失败的处理器替身。"""

    def __init__(self, *, fail_ids: ConcurrentStableList[str]) -> None:
        """初始化。

        Args:
            fail_ids: 需要抛错的事件 ID。
        """
        self._fail_ids = fail_ids
        self.consumed: ConcurrentStableList[str] = ConcurrentStableList()

    @property
    def event_type(self) -> str:
        """事件类型。"""
        return "sys.operation.logged"

    async def consume(self, event: EventEnvelope) -> None:
        """消费一条事件（命中失败清单即抛错）。"""
        if event.event_id in self._fail_ids:
            raise RuntimeError(f"boom:{event.event_id}")
        self.consumed.add(event.event_id or "")


async def test_default_consume_batch_isolates_single_failure() -> None:
    """缺省实现逐条调用 `consume`；单条失败只标记该条，其余照常成功且顺序不变。"""
    handler = _Handler(fail_ids=ConcurrentStableList(["e-2"]))
    outcomes = await handler.consume_batch(ConcurrentStableList([_event("e-1"), _event("e-2"), _event("e-3")]))
    assert [item.kind for item in outcomes] == ["succeeded", "failed", "succeeded"]
    assert outcomes[1].retryable is True
    assert "boom:e-2" in (outcomes[1].error or "")
    assert list(handler.consumed) == ["e-1", "e-3"]
    assert [item.event_id for item in outcomes] == ["e-1", "e-2", "e-3"]


def test_batch_outcome_defaults() -> None:
    """结果值对象缺省：可重试、无错误。"""
    outcome = BatchConsumeOutcome(event_id="e-1", kind="succeeded")
    assert outcome.retryable is True
    assert outcome.error is None
