"""作业监控投影服务：消费四条生命周期事件 → upsert `sys_job_monitor`。

- 按 `job_id` 一作业一行；`last_event_at` 小于等于既有值时丢弃（乱序 / 重放保护）；
- 投影不可重建不影响作业执行，只影响平台统一列表；
- 事件负载字段：`job_id` / `job_type` / `service_key`（全部事件）；
  `status`（submitted / completed）、`attempt`（started）、`progress_done` / `progress_total`（progress）、
  `attempts` / `error`（completed）。
"""

from __future__ import annotations

from typing import cast

from bms_core.core.concurrent import ConcurrentStableDict
from bms_core.events.base import EventEnvelope
from bms_core.jobs.events import (
    JOB_COMPLETED_EVENT,
    JOB_PROGRESS_EVENT,
    JOB_STARTED_EVENT,
    JOB_SUBMITTED_EVENT,
)
from bms_core.jobs.spec import now_utc
from bms_core.models.job import JOB_STATUS_QUEUED, JOB_STATUS_RUNNING
from bms_platform.domains.job.repositories.job import JobMonitorRepository

__all__ = ["JobMonitorService"]


def _int_of(value: object, default: int | None = None) -> int | None:
    """把负载值转为 int（空值返回缺省）。

    Args:
        value: 负载值。
        default: 缺省值。

    Returns:
        int | None: 转换结果。
    """
    if value is None or value == "":
        return default
    return int(str(value))


class JobMonitorService:
    """监控投影写入（事务边界由调用方开启）。"""

    def __init__(self, repository: JobMonitorRepository) -> None:
        """初始化。

        Args:
            repository: 投影仓储。
        """
        self._repo = repository

    async def apply(self, event: EventEnvelope) -> bool:
        """应用一条作业事件（upsert）。

        Args:
            event: 事件信封。

        Returns:
            bool: 写库 True；旧事件被丢弃 / 非作业事件 False。
        """
        payload = event.payload
        job_id = _int_of(payload.get("job_id"))
        if job_id is None:
            return False
        job_type = str(payload.get("job_type") or "")
        service_key = str(payload.get("service_key") or "")
        if not job_type or not service_key:
            return False
        occurred = event.occurred_at if event.occurred_at is not None else now_utc()
        existing = await self._repo.get_by_job_id(job_id)
        if existing is not None and existing.last_event_at >= occurred:
            return False
        values: ConcurrentStableDict[str, object] = ConcurrentStableDict(
            {"job_type": job_type, "service_key": service_key, "last_event_at": occurred}
        )
        if event.event_type == JOB_SUBMITTED_EVENT:
            values.set("status", str(payload.get("status") or JOB_STATUS_QUEUED))
            values.set("submitted_at", occurred)
        elif event.event_type == JOB_STARTED_EVENT:
            values.set("status", JOB_STATUS_RUNNING)
            values.set("started_at", occurred)
            values.set("attempts", _int_of(payload.get("attempt"), 0))
        elif event.event_type == JOB_PROGRESS_EVENT:
            values.set("progress_done", _int_of(payload.get("progress_done"), 0))
            values.set("progress_total", _int_of(payload.get("progress_total")))
            if existing is None:
                values.set("status", JOB_STATUS_RUNNING)
        elif event.event_type == JOB_COMPLETED_EVENT:
            values.set("status", str(payload.get("status") or ""))
            values.set("finished_at", occurred)
            values.set("attempts", _int_of(payload.get("attempts"), 0))
            values.set("error", cast("str | None", payload.get("error")))
        else:
            return False
        if existing is None:
            await self._repo.create_projection(job_id=job_id, **dict(values))
            return True
        await self._repo.update_projection(job_id, now=occurred, **dict(values))
        return True
