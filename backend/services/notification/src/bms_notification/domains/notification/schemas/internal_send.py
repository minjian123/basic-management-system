"""通知服务内部发送端点契约（`BaseNotifier` 的 `http` 实现调用）。"""

from typing import Annotated

from pydantic import Field, field_validator

from bms_core.core.concurrent import ConcurrentStableDict
from bms_core.schemas.base import CONTRACT_COLLECTION, BaseSchema, SnowflakeIdStr

__all__ = ["InternalSendRequest", "InternalSendResult"]


class InternalSendRequest(BaseSchema):
    """内部发送请求（服务间调用；租户由服务 JWT 解析）。"""

    channel: str = Field(description="渠道（email / sms）")
    recipient: str = Field(min_length=1, max_length=255, description="收件地址（邮箱 / 手机号）")
    title: str = Field(default="", max_length=256, description="标题 / 邮件主题")
    content: str = Field(default="", max_length=60000, description="已渲染正文（邮件 raw / 短信日志用）")
    template_code: str | None = Field(default=None, max_length=64, description="短信模板 code（短信必填）")
    params: Annotated[ConcurrentStableDict[str, str], CONTRACT_COLLECTION] = Field(
        default_factory=lambda: ConcurrentStableDict[str, str](), description="模板参数"
    )
    html: bool = Field(default=False, description="邮件正文是否 HTML")
    user_id: SnowflakeIdStr | None = Field(default=None, description="收件用户主键（可空）")
    biz_type: str | None = Field(default=None, max_length=64, description="业务类型")
    biz_id: str | None = Field(default=None, max_length=64, description="业务标识")
    transactional: bool = Field(default=True, description="事务性消息（跳过渠道开关与免打扰）")
    idempotency_key: str | None = Field(default=None, max_length=128, description="幂等键")

    @field_validator("channel")
    @classmethod
    def _channel_known(cls, value: str) -> str:
        """渠道必须是 email / sms。"""
        if value not in ("email", "sms"):
            raise ValueError(f"内部发送渠道非法：{value}")
        return value


class InternalSendResult(BaseSchema):
    """内部发送受理结果。"""

    log_id: SnowflakeIdStr = Field(description="发送记录主键")
    status: str = Field(description="状态（pending / skipped）")
