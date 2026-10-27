"""schemas 层能力分配授权契约（07B `02_04`）：管理面记录 / 授予请求 / 内部授权视图项。

字段与 `sys_capability_grant` 对齐（表结构以表文件为准）；内部视图段只暴露「能力 × 消费方 +
提供方业务域与访问面类别」，不含 `note` / `granted_by` 等运营字段（运营面走管理面端点）。
"""

from datetime import datetime
from typing import Annotated

from pydantic import Field

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.schemas.base import CONTRACT_COLLECTION, BaseSchema


class CapabilityGrantResponse(BaseSchema):
    """授权记录响应（与 `sys_capability_grant` 对齐；`id` 序列化为字符串）。"""

    id: int
    capability_name: str
    consumer_key: str
    source: str
    status: str
    expire_at: datetime | None
    granted_by: int | None
    granted_at: datetime | None
    revoked_at: datetime | None
    note: str | None


class CapabilityGrantCreateRequest(BaseSchema):
    """人工授予请求（幂等 UPSERT 同一「能力 × 消费方」行）。

    `expire_at` 与 `note` **成对出现**：临时授权（排障 / 迁移窗口）必须给有效期与理由，
    避免长期留存的排障授权；长期授权可不填有效期。
    """

    capability_name: Annotated[str, Field(min_length=1, max_length=128, description="能力名（须已登记）")]
    consumer_key: Annotated[str, Field(min_length=1, max_length=64, description="消费方服务键（须已登记）")]
    expire_at: Annotated[datetime | None, Field(description="有效期截止（UTC；空=长期有效）")] = None
    note: Annotated[str, Field(max_length=255, description="授予理由（临时授权必填）")] = ""


class CapabilityGrantViewItem(BaseSchema):
    """内部授权视图项（服务间读取：谁能调谁）。"""

    capability_name: str
    consumer_key: str
    domain: str
    kind: str
    expire_at: datetime | None


class CapabilityGrantViewResponse(BaseSchema):
    """内部授权视图响应（按 `provider` 或 `consumer` 维度下发）。"""

    provider: str | None
    consumer: str | None
    grants: Annotated[ConcurrentStableList[CapabilityGrantViewItem], CONTRACT_COLLECTION]
