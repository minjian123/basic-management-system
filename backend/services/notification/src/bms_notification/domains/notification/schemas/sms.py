"""短信模板 / 发送 / 日志接口契约。"""

from datetime import datetime
from typing import Annotated

from pydantic import Field, field_validator

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.schemas.base import CONTRACT_COLLECTION, BaseSchema, SnowflakeIdStr
from bms_notification.domains.notification.delivery_constants import DELIVERY_STATUSES
from bms_notification.domains.notification.sms_constants import (
    SMS_CHANNEL_ALIYUN,
    SMS_CHANNELS,
    SMS_SCENE_DEFAULT,
    SMS_SCENES,
    SMS_TEMPLATE_STATUS_ENABLED,
    SMS_TEMPLATE_STATUSES,
)

__all__ = [
    "SmsLogItem",
    "SmsSendRequest",
    "SmsSendResult",
    "SmsTemplateCreateRequest",
    "SmsTemplateDetail",
    "SmsTemplateListItem",
    "SmsTemplateTestRequest",
    "SmsTemplateTestResult",
    "SmsTemplateUpdateRequest",
]

_MAX_PROVIDER_PARAMS = 20


class SmsTemplateCreateRequest(BaseSchema):
    """新建短信模板请求。"""

    code: str = Field(min_length=2, max_length=64, pattern=r"^[a-z][a-z0-9_.-]{1,63}$", description="模板 code")
    name: str = Field(min_length=1, max_length=128, description="模板名称")
    content: str = Field(min_length=1, max_length=2000, description="正文 Jinja2（单语言）")
    channel: str = Field(default=SMS_CHANNEL_ALIYUN, max_length=16, description="渠道（aliyun/tencent）")
    scene: str = Field(default=SMS_SCENE_DEFAULT, max_length=16, description="场景（选项集值）")
    provider_template_id: str | None = Field(default=None, max_length=64, description="厂商模板 ID")
    provider_param_keys: Annotated[ConcurrentStableList[str], CONTRACT_COLLECTION] = Field(
        default_factory=lambda: ConcurrentStableList[str](),
        description="厂商参数名顺序（≤20，去重）",
    )
    status: str = Field(default=SMS_TEMPLATE_STATUS_ENABLED, max_length=16, description="状态（enabled/disabled）")
    remark: str | None = Field(default=None, max_length=255, description="备注")

    @field_validator("channel")
    @classmethod
    def _channel_known(cls, value: str) -> str:
        """渠道必须在闭集内。"""
        if value not in SMS_CHANNELS:
            raise ValueError(f"短信渠道非法：{value}")
        return value

    @field_validator("scene")
    @classmethod
    def _scene_known(cls, value: str) -> str:
        """场景必须在闭集内（运行期仍由选项集复核）。"""
        if value not in SMS_SCENES:
            raise ValueError(f"短信场景非法：{value}")
        return value

    @field_validator("status")
    @classmethod
    def _status_known(cls, value: str) -> str:
        """状态必须在闭集内。"""
        if value not in SMS_TEMPLATE_STATUSES:
            raise ValueError(f"短信模板状态非法：{value}")
        return value

    @field_validator("provider_param_keys")
    @classmethod
    def _param_keys_valid(cls, value: ConcurrentStableList[str]) -> ConcurrentStableList[str]:
        """参数名非空、去重、数量受限。"""
        if len(value) > _MAX_PROVIDER_PARAMS:
            raise ValueError("厂商参数名超过 20 个")
        seen: ConcurrentStableList[str] = ConcurrentStableList()
        for item in value:
            key = item.strip()
            if not key:
                raise ValueError("厂商参数名不得为空")
            if key in seen:
                raise ValueError(f"厂商参数名重复：{key}")
            seen.append(key)
        return seen


class SmsTemplateUpdateRequest(BaseSchema):
    """编辑短信模板请求（code / channel 不可改）。"""

    name: str | None = Field(default=None, min_length=1, max_length=128, description="模板名称")
    content: str | None = Field(default=None, min_length=1, max_length=2000, description="正文 Jinja2")
    scene: str | None = Field(default=None, max_length=16, description="场景（选项集值）")
    provider_template_id: str | None = Field(default=None, max_length=64, description="厂商模板 ID")
    provider_param_keys: Annotated[ConcurrentStableList[str] | None, CONTRACT_COLLECTION] = Field(
        default=None, description="厂商参数名顺序（提供时整体替换）"
    )
    status: str | None = Field(default=None, max_length=16, description="状态（enabled/disabled）")
    remark: str | None = Field(default=None, max_length=255, description="备注")

    @field_validator("scene")
    @classmethod
    def _scene_known(cls, value: str | None) -> str | None:
        """场景必须在闭集内。"""
        if value is not None and value not in SMS_SCENES:
            raise ValueError(f"短信场景非法：{value}")
        return value

    @field_validator("status")
    @classmethod
    def _status_known(cls, value: str | None) -> str | None:
        """状态必须在闭集内。"""
        if value is not None and value not in SMS_TEMPLATE_STATUSES:
            raise ValueError(f"短信模板状态非法：{value}")
        return value


class SmsTemplateListItem(BaseSchema):
    """短信模板列表行（租户模板与内置事务性模板合并）。"""

    id: SnowflakeIdStr | None = Field(default=None, description="租户模板主键；内置默认为 null")
    code: str = Field(description="模板 code")
    name: str = Field(description="模板名称")
    channel: str = Field(description="渠道（aliyun/tencent）")
    scene: str = Field(description="场景（选项集值）")
    status: str = Field(description="状态（enabled/disabled）")
    remark: str | None = Field(default=None, description="备注")
    source: str = Field(description="来源（tenant / builtin）")
    updated_at: datetime | None = Field(default=None, description="更新时间（内置默认为 null）")


class SmsTemplateDetail(SmsTemplateListItem):
    """短信模板详情。"""

    content: str = Field(default="", description="正文 Jinja2")
    provider_template_id: str | None = Field(default=None, description="厂商模板 ID")
    provider_param_keys: Annotated[ConcurrentStableList[str], CONTRACT_COLLECTION] = Field(
        default_factory=lambda: ConcurrentStableList[str](), description="厂商参数名顺序"
    )


class SmsTemplateTestRequest(BaseSchema):
    """短信模板渲染测试请求（不发送）。"""

    params: Annotated[ConcurrentStableDict[str, str], CONTRACT_COLLECTION] = Field(
        default_factory=lambda: ConcurrentStableDict[str, str](), description="渲染参数"
    )


class SmsTemplateTestResult(BaseSchema):
    """短信模板渲染结果（不发送）。"""

    code: str = Field(description="模板 code")
    content: str = Field(description="渲染后的正文")


class SmsSendRequest(BaseSchema):
    """短信模板发送请求（渠道取配置的当前生效渠道）。"""

    template_code: str = Field(min_length=2, max_length=64, description="模板 code")
    params: Annotated[ConcurrentStableDict[str, str], CONTRACT_COLLECTION] = Field(
        default_factory=lambda: ConcurrentStableDict[str, str](), description="渲染参数（值统一按字符串）"
    )
    user_id: SnowflakeIdStr | None = Field(default=None, description="收件用户主键（用于地址解析）")
    recipient: str | None = Field(default=None, max_length=32, description="显式收件手机号")
    transactional: bool = Field(default=False, description="事务性消息（跳过渠道开关与免打扰）")


class SmsSendResult(BaseSchema):
    """发送受理结果。"""

    log_id: SnowflakeIdStr = Field(description="发送记录主键")
    status: str = Field(description="状态（pending / skipped）")


class SmsLogItem(BaseSchema):
    """短信发送记录行。"""

    id: SnowflakeIdStr = Field(description="记录主键")
    recipient: str | None = Field(default=None, description="收件手机号")
    channel: str = Field(description="实际发送渠道")
    template_code: str | None = Field(default=None, description="模板 code")
    scene: str | None = Field(default=None, description="场景")
    content: str | None = Field(default=None, description="脱敏后的正文")
    status: str = Field(description="状态（pending/success/failed/skipped）")
    error_msg: str | None = Field(default=None, description="失败原因摘要")
    attempts: int = Field(ge=0, description="已尝试次数")
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
