"""作业监控消费组声明（`job-monitor`）：四条生命周期事件 → `sys_job_monitor` 投影。

- 组名 `job-monitor`（装载时补 `[event_consumer].group_prefix` 前缀）；
- `ordered=True`：同一组内按 `aggregate_key`（`job:{job_id}`）串行，保证同作业事件不乱序；
- 处理器每次启动构造独立实例；写库用平台库短事务。
"""

from __future__ import annotations

from collections.abc import Callable

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.config import get_settings
from bms_core.db.engine import EngineFactory
from bms_core.db.keys import PLATFORM_DB_KEY
from bms_core.db.registry import EngineRegistry
from bms_core.db.session import SessionFactory, session_scope
from bms_core.events.base import EventConsumer, EventEnvelope
from bms_core.events.consumer_records import EventConsumerRecord
from bms_core.jobs.events import (
    JOB_COMPLETED_EVENT,
    JOB_PROGRESS_EVENT,
    JOB_STARTED_EVENT,
    JOB_SUBMITTED_EVENT,
)
from bms_platform.domains.job.repositories.job import JobMonitorRepository
from bms_platform.domains.job.services.monitor import JobMonitorService

__all__ = ["JOB_MONITOR_GROUP", "JobMonitorConsumer", "event_consumer_records", "reset_monitor_registry"]

JOB_MONITOR_GROUP = "job-monitor"
"""消费组名（装载时补前缀，如 `bms-job-monitor`）。"""

_MONITOR_EVENTS = (
    JOB_SUBMITTED_EVENT,
    JOB_STARTED_EVENT,
    JOB_PROGRESS_EVENT,
    JOB_COMPLETED_EVENT,
)
"""监控投影订阅的四条事件。"""

_registry_cache: EngineRegistry | None = None


def _monitor_registry() -> EngineRegistry:
    """取（懒建）平台库引擎注册表。

    Returns:
        EngineRegistry: 引擎注册表。
    """
    global _registry_cache
    if _registry_cache is None:
        _registry_cache = EngineRegistry(EngineFactory(get_settings()))
    return _registry_cache


def reset_monitor_registry() -> None:
    """清空懒建注册表（测试隔离用）。"""
    global _registry_cache
    _registry_cache = None


class JobMonitorConsumer(EventConsumer):
    """单事件处理器：把一条作业事件写入平台投影。"""

    def __init__(self, event_type: str) -> None:
        """初始化。

        Args:
            event_type: 订阅的事件类型。
        """
        self._event_type = event_type

    @property
    def event_type(self) -> str:
        """事件类型（订阅主题）。

        Returns:
            str: 事件类型。
        """
        return self._event_type

    async def consume(self, event: EventEnvelope) -> None:
        """消费一条事件（upsert 投影）。

        Args:
            event: 事件信封。
        """
        async with (
            session_scope(_monitor_registry(), db_key=PLATFORM_DB_KEY, factory=SessionFactory()) as session,
            session.begin(),
        ):
            await JobMonitorService(JobMonitorRepository(session)).apply(event)


def event_consumer_records() -> ConcurrentStableList[EventConsumerRecord]:
    """平台自持的作业监控消费组声明（四条事件各一条记录）。

    Returns:
        ConcurrentStableList[EventConsumerRecord]: 消费组声明。
    """
    records: ConcurrentStableList[EventConsumerRecord] = ConcurrentStableList()
    for event_type in _MONITOR_EVENTS:
        records.add(
            EventConsumerRecord(
                consumer=JOB_MONITOR_GROUP,
                event_type=event_type,
                handler_factory=_factory(event_type),
                ordered=True,
                description=f"作业监控投影：{event_type} → sys_job_monitor",
            )
        )
    return records


def _factory(event_type: str) -> Callable[[], JobMonitorConsumer]:
    """构造处理器工厂（每次返回独立实例）。

    Args:
        event_type: 事件类型。

    Returns:
        Callable[[], JobMonitorConsumer]: 零参工厂。
    """

    def _build() -> JobMonitorConsumer:
        return JobMonitorConsumer(event_type)

    return _build
