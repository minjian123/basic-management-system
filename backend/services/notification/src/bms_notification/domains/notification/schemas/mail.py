"""邮件模板 / 发送 / 日志接口契约。"""

from datetime import datetime
from typing import Annotated

from pydantic import Field, field_validator

from bms_core.core.concurrent import ConcurrentStableDict
from bms_core.schemas.base import CONTRACT_COLLECTION, BaseSchema, SnowflakeIdStr
from bms_notification.domains.notification.delivery_constants import DELIVERY_STATUSES
from bms_notification.domains.notification.mail_constants import (
    MAIL_TEMPLATE_CODE_PATTERN,
    MAIL_TEMPLATE_STATUS_ENABLED,
    MAIL_TEMPLATE_STATUSES,
)

__all__ = [
    "MailLogItem",
    "MailSendRequest",
    "MailSendResult",
    "MailTemplateCreateRequest",
    "MailTemplateDetail",
    "MailTemplateListItem",
    "MailTemplatePreviewRequest",
    "MailTemplatePreviewResult",
    "MailTemplateTestRequest",
    "MailTemplateTestResult",
    "MailTemplateUpdateRequest",
    "MailTextInput",
    "MailTextOutput",
]


class MailTextInput(BaseSchema):
    """邮件单语言文案入参。"""

    subject: str = Field(min_length=1, max_length=256, description="主题（该语言）")
    content: str = Field(default="", max_length=60000, description="正文 Jinja2 / HTML（该语言）")


class MailTextOutput(BaseSchema):
    """邮件单语言文案出参。"""

    subject: str = Field(description="主题（该语言）")
    content: str = Field(default="", description="正文 Jinja2 / HTML（该语言）")


class MailTemplateCreateRequest(BaseSchema):
    """新建邮件模板请求（code 与内置默认相同即覆盖）。"""

    code: str = Field(pattern=MAIL_TEMPLATE_CODE_PATTERN, description="模板 code（创建后不可改）")
    name: str = Field(min_length=1, max_length=128, description="模板名称")
    status: str = Field(default=MAIL_TEMPLATE_STATUS_ENABLED, max_length=16, description="状态（enabled/disabled）")
    remark: str | None = Field(default=None, max_length=255, description="备注")
    i18n: Annotated[ConcurrentStableDict[str, MailTextInput], CONTRACT_COLLECTION] = Field(
        description="语言标识 → 主题 / 正文（至少一种语言）"
    )
    sample_params: Annotated[ConcurrentStableDict[str, str], CONTRACT_COLLECTION] = Field(
        default_factory=lambda: ConcurrentStableDict[str, str](),
        description="样例参数（提供时保存前严格渲染一次）",
    )

    @field_validator("status")
    @classmethod
    def _status_known(cls, value: str) -> str:
        """状态必须在闭集内。"""
        if value not in MAIL_TEMPLATE_STATUSES:
            raise ValueError(f"邮件模板状态非法：{value}")
        return value


class MailTemplateUpdateRequest(BaseSchema):
    """编辑邮件模板请求（code 不可改；`i18n` 提供时整体替换）。"""

    name: str | None = Field(default=None, min_length=1, max_length=128, description="模板名称")
    status: str | None = Field(default=None, max_length=16, description="状态（enabled/disabled）")
    remark: str | None = Field(default=None, max_length=255, description="备注")
    i18n: Annotated[ConcurrentStableDict[str, MailTextInput], CONTRACT_COLLECTION] = Field(
        default_factory=lambda: ConcurrentStableDict[str, MailTextInput](),
        description="语言标识 → 主题 / 正文（提供时整体替换）",
    )
    sample_params: Annotated[ConcurrentStableDict[str, str], CONTRACT_COLLECTION] = Field(
        default_factory=lambda: ConcurrentStableDict[str, str](),
        description="样例参数（提供时保存前严格渲染一次）",
    )

    @field_validator("status")
    @classmethod
    def _status_known(cls, value: str | None) -> str | None:
        """状态必须在闭集内。"""
        if value is not None and value not in MAIL_TEMPLATE_STATUSES:
            raise ValueError(f"邮件模板状态非法：{value}")
        return value


class MailTemplateListItem(BaseSchema):
    """邮件模板列表行（租户行与内置默认合并）。"""

    id: SnowflakeIdStr | None = Field(default=None, description="租户模板主键；内置默认为 null")
    code: str = Field(description="模板 code")
    name: str = Field(description="模板名称")
    status: str = Field(description="状态（enabled/disabled）")
    remark: str | None = Field(default=None, description="备注")
    source: str = Field(description="来源（tenant / builtin）")
    subject: str = Field(description="当前语言主题")
    updated_at: datetime | None = Field(default=None, description="更新时间（内置默认为 null）")


class MailTemplateDetail(MailTemplateListItem):
    """邮件模板详情（含正文与完整多语言映射）。"""

    content: str = Field(default="", description="当前语言正文")
    i18n: Annotated[ConcurrentStableDict[str, MailTextOutput], CONTRACT_COLLECTION] = Field(
        default_factory=lambda: ConcurrentStableDict[str, MailTextOutput](), description="完整多语言映射"
    )


class MailTemplateTestRequest(BaseSchema):
    """邮件模板渲染测试请求（不发送）。"""

    params: Annotated[ConcurrentStableDict[str, str], CONTRACT_COLLECTION] = Field(
        default_factory=lambda: ConcurrentStableDict[str, str](), description="渲染参数"
    )
    locale: str | None = Field(default=None, max_length=16, description="语言标识（缺省系统默认语言）")


class MailTemplatePreviewRequest(MailTemplateTestRequest):
    """按 code 预览（可命中内置默认）。"""

    code: str = Field(pattern=MAIL_TEMPLATE_CODE_PATTERN, description="模板 code")


class MailTemplateTestResult(BaseSchema):
    """模板渲染结果（不发送）。"""

    subject: str = Field(description="渲染后的主题")
    content: str = Field(description="渲染后的正文")


class MailTemplatePreviewResult(MailTemplateTestResult):
    """按 code 预览结果。"""

    code: str = Field(description="模板 code")


class MailSendRequest(BaseSchema):
    """邮件模板发送请求。"""

    template_code: str = Field(pattern=MAIL_TEMPLATE_CODE_PATTERN, description="模板 code")
    params: Annotated[ConcurrentStableDict[str, str], CONTRACT_COLLECTION] = Field(
        default_factory=lambda: ConcurrentStableDict[str, str](), description="渲染参数（值统一按字符串）"
    )
    user_id: SnowflakeIdStr | None = Field(default=None, description="收件用户主键（用于地址 / 语言解析）")
    recipient: str | None = Field(default=None, max_length=255, description="显式收件邮箱")
    locale: str | None = Field(default=None, max_length=16, description="显式语言")
    transactional: bool = Field(default=False, description="事务性消息（跳过渠道开关与免打扰）")


class MailSendResult(BaseSchema):
    """发送受理结果。"""

    log_id: SnowflakeIdStr = Field(description="发送记录主键")
    status: str = Field(description="状态（pending / skipped）")


class MailLogItem(BaseSchema):
    """邮件发送记录行。"""

    id: SnowflakeIdStr = Field(description="记录主键")
    recipient: str | None = Field(default=None, description="收件邮箱")
    subject: str | None = Field(default=None, description="渲染后的主题")
    template_code: str | None = Field(default=None, description="模板 code")
    channel: str = Field(description="发送渠道（smtp）")
    status: str = Field(description="状态（pending/success/failed/skipped）")
    error_msg: str | None = Field(default=None, description="失败原因摘要")
    attempts: int = Field(ge=0, description="已尝试次数")
    locale: str | None = Field(default=None, description="渲染语言")
    user_id: SnowflakeIdStr | None = Field(default=None, description="收件用户主键")
    sent_at: datetime | None = Field(default=None, description="发送成功时间（UTC）")
    created_at: datetime = Field(description="创建时间（UTC）")

    @field_validator("status")
    @classmethod
    def _status_known(cls, value: str) -> str:
        """状态必须在闭集内。"""
        if value not in DELIVERY_STATUSES:
            raise ValueError(f"发送状态非法：{value}")
        return value
