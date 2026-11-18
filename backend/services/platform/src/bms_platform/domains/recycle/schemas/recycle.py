"""回收站接口契约：模块 / 列表 / 详情 / 恢复 / 清理批次记录。"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from pydantic import ConfigDict, Field

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.schemas.base import CONTRACT_COLLECTION, BaseSchema, SnowflakeIdStr
from bms_core.schemas.pagination import BasePageResponse

__all__ = [
    "RecycleCleanupItem",
    "RecycleCleanupPage",
    "RecycleDetailResponse",
    "RecycleItem",
    "RecycleItemPage",
    "RecycleModuleItem",
    "RecycleModulesResponse",
    "RecycleRestoreRequest",
    "RecycleRestoreResult",
    "RecycleTableItem",
]


class RecycleTableItem(BaseSchema):
    """模块内单表删除计数。"""

    table: str = Field(description="逻辑表名")
    label: str = Field(description="中文表名")
    deleted_count: int = Field(ge=0, description="软删除条数")


class RecycleModuleItem(BaseSchema):
    """模块分组（含表计数）。"""

    module_key: str = Field(description="模块标识")
    module_label: str = Field(description="模块中文名")
    deleted_count: int = Field(ge=0, description="模块内软删除总条数")
    tables: Annotated[ConcurrentStableList[RecycleTableItem], CONTRACT_COLLECTION] = Field(description="模块内表清单")


class RecycleModulesResponse(BaseSchema):
    """模块 / 表清单响应。"""

    items: Annotated[ConcurrentStableList[RecycleModuleItem], CONTRACT_COLLECTION] = Field(description="模块分组")


class RecycleItem(BaseSchema):
    """软删除列表行。"""

    table: str = Field(description="逻辑表名")
    id: SnowflakeIdStr = Field(description="记录主键")
    title: str = Field(description="展示标题")
    deleted_at: datetime = Field(description="删除时间（UTC）")
    deleted_by: SnowflakeIdStr | None = Field(default=None, description="删除人")


class RecycleItemPage(BasePageResponse[RecycleItem]):
    """软删除列表分页响应。"""


class RecycleDetailResponse(BaseSchema):
    """软删除详情（展示列快照）。"""

    table: str = Field(description="逻辑表名")
    id: SnowflakeIdStr = Field(description="记录主键")
    title: str = Field(description="展示标题")
    deleted_at: datetime = Field(description="删除时间（UTC）")
    deleted_by: SnowflakeIdStr | None = Field(default=None, description="删除人")
    created_at: datetime = Field(description="创建时间（UTC）")
    updated_at: datetime = Field(description="更新时间（UTC）")
    fields: Annotated[ConcurrentStableDict[str, str], CONTRACT_COLLECTION] = Field(
        description="展示列（中文标签 → 文本值）"
    )


class RecycleRestoreRequest(BaseSchema):
    """恢复请求。"""

    table: str = Field(min_length=1, max_length=64, description="逻辑表名（须在回收站纳管范围）")
    id: SnowflakeIdStr = Field(description="记录主键")


class RecycleRestoreResult(BaseSchema):
    """恢复结果。"""

    table: str = Field(description="逻辑表名")
    id: SnowflakeIdStr = Field(description="记录主键")
    title: str = Field(description="展示标题")
    restored: bool = Field(description="是否恢复成功")
    cascaded: Annotated[ConcurrentStableDict[str, int], CONTRACT_COLLECTION] = Field(
        description="级联恢复计数（子表 → 条数）"
    )


class RecycleCleanupItem(BaseSchema):
    """清理批次记录行。"""

    model_config = ConfigDict(from_attributes=True)

    id: SnowflakeIdStr = Field(description="批次行主键")
    batch_key: str = Field(description="批次键")
    table_name: str = Field(description="被清理的逻辑表名")
    status: str = Field(description="状态（running / success / failed）")
    retention_days: int = Field(description="保留天数")
    cutoff_at: datetime = Field(description="清理截止时刻（UTC）")
    deleted_count: int = Field(ge=0, description="物理删除条数")
    cost_time: int | None = Field(default=None, description="耗时（毫秒）")
    started_at: datetime = Field(description="开始时间（UTC）")
    finished_at: datetime | None = Field(default=None, description="结束时间（UTC）")
    error_msg: str | None = Field(default=None, description="失败摘要")


class RecycleCleanupPage(BasePageResponse[RecycleCleanupItem]):
    """清理批次记录分页响应。"""
