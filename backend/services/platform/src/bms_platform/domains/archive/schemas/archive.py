"""归档管理接口契约：策略 / 执行记录 / 归档数据 / 触发与销毁。"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

from pydantic import ConfigDict, Field

from bms_core.core.concurrent import ConcurrentStableDict
from bms_core.schemas.base import CONTRACT_COLLECTION, BaseSchema, SnowflakeIdStr
from bms_core.schemas.pagination import BasePageResponse

__all__ = [
    "ArchiveDataDestroyRequest",
    "ArchiveDataItem",
    "ArchiveDataPage",
    "ArchiveDataQuery",
    "ArchiveDeleteResult",
    "ArchiveLogDestroyRequest",
    "ArchiveLogItem",
    "ArchiveLogPage",
    "ArchivePolicyCreateRequest",
    "ArchivePolicyItem",
    "ArchivePolicyPage",
    "ArchivePolicyUpdateRequest",
    "ArchiveTriggerResult",
    "PresignedDownload",
]


class ArchivePolicyItem(BaseSchema):
    """归档策略（列表 / 详情同构）。"""

    model_config = ConfigDict(from_attributes=True)

    id: SnowflakeIdStr = Field(description="策略主键")
    table_name: str = Field(description="逻辑表名")
    time_field: str = Field(description="归档判定时间字段")
    threshold_days: int = Field(description="阈值天数")
    retention_days: int = Field(description="归档库保留天数")
    target: str = Field(description="归档目标（archive_db / minio）")
    batch_size: int = Field(description="单批迁移条数")
    status: str = Field(description="状态（enabled / disabled）")
    require_chain: bool = Field(description="是否强制哈希链校验")
    remark: str | None = Field(default=None, description="备注")
    version: int = Field(description="乐观锁版本")


class ArchivePolicyPage(BasePageResponse[ArchivePolicyItem]):
    """归档策略分页响应。"""


class ArchivePolicyCreateRequest(BaseSchema):
    """新增归档策略。"""

    table_name: str = Field(min_length=1, max_length=64, description="逻辑表名（须为平台库已登记表）")
    time_field: str = Field(min_length=1, max_length=64, description="归档判定时间字段")
    threshold_days: int = Field(default=90, ge=0, description="阈值天数")
    retention_days: int = Field(default=180, ge=0, description="归档库保留天数")
    target: str = Field(default="archive_db", description="归档目标（archive_db / minio）")
    batch_size: int | None = Field(
        default=None, ge=1, description="单批迁移条数（缺省取 [archive].batch_size_default）"
    )
    status: str = Field(default="enabled", description="初始状态（enabled / disabled）")
    require_chain: bool = Field(default=False, description="归档前强制哈希链校验（审计分片表强制 true）")
    remark: str | None = Field(default=None, max_length=256, description="备注")


class ArchivePolicyUpdateRequest(BaseSchema):
    """修改归档策略（乐观锁：`version` 必填）。"""

    time_field: str | None = Field(default=None, min_length=1, max_length=64, description="归档判定时间字段")
    threshold_days: int | None = Field(default=None, ge=0, description="阈值天数")
    retention_days: int | None = Field(default=None, ge=0, description="归档库保留天数")
    target: str | None = Field(default=None, description="归档目标（archive_db / minio）")
    batch_size: int | None = Field(default=None, ge=1, description="单批迁移条数")
    status: str | None = Field(default=None, description="状态（enabled / disabled）")
    require_chain: bool | None = Field(default=None, description="归档前强制哈希链校验")
    remark: str | None = Field(default=None, max_length=256, description="备注")
    version: int = Field(ge=1, description="乐观锁版本（取详情里的当前值）")


class ArchiveLogItem(BaseSchema):
    """归档执行记录（列表 / 详情同构）。"""

    model_config = ConfigDict(from_attributes=True)

    id: SnowflakeIdStr = Field(description="执行记录主键")
    policy_id: SnowflakeIdStr | None = Field(default=None, description="策略主键")
    table_name: str = Field(description="源逻辑表名")
    target: str = Field(description="动作 / 目标")
    tenant_id: SnowflakeIdStr | None = Field(default=None, description="租户主键（平台级批次为空）")
    archived_count: int = Field(description="本次处理条数")
    file_key: str | None = Field(default=None, description="冷化数据对象 key")
    status: str = Field(description="状态（running/success/failed/skipped）")
    cost_time: int | None = Field(default=None, description="耗时（毫秒）")
    started_at: datetime = Field(description="开始时间（UTC）")
    finished_at: datetime | None = Field(default=None, description="结束时间（UTC）")
    error_msg: str | None = Field(default=None, description="失败摘要")
    detail: str | None = Field(default=None, description="明细 JSON")
    retention_until: datetime | None = Field(default=None, description="冷化文件保留到期时刻（UTC）")
    disposed_at: datetime | None = Field(default=None, description="文件处置时刻（UTC）")
    dispose_type: str | None = Field(default=None, description="处置类型（cleanup / destroy）")


class ArchiveLogPage(BasePageResponse[ArchiveLogItem]):
    """归档执行记录分页响应。"""


class ArchiveDataQuery(BaseSchema):
    """归档数据查询筛选。"""

    source_table: str | None = Field(default=None, max_length=64, description="源逻辑表名")
    source_id: str | None = Field(default=None, max_length=64, description="源行主键")
    source_month: str | None = Field(default=None, min_length=6, max_length=6, description="源分片月份（yyyyMM）")
    tenant_id: SnowflakeIdStr | None = Field(default=None, description="租户主键（审计管理员可跨租户）")
    stored_from: datetime | None = Field(default=None, description="归档起始时刻（UTC）")
    stored_to: datetime | None = Field(default=None, description="归档结束时刻（UTC）")


class ArchiveDataItem(BaseSchema):
    """归档数据行（元数据 + 源行载荷）。"""

    id: SnowflakeIdStr = Field(description="归档行主键")
    tenant_id: SnowflakeIdStr | None = Field(default=None, description="租户主键")
    source_table: str = Field(description="源逻辑表名")
    source_id: str = Field(description="源行主键")
    source_month: str | None = Field(default=None, description="源分片月份")
    policy_id: SnowflakeIdStr = Field(description="策略主键")
    batch_id: SnowflakeIdStr = Field(description="归档批次主键")
    archived_at: datetime = Field(description="归档时刻（UTC）")
    payload: Annotated[ConcurrentStableDict[str, Any], CONTRACT_COLLECTION] = Field(description="源行完整字段")


class ArchiveDataPage(BasePageResponse[ArchiveDataItem]):
    """归档数据分页响应。"""


class ArchiveTriggerResult(BaseSchema):
    """手动触发结果。"""

    job_id: SnowflakeIdStr = Field(description="作业主键")
    policy_id: SnowflakeIdStr = Field(description="策略主键")


class ArchiveDeleteResult(BaseSchema):
    """删除结果。"""

    id: SnowflakeIdStr = Field(description="策略主键")
    deleted: bool = Field(description="是否已删除")


class ArchiveLogDestroyRequest(BaseSchema):
    """销毁某批冷化文件。"""

    confirm: bool = Field(default=False, description="二次确认（必须为 true，否则 93006）")


class ArchiveDataDestroyRequest(BaseSchema):
    """销毁单条归档行。"""

    source_table: str = Field(min_length=1, max_length=64, description="源逻辑表名")
    source_id: str = Field(min_length=1, max_length=64, description="源行主键")
    confirm: bool = Field(default=False, description="二次确认（必须为 true，否则 93006）")


class PresignedDownload(BaseSchema):
    """冷化文件预签名下载。"""

    url: str = Field(description="预签名 URL")
    expires_in: int = Field(description="有效期（秒）")
    method: str = Field(description="HTTP 方法")
    file_key: str = Field(description="对象 key")
