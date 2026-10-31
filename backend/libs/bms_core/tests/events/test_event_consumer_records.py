"""消费组声明护栏：自持声明的合并（同值去重 / 异值即拒）与启动校验。

依据《详细设计 · 事件总线》§4.3.1：声明归提供方（服务工厂钩子）、基座统一装载；
校验不得放行「未登记契约」「有序组并行」「同组 ordered 自相矛盾」——这些都会在运行期变成
顺序错乱或空转订阅，必须在启动期 fail-closed。
"""

import pytest

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.exceptions import EventContractError
from bms_core.events.base import EventConsumer, EventEnvelope
from bms_core.events.consumer_records import (
    EventConsumerRecord,
    merge_event_consumer_records,
    qualify_consumer,
    validate_event_consumer_records,
)
from bms_core.events.platform_events import register_platform_event_contracts


class _Handler(EventConsumer):
    """测试处理器（记录收到的事件）。"""

    def __init__(self) -> None:
        """初始化收件箱。"""
        self.seen: ConcurrentStableList[EventEnvelope] = ConcurrentStableList()

    @property
    def event_type(self) -> str:
        """事件类型。"""
        return "sys.user.created"

    async def consume(self, event: EventEnvelope) -> None:
        """消费事件。

        Args:
            event: 事件信封。
        """
        self.seen.add(event)


def _first_handler() -> _Handler:
    """处理器工厂一。"""
    return _Handler()


def _second_handler() -> _Handler:
    """处理器工厂二（与一实现不同，用于冲突判定）。"""
    return _Handler()


def _records(*items: EventConsumerRecord) -> ConcurrentStableList[EventConsumerRecord]:
    """把若干声明打成并发有序集合（契约入参口径）。

    Args:
        *items: 声明。

    Returns:
        ConcurrentStableList[EventConsumerRecord]: 声明集合。
    """
    return ConcurrentStableList(items)


def _record(
    *,
    consumer: str = "audit.chain",
    event_type: str = "sys.user.created",
    handler_factory: object = _first_handler,
    ordered: bool = False,
    concurrency: int | None = None,
) -> EventConsumerRecord:
    """构造一条声明。

    Args:
        consumer: 组名。
        event_type: 事件类型。
        handler_factory: 处理器工厂。
        ordered: 是否全组串行。
        concurrency: 并发覆盖。

    Returns:
        EventConsumerRecord: 声明。
    """
    return EventConsumerRecord(
        consumer=consumer,
        event_type=event_type,
        handler_factory=handler_factory,  # type: ignore[arg-type]
        ordered=ordered,
        concurrency=concurrency,
    )


@pytest.fixture(autouse=True)
def _platform_contracts() -> None:
    """登记平台默认事件契约（幂等；`validate` 依赖契约已登记）。"""
    register_platform_event_contracts()


def test_qualify_consumer_prefixes_bare_name() -> None:
    """裸组名补前缀；已含前缀 / 多段保持原样。"""
    assert qualify_consumer("audit.chain") == "bms.audit.chain"
    assert qualify_consumer("bms.audit.chain") == "bms.audit.chain"
    assert qualify_consumer("audit.chain", group_prefix="bms_x") == "bms_x.audit.chain"


def test_qualify_consumer_keeps_empty() -> None:
    """空组名原样返回（由校验报错，不在补齐阶段吞掉）。"""
    assert qualify_consumer("") == ""


def test_merge_deduplicates_same_declaration() -> None:
    """同 `(组, 事件)` 且同处理器 → 去重保留一条，顺序稳定。"""
    merged = merge_event_consumer_records(_records(_record(), _record()))
    assert len(merged) == 1
    assert merged[0].consumer == "bms.audit.chain"


def test_merge_rejects_conflicting_handlers() -> None:
    """同 `(组, 事件)` 但处理器不同 → 声明漂移，拒。"""
    with pytest.raises(EventContractError, match="声明冲突"):
        merge_event_consumer_records(_records(_record(), _record(handler_factory=_second_handler)))


def test_merge_keeps_distinct_event_types() -> None:
    """同组不同事件 → 两条都在（一组可订阅多个事件）。"""
    merged = merge_event_consumer_records(_records(_record(), _record(event_type="sys.user.updated")))
    assert len(merged) == 2


def test_validate_accepts_registered_contract() -> None:
    """合法声明（已登记契约、组名合规）通过。"""
    records = merge_event_consumer_records(_records(_record()))
    assert list(validate_event_consumer_records(records)) == []


def test_validate_rejects_bad_group_name() -> None:
    """组名不合规（单段 / 大写 / 短横线）→ 拒。"""
    for name in ("audit", "Audit.Chain", "audit-chain.x"):
        errors = validate_event_consumer_records(_records(_record(consumer=name)))
        assert any("消费组名非法" in error for error in errors), name


def test_validate_rejects_bad_event_type() -> None:
    """事件类型形态非法 → 拒。"""
    errors = validate_event_consumer_records(_records(_record(event_type="Sys.User")))
    assert any("订阅事件类型非法" in error for error in errors)


def test_validate_rejects_unregistered_contract() -> None:
    """未登记契约（拼错 / 未申报）→ 拒，防订阅空转。"""
    errors = validate_event_consumer_records(_records(_record(event_type="sys.nothing.happened")))
    assert any("未登记契约" in error for error in errors)


def test_validate_rejects_ordered_with_concurrency() -> None:
    """有序组不得并行（ordered=True 且并发 > 1）。"""
    errors = validate_event_consumer_records(_records(_record(ordered=True, concurrency=2)))
    assert any("有序组不得并行" in error for error in errors)


def test_validate_rejects_non_positive_concurrency() -> None:
    """并发数必须 ≥1。"""
    errors = validate_event_consumer_records(_records(_record(concurrency=0)))
    assert any("并发数非法" in error for error in errors)


def test_validate_rejects_inconsistent_ordered_in_group() -> None:
    """同组内 ordered 声明必须一致（一半串行一半并行 = 顺序语义不明）。"""
    errors = validate_event_consumer_records(
        _records(_record(ordered=True), _record(event_type="sys.user.updated", ordered=False))
    )
    assert any("ordered 声明不一致" in error for error in errors)


def test_validate_rejects_non_callable_factory() -> None:
    """处理器工厂不可调用 → 拒（声明写错比启动后才炸更好）。"""
    errors = validate_event_consumer_records(_records(_record(handler_factory="not-callable")))
    assert any("处理器工厂不可调用" in error for error in errors)
