"""事件消费组声明：**各产品（服务）自持**、基座统一装载的记录与合并 / 校验。

口径与 `FormRecord` / `CapabilityUsage` 同构——清单在提供方（服务的 `event_consumer_records()`
钩子），基座不改常量、不设进程级注册表，装配期统一合并成应用级视图：

- **声明** `EventConsumerRecord`：组名 + 订阅事件类型 + 处理器工厂 + 有序 / 并发覆盖。
  用**工厂**而非实例：每次进程独立构造，避免跨进程 / 跨测试共享状态，服务未启用消费时也不白建对象。
- **合并** `merge_event_consumer_records`：按 `(consumer, event_type)` 去重——同值（处理器实现相同）
  跳过、**异值即拒**（组名与事件撞车但处理器不同 = 声明漂移）。
- **校验** `validate_event_consumer_records`：组名 / 事件名形态、契约已登记、有序与并发不冲突、
  同组有序声明一致；返回违规明细（空 = 通过），启动期 fail-closed 拒启。
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import cast

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.exceptions import EventContractError
from bms_core.core.objects import BaseValueObject
from bms_core.events.base import EventConsumer
from bms_core.events.contracts import (
    EVENT_TYPE_RE,
    EventContractRegistry,
    default_event_contract_registry,
    resolve_event_contract,
)

__all__ = [
    "CONSUMER_NAME_RE",
    "DEFAULT_GROUP_PREFIX",
    "EventConsumerRecord",
    "merge_event_consumer_records",
    "qualify_consumer",
    "validate_event_consumer_records",
]

CONSUMER_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$")
"""消费组名形态：点分小写、至少两段（`{group_prefix}.{域}`，如 `bms.audit.chain`）。"""

DEFAULT_GROUP_PREFIX = "bms"
"""消费组名缺省前缀（`[event_consumer].group_prefix` 未配置时）。"""


@dataclass(frozen=True)
class EventConsumerRecord(BaseValueObject):
    """消费组声明（服务自持；基座合并后装载进组运行器）。

    Attributes:
        consumer: 组名（`{group_prefix}.{域}`；不含前缀时由装载方补齐）。
        event_type: 订阅的事件类型（须已登记契约）。
        handler_factory: 处理器工厂（每次启动构造独立实例）。
        ordered: 是否全组串行（True → 该组 lane 固定 1，审计链组等强顺序场景）。
        concurrency: 组级并发（lane 数）覆盖；None 取 `[event_consumer].concurrency`。
        description: 说明（中文，供启动日志与排障）。
    """

    consumer: str
    event_type: str
    handler_factory: Callable[[], EventConsumer]
    ordered: bool = False
    concurrency: int | None = None
    description: str = ""


def qualify_consumer(consumer: str, *, group_prefix: str = DEFAULT_GROUP_PREFIX) -> str:
    """补齐组名前缀（已含前缀 / 多段组名保持原样）。

    Args:
        consumer: 组名（如 `audit.chain` 或 `bms.audit.chain`）。
        group_prefix: 组名前缀（`[event_consumer].group_prefix`）。

    Returns:
        str: 限定后的组名。
    """
    if not consumer:
        return consumer
    prefix = (group_prefix or DEFAULT_GROUP_PREFIX).strip().strip(".")
    if not prefix or consumer == prefix or consumer.startswith(f"{prefix}."):
        return consumer
    return f"{prefix}.{consumer}"


def merge_event_consumer_records(
    records: ConcurrentStableList[EventConsumerRecord], *, group_prefix: str = DEFAULT_GROUP_PREFIX
) -> ConcurrentStableList[EventConsumerRecord]:
    """合并多来源声明（插入序稳定；同值去重、异值即拒）。

    Args:
        records: 各服务自持的声明（平台 + 产品）。
        group_prefix: 组名前缀。

    Returns:
        ConcurrentStableList[EventConsumerRecord]: 合并后的声明（保序）。

    Raises:
        EventContractError: 同 `(consumer, event_type)` 出现不同处理器实现（声明漂移）。
    """
    merged: ConcurrentStableList[EventConsumerRecord] = ConcurrentStableList()
    seen: ConcurrentStableDict[tuple[str, str], EventConsumerRecord] = ConcurrentStableDict()
    for record in records:
        qualified = EventConsumerRecord(
            consumer=qualify_consumer(record.consumer, group_prefix=group_prefix),
            event_type=record.event_type,
            handler_factory=record.handler_factory,
            ordered=record.ordered,
            concurrency=record.concurrency,
            description=record.description,
        )
        key = (qualified.consumer, qualified.event_type)
        existing = seen.get(key)
        if existing is None:
            seen[key] = qualified
            merged.add(qualified)
            continue
        if _factory_key(existing.handler_factory) != _factory_key(qualified.handler_factory):
            raise EventContractError(
                f"消费组声明冲突（同组同事件不同处理器）：{qualified.consumer} ← {qualified.event_type}"
            )
    return merged


def validate_event_consumer_records(
    records: ConcurrentStableList[EventConsumerRecord],
    *,
    registry: EventContractRegistry | None = None,
) -> ConcurrentStableList[str]:
    """校验消费组声明（启动期 fail-closed；空清单通过）。

    Args:
        records: 声明清单。
        registry: 事件契约注册表（缺省默认注册表）。

    Returns:
        ConcurrentStableList[str]: 违规明细；空 = 通过。
    """
    errors: ConcurrentStableList[str] = ConcurrentStableList()
    ordered_by_group: ConcurrentStableDict[str, bool] = ConcurrentStableDict()
    contract_registry = registry or default_event_contract_registry()
    for record in records:
        label = f"{record.consumer} ← {record.event_type}"
        if not record.consumer or not CONSUMER_NAME_RE.fullmatch(record.consumer):
            errors.add(f"消费组名非法（应为点分小写、至少两段）：{record.consumer!r}")
        if not EVENT_TYPE_RE.fullmatch(record.event_type):
            errors.add(f"订阅事件类型非法：{label}")
        elif resolve_event_contract(record.event_type, registry=contract_registry) is None:
            errors.add(f"订阅的事件未登记契约：{label}")
        if not callable(record.handler_factory):
            errors.add(f"处理器工厂不可调用：{label}")
        if record.concurrency is not None and record.concurrency < 1:
            errors.add(f"并发数非法（应 ≥1）：{label}（{record.concurrency}）")
        if record.ordered and record.concurrency is not None and record.concurrency > 1:
            errors.add(f"有序组不得并行（ordered=True 时并发只能为 1）：{label}（{record.concurrency}）")
        previous = ordered_by_group.get(record.consumer)
        if previous is None:
            ordered_by_group[record.consumer] = record.ordered
        elif previous != record.ordered:
            errors.add(f"同组内 ordered 声明不一致：{record.consumer}（{previous} 与 {record.ordered}）")
    return errors


def _factory_key(factory: Callable[[], EventConsumer]) -> str:
    """处理器工厂的标识（用于「同值去重 / 异值即拒」判定）。

    Args:
        factory: 处理器工厂。

    Returns:
        str: 工厂标识（缺 `__qualname__` 时回落 `repr`）。
    """
    qualname = getattr(factory, "__qualname__", None)
    return cast("str", qualname) if qualname else repr(factory)
