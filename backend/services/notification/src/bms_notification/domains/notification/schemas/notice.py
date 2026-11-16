"""公告请求 / 响应契约：新建 / 编辑 / 列表 / 详情 / 回执 / 统计 / 内部过期。

时间字段统一 UTC；请求可带时区，服务层转换为 UTC naive 后入库。多语言入参只提交
`locale → {title, content}` 映射，主表默认文案列由服务端派生。
"""

from datetime import datetime
from typing import Annotated

from pydantic import Field, field_validator

from bms_core.core.concurrent import ConcurrentStableDict
from bms_core.schemas.base import CONTRACT_COLLECTION, BaseSchema, SnowflakeIdStr
from bms_notification.domains.notification.notice_constants import (
    NOTICE_PRIORITY_DEFAULT,
    NOTICE_STATUSES,
    NOTICE_TYPE_DEFAULT,
)

__all__ = [
    "NoticeCreateRequest",
    "NoticeDetail",
    "NoticeExpireRequest",
    "NoticeExpireResult",
    "NoticeListItem",
    "NoticeReadReceipt",
    "NoticeReadStats",
    "NoticeTextInput",
    "NoticeTextOutput",
    "NoticeUpdateRequest",
]


class NoticeTextInput(BaseSchema):
    """公告单语言文案入参。"""

    title: str = Field(min_length=1, max_length=256, description="标题（该语言）")
    content: str = Field(default="", max_length=60000, description="正文 HTML（该语言；草稿可空）")


class NoticeTextOutput(BaseSchema):
    """公告单语言文案出参。"""

    title: str = Field(description="标题（该语言）")
    content: str = Field(default="", description="正文 HTML（该语言）")


class NoticeCreateRequest(BaseSchema):
    """新建公告请求（草稿或直接发布）。"""

    i18n: Annotated[ConcurrentStableDict[str, NoticeTextInput], CONTRACT_COLLECTION] = Field(
        description="语言标识 → 文案（至少一种语言；发布时正文必填）"
    )
    type: str = Field(default=NOTICE_TYPE_DEFAULT, max_length=32, description="公告类型（选项集值）")
    priority: str = Field(default=NOTICE_PRIORITY_DEFAULT, max_length=16, description="优先级（选项集值）")
    is_top: bool = Field(default=False, description="是否置顶")
    publish_at: datetime | None = Field(default=None, description="发布时间（UTC；缺省当前时间）")
    expire_at: datetime | None = Field(default=None, description="过期时间（UTC；空 = 永不过期）")
    publish: bool = Field(default=True, description="是否直接发布（false = 保存草稿）")


class NoticeUpdateRequest(BaseSchema):
    """编辑公告请求（字段均可选；`i18n` 提供时整体替换）。"""

    i18n: Annotated[ConcurrentStableDict[str, NoticeTextInput], CONTRACT_COLLECTION] = Field(
        default_factory=lambda: ConcurrentStableDict[str, NoticeTextInput](),
        description="语言标识 → 文案（提供时整体替换；空映射表示不改文案）",
    )
    type: str | None = Field(default=None, max_length=32, description="公告类型（选项集值）")
    priority: str | None = Field(default=None, max_length=16, description="优先级（选项集值）")
    is_top: bool | None = Field(default=None, description="是否置顶")
    publish_at: datetime | None = Field(default=None, description="发布时间（UTC；缺省保持原值）")
    expire_at: datetime | None = Field(default=None, description="过期时间（UTC；显式 null 表示清除）")
    publish: bool | None = Field(default=None, description="true = 草稿发布；false = 拒绝；缺省保持状态")

    @field_validator("type")
    @classmethod
    def _type_not_empty(cls, value: str | None) -> str | None:
        """类型非空白（值域由选项集运行时校验）。

        Args:
            value: 原始类型值。

        Returns:
            str | None: 校验后的值。

        Raises:
            ValueError: 显式传空串。
        """
        if value is not None and not value.strip():
            raise ValueError("公告类型不得为空")
        return value

    @field_validator("priority")
    @classmethod
    def _priority_not_empty(cls, value: str | None) -> str | None:
        """优先级非空白（值域由选项集运行时校验）。

        Args:
            value: 原始优先级值。

        Returns:
            str | None: 校验后的值。

        Raises:
            ValueError: 显式传空串。
        """
        if value is not None and not value.strip():
            raise ValueError("公告优先级不得为空")
        return value


class NoticeListItem(BaseSchema):
    """公告列表行（不含正文，减少列表载荷）。"""

    id: SnowflakeIdStr = Field(description="公告主键")
    title: str = Field(description="标题（按请求语言本地化）")
    type: str = Field(description="公告类型")
    priority: str = Field(description="优先级")
    is_top: bool = Field(description="是否置顶")
    status: str = Field(description="状态（draft / published / offline）")
    publish_at: datetime = Field(description="发布时间（UTC）")
    expire_at: datetime | None = Field(default=None, description="过期时间（UTC）")
    is_read: bool = Field(default=False, description="当前用户是否已读（管理列表为当前用户视角）")
    created_at: datetime = Field(description="创建时间（UTC）")
    updated_at: datetime = Field(description="更新时间（UTC）")

    @field_validator("status")
    @classmethod
    def _status_known(cls, value: str) -> str:
        """状态必须在闭集内。

        Args:
            value: 状态值。

        Returns:
            str: 状态值。

        Raises:
            ValueError: 未知状态。
        """
        if value not in NOTICE_STATUSES:
            raise ValueError(f"公告状态非法：{value}")
        return value


class NoticeDetail(NoticeListItem):
    """公告详情（含正文；管理侧另含完整多语言映射）。"""

    content: str = Field(default="", description="正文 HTML（按请求语言本地化）")
    i18n: Annotated[ConcurrentStableDict[str, NoticeTextOutput] | None, CONTRACT_COLLECTION] = Field(
        default=None, description="完整多语言映射（仅管理侧返回）"
    )


class NoticeReadReceipt(BaseSchema):
    """已读回执响应（幂等：重复阅读返回首次时间）。"""

    notice_id: SnowflakeIdStr = Field(description="公告主键")
    read_at: datetime = Field(description="首次阅读时间（UTC）")


class NoticeReadStats(BaseSchema):
    """已读统计响应（应读 = 当前租户启用用户数）。"""

    notice_id: SnowflakeIdStr = Field(description="公告主键")
    audience_count: int = Field(ge=0, description="应读人数（当前租户启用用户数）")
    read_count: int = Field(ge=0, description="已读人数（回执去重用户数）")
    unread_count: int = Field(ge=0, description="未读人数（max(应读 - 已读, 0)）")


class NoticeExpireRequest(BaseSchema):
    """内部过期扫描请求。"""

    limit: int = Field(default=200, ge=1, le=1000, description="单批上限")
    now: datetime | None = Field(default=None, description="基准时间（UTC；缺省服务端当前时间，测试用）")


class NoticeExpireResult(BaseSchema):
    """内部过期扫描结果。"""

    expired: int = Field(default=0, ge=0, description="本次下线公告数")
