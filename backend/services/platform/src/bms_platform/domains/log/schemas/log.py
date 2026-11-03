"""审计日志接口契约：操作 / 登录日志列表与详情、链校验、分片预创建（06_01）。"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from pydantic import ConfigDict, Field

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.schemas.base import CONTRACT_COLLECTION, CONTRACT_STABLE_LIST, BaseSchema, SnowflakeIdStr
from bms_core.schemas.pagination import BasePageResponse

__all__ = [
    "EnsureShardsRequest",
    "EnsureShardsResult",
    "LoginLogItem",
    "LoginLogPage",
    "OperationLogItem",
    "OperationLogPage",
    "VerifyRequest",
    "VerifyResult",
]


class OperationLogItem(BaseSchema):
    """操作日志列表 / 详情同构。"""

    model_config = ConfigDict(from_attributes=True)

    id: SnowflakeIdStr = Field(description="日志主键")
    event_id: str = Field(description="事件幂等键")
    tenant_id: SnowflakeIdStr | None = Field(default=None, description="租户主键")
    user_id: SnowflakeIdStr | None = Field(default=None, description="操作人主键")
    username: str | None = Field(default=None, description="操作账号快照")
    module: str = Field(description="模块")
    action: str = Field(description="动作（权限码 / 回落动词）")
    method: str = Field(description="HTTP 方法")
    path: str = Field(description="请求路径")
    query_params: str | None = Field(default=None, description="查询串（已脱敏）")
    params: str | None = Field(default=None, description="请求体参数 JSON（已脱敏）")
    ip: str | None = Field(default=None, description="客户端 IP")
    user_agent: str | None = Field(default=None, description="User-Agent")
    cost_time: int | None = Field(default=None, description="耗时（毫秒）")
    status: int = Field(description="HTTP 状态码")
    error_msg: str | None = Field(default=None, description="错误摘要")
    occurred_at: datetime = Field(description="事件发生时间（UTC）")
    prev_hash: str = Field(description="前一条记录哈希")
    record_hash: str = Field(description="本条记录哈希")
    created_at: datetime = Field(description="写入时间（UTC）")


class OperationLogPage(BasePageResponse[OperationLogItem]):
    """操作日志分页响应。"""


class LoginLogItem(BaseSchema):
    """登录日志列表 / 详情同构。"""

    model_config = ConfigDict(from_attributes=True)

    id: SnowflakeIdStr = Field(description="日志主键")
    event_id: str = Field(description="事件幂等键")
    tenant_id: SnowflakeIdStr | None = Field(default=None, description="租户主键")
    user_id: SnowflakeIdStr | None = Field(default=None, description="命中用户主键")
    username: str = Field(description="登录名")
    ip: str | None = Field(default=None, description="客户端 IP")
    user_agent: str | None = Field(default=None, description="User-Agent")
    status: str = Field(description="结果（success / failed）")
    fail_reason: str | None = Field(default=None, description="失败原因")
    occurred_at: datetime = Field(description="事件发生时间（UTC）")
    prev_hash: str = Field(description="前一条记录哈希")
    record_hash: str = Field(description="本条记录哈希")
    created_at: datetime = Field(description="写入时间（UTC）")


class LoginLogPage(BasePageResponse[LoginLogItem]):
    """登录日志分页响应。"""


class VerifyRequest(BaseSchema):
    """链校验请求（内部端点 / 巡检任务）。"""

    log_type: str = Field(description="日志类型（operation / login）")
    months: Annotated[ConcurrentStableList[str], CONTRACT_COLLECTION] | None = Field(
        default=None, description="指定月份（yyyyMM；空 = 台账全部）"
    )


class VerifyResult(BaseSchema):
    """链校验结果。"""

    log_type: str = Field(description="日志类型")
    valid: bool = Field(description="链是否完整")
    checked_months: Annotated[ConcurrentStableList[str], CONTRACT_COLLECTION] = Field(
        default_factory=CONTRACT_STABLE_LIST, description="实际校验月份"
    )
    checked_records: int = Field(description="校验记录数")
    broken_month: str | None = Field(default=None, description="断裂分片月份")
    broken_index: int | None = Field(default=None, description="断裂位置（月内从 0 起）")
    broken_record_id: SnowflakeIdStr | None = Field(default=None, description="断裂记录主键")


class EnsureShardsRequest(BaseSchema):
    """分片预创建请求。"""

    months_ahead: int = Field(default=1, ge=0, description="提前月数（0 = 仅当月）")


class EnsureShardsResult(BaseSchema):
    """分片预创建结果。"""

    months: Annotated[ConcurrentStableList[str], CONTRACT_COLLECTION] = Field(
        default_factory=CONTRACT_STABLE_LIST, description="已确保存在的月份（含当月）"
    )
