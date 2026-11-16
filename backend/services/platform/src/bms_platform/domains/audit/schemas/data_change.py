"""数据变更审计接口契约：列表 / 详情 / 链校验（06_02）。"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from pydantic import ConfigDict, Field

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.schemas.base import CONTRACT_COLLECTION, CONTRACT_STABLE_LIST, BaseSchema, SnowflakeIdStr
from bms_core.schemas.pagination import BasePageResponse

__all__ = [
    "ChainVerifyView",
    "DataChangeItem",
    "DataChangePage",
]


class DataChangeItem(BaseSchema):
    """字段级变更审计条目（列表 / 详情同构）。"""

    model_config = ConfigDict(from_attributes=True)

    id: SnowflakeIdStr = Field(description="审计主键")
    event_id: str = Field(description="事件幂等键")
    tenant_id: SnowflakeIdStr | None = Field(default=None, description="租户主键")
    table_name: str = Field(description="被审计的逻辑表名")
    record_id: SnowflakeIdStr | None = Field(default=None, description="被审计记录主键")
    field: str = Field(description="变更字段名")
    old_value: str | None = Field(default=None, description="变更前值（JSON 文本；敏感列 ***）")
    new_value: str | None = Field(default=None, description="变更后值（JSON 文本；敏感列 ***）")
    operator_id: SnowflakeIdStr | None = Field(default=None, description="操作人主键")
    domain_key: str = Field(description="业务域归属")
    occurred_at: datetime = Field(description="事件发生时间（UTC）")
    prev_hash: str = Field(description="前一条记录哈希")
    record_hash: str = Field(description="本条记录哈希")
    created_at: datetime = Field(description="写入时间（UTC）")


class DataChangePage(BasePageResponse[DataChangeItem]):
    """数据变更审计分页响应。"""


class ChainVerifyView(BaseSchema):
    """链校验结果（数据变更审计）。"""

    log_type: str = Field(description="日志类型（固定 data_audit）")
    valid: bool = Field(description="链是否完整")
    checked_months: Annotated[ConcurrentStableList[str], CONTRACT_COLLECTION] = Field(
        default_factory=CONTRACT_STABLE_LIST, description="实际校验月份"
    )
    checked_records: int = Field(description="校验记录数")
    broken_month: str | None = Field(default=None, description="断裂分片月份")
    broken_index: int | None = Field(default=None, description="断裂位置（月内从 0 起）")
    broken_record_id: SnowflakeIdStr | None = Field(default=None, description="断裂记录主键")
