"""作业中心接口契约：类型目录 / 监控投影 / 内部提交与本地详情。"""

from __future__ import annotations

from datetime import datetime

from pydantic import ConfigDict, Field

from bms_core.schemas.base import BaseSchema
from bms_core.schemas.pagination import BasePageResponse

__all__ = [
    "JobMonitorItem",
    "JobMonitorPage",
    "JobTypeItem",
    "JobTypePage",
]


class JobTypeItem(BaseSchema):
    """作业类型目录条目。"""

    model_config = ConfigDict(from_attributes=True)

    job_type: str = Field(description="作业类型（全局唯一）")
    service_key: str = Field(description="提供方服务键")
    domain_key: str = Field(description="提供方业务域")
    handler: str = Field(description="执行者点分路径（module:attr）")
    description: str = Field(description="说明")
    timeout_seconds: int = Field(description="单次执行超时（秒）")
    max_attempts: int = Field(description="最大执行次数")
    backoff_seconds: int = Field(description="退避基数（秒）")
    concurrency: int = Field(description="单租户该类型并发上限")
    payload_version: str = Field(description="负载版本")
    status: str = Field(description="目录状态（enabled/deprecated/retired）")
    source: str = Field(description="声明来源（platform/product）")


class JobTypePage(BasePageResponse[JobTypeItem]):
    """作业类型目录分页响应。"""


class JobMonitorItem(BaseSchema):
    """作业监控投影条目。"""

    model_config = ConfigDict(from_attributes=True)

    job_id: int = Field(description="作业标识（雪花 id）")
    service_key: str = Field(description="提供方服务键")
    job_type: str = Field(description="作业类型")
    tenant_id: int | None = Field(default=None, description="租户主键")
    status: str = Field(description="作业状态（queued/running/succeeded/failed/canceled/dead）")
    progress_done: int = Field(description="已完成量")
    progress_total: int | None = Field(default=None, description="总量（NULL = 不确定进度）")
    attempts: int = Field(description="尝试次数")
    error: str | None = Field(default=None, description="错误摘要")
    submitted_at: datetime | None = Field(default=None, description="提交时刻（UTC）")
    started_at: datetime | None = Field(default=None, description="开始时刻（UTC）")
    finished_at: datetime | None = Field(default=None, description="终态时刻（UTC）")
    last_event_at: datetime = Field(description="最近事件时刻（UTC）")


class JobMonitorPage(BasePageResponse[JobMonitorItem]):
    """作业监控列表分页响应。"""
