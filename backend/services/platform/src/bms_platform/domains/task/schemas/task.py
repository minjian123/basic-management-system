"""任务调度接口契约：任务定义 / 执行记录 / 手动触发结果。"""

from __future__ import annotations

from datetime import datetime

from pydantic import ConfigDict, Field

from bms_core.schemas.base import BaseSchema
from bms_core.schemas.pagination import BasePageResponse

__all__ = [
    "TaskCreateRequest",
    "TaskItem",
    "TaskLogItem",
    "TaskLogPage",
    "TaskPage",
    "TaskTriggerResult",
    "TaskUpdateRequest",
]


class TaskItem(BaseSchema):
    """任务定义（列表 / 详情同构）。"""

    model_config = ConfigDict(from_attributes=True)

    id: int = Field(description="任务主键")
    code: str = Field(description="任务代码（唯一）")
    name: str = Field(description="任务名（唯一）")
    handler: str = Field(description="执行体（`module:attr`）")
    cron: str | None = Field(default=None, description="调度表达式（NULL=仅手动触发）")
    args: str | None = Field(default=None, description="参数原文（JSON 对象或数组）")
    status: str = Field(description="状态（enabled/disabled）")
    last_run_at: datetime | None = Field(default=None, description="最近一次派发时间（UTC）")
    next_run_at: datetime | None = Field(default=None, description="下次到期时间（UTC）")
    remark: str | None = Field(default=None, description="备注")
    version: int = Field(description="乐观锁版本")


class TaskPage(BasePageResponse[TaskItem]):
    """任务列表分页响应。"""


class TaskLogItem(BaseSchema):
    """执行记录。"""

    model_config = ConfigDict(from_attributes=True)

    id: int = Field(description="记录主键")
    task_id: int = Field(description="任务主键")
    run_id: str | None = Field(default=None, description="本次执行标识")
    trigger_source: str = Field(description="触发来源（schedule/manual）")
    status: str = Field(description="执行状态（running/success/failed/skipped）")
    retry_count: int = Field(description="已重试次数")
    started_at: datetime | None = Field(default=None, description="开始时间（UTC）")
    finished_at: datetime | None = Field(default=None, description="结束时间（UTC）")
    cost_time: int | None = Field(default=None, description="耗时（毫秒）")
    result: str | None = Field(default=None, description="成功输出摘要")
    error_msg: str | None = Field(default=None, description="错误摘要")


class TaskLogPage(BasePageResponse[TaskLogItem]):
    """执行记录分页响应。"""


class TaskCreateRequest(BaseSchema):
    """新建任务。"""

    code: str = Field(min_length=1, max_length=64, description="任务代码（唯一；同时是内置 handler 的注册键）")
    name: str = Field(min_length=1, max_length=128, description="任务名（唯一）")
    handler: str = Field(min_length=3, max_length=256, description="执行体（`module:attr`，须在白名单内）")
    cron: str | None = Field(default=None, max_length=64, description="调度表达式（留空=仅手动触发）")
    args: str | None = Field(default=None, description="参数原文（JSON 对象或数组）")
    remark: str | None = Field(default=None, max_length=256, description="备注")
    status: str = Field(default="enabled", description="初始状态（enabled/disabled）")


class TaskUpdateRequest(BaseSchema):
    """修改任务（乐观锁：`version` 必填）。"""

    name: str | None = Field(default=None, min_length=1, max_length=128, description="任务名")
    handler: str | None = Field(default=None, min_length=3, max_length=256, description="执行体")
    cron: str | None = Field(default=None, max_length=64, description="调度表达式")
    args: str | None = Field(default=None, description="参数原文")
    remark: str | None = Field(default=None, max_length=256, description="备注")
    version: int = Field(ge=1, description="乐观锁版本（取详情里的当前值）")


class TaskTriggerResult(BaseSchema):
    """手动触发结果（已落记录并入队）。"""

    log_id: int = Field(description="执行记录主键")
    run_id: str = Field(description="本次执行标识")
