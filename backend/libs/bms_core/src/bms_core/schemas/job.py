"""作业中心接口契约（基座共享）：内部提交 / 取消 / 本地详情。

平台用户面的类型目录 / 监控投影契约归 `bms_platform.domains.job.schemas`，不在此处。
"""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from bms_core.schemas.base import BaseSchema, SnowflakeIdStr

__all__ = ["JobActionResponse", "JobCancelRequest", "JobInternalItem", "JobSubmitRequest"]


class JobSubmitRequest(BaseSchema):
    """内部提交作业请求。"""

    job_type: str = Field(min_length=3, max_length=128, description="作业类型（须属于本服务声明）")
    payload: dict[str, object] = Field(default_factory=dict, description="负载 JSON 对象")
    priority: int = Field(default=0, description="租户内优先级（大者先）")
    idempotency_key: str | None = Field(default=None, max_length=128, description="提交幂等键")
    max_attempts: int | None = Field(default=None, ge=1, description="最大执行次数（缺省取声明）")
    payload_version: str | None = Field(default=None, max_length=16, description="负载版本（缺省取声明）")


class JobCancelRequest(BaseSchema):
    """取消作业请求。"""

    reason: str | None = Field(default=None, max_length=256, description="取消原因")


class JobActionResponse(BaseSchema):
    """取消 / 重试结果。"""

    status: str = Field(description="处理结果（canceled/requested/retried）")


class JobInternalItem(BaseSchema):
    """内部本地作业详情（含结果与错误摘要）。"""

    job_id: SnowflakeIdStr = Field(description="作业标识")
    job_type: str = Field(description="作业类型")
    status: str = Field(description="状态")
    tenant_id: SnowflakeIdStr | None = Field(default=None, description="租户主键")
    progress_done: int = Field(description="已完成量")
    progress_total: int | None = Field(default=None, description="总量")
    attempts: int = Field(description="尝试次数")
    max_attempts: int = Field(description="最大执行次数")
    error: str | None = Field(default=None, description="错误摘要")
    result: str | None = Field(default=None, description="结果 JSON（截断后的原文）")
    created_at: datetime | None = Field(default=None, description="提交时刻（UTC）")
    started_at: datetime | None = Field(default=None, description="开始时刻（UTC）")
    finished_at: datetime | None = Field(default=None, description="终态时刻（UTC）")
