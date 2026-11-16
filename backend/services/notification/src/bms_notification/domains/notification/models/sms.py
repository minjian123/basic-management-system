"""短信域表模型：`sys_sms_template` / `sys_sms_log`。

- 模板按 `(code, channel)` 区分渠道，`scene` 区分验证码 / 告警 / 通知；
- 发送日志正文脱敏（连续 4 位及以上数字替换为 `****`），不含完整验证码；
- 表结构以《数据库设计》数据表文件为唯一事实源。
"""

from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from bms_core.models.base import BaseModel, SnowflakeId
from bms_notification.domains.notification.delivery_constants import DELIVERY_STATUS_PENDING
from bms_notification.domains.notification.sms_constants import (
    SMS_CHANNEL_ALIYUN,
    SMS_SCENE_DEFAULT,
    SMS_TEMPLATE_STATUS_ENABLED,
)

__all__ = ["SysSmsLog", "SysSmsTemplate"]


class SysSmsTemplate(BaseModel):
    """短信模板（`sys_sms_template`）：`(code, channel, deleted_at)` 唯一。"""

    __tablename__ = "sys_sms_template"
    __table_args__ = (
        UniqueConstraint("code", "channel", "deleted_at", name="uq_sys_sms_template_code_channel_deleted_at"),
        Index("idx_sys_sms_template_channel_status", "channel", "status"),
        Index("idx_sys_sms_template_scene", "scene"),
    )

    code: Mapped[str] = mapped_column(String(64), comment="模板 code（与渠道组合唯一；创建后不可改）")
    name: Mapped[str] = mapped_column(String(128), comment="模板名称")
    content: Mapped[str] = mapped_column(Text, default="", comment="正文 Jinja2（单语言）")
    channel: Mapped[str] = mapped_column(String(16), default=SMS_CHANNEL_ALIYUN, comment="渠道（aliyun/tencent）")
    scene: Mapped[str] = mapped_column(String(16), default=SMS_SCENE_DEFAULT, comment="场景（选项集值）")
    provider_template_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="厂商模板 ID（真实发送必填）"
    )
    provider_param_keys: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="厂商参数名顺序（JSON 数组；仅应用侧读写）"
    )
    status: Mapped[str] = mapped_column(
        String(16), default=SMS_TEMPLATE_STATUS_ENABLED, comment="状态（enabled/disabled）"
    )
    remark: Mapped[str | None] = mapped_column(String(255), nullable=True, comment="备注")


class SysSmsLog(BaseModel):
    """短信发送记录（`sys_sms_log`）：正文脱敏存储。"""

    __tablename__ = "sys_sms_log"
    __table_args__ = (
        UniqueConstraint("idempotency_key", "deleted_at", name="uq_sys_sms_log_idempotency_key_deleted_at"),
        Index("idx_sys_sms_log_status_created_at", "status", "created_at"),
        Index("idx_sys_sms_log_template_code", "template_code"),
        Index("idx_sys_sms_log_user_id", "user_id"),
    )

    recipient: Mapped[str | None] = mapped_column(String(32), nullable=True, comment="收件手机号（缺失时为空）")
    channel: Mapped[str] = mapped_column(String(16), default=SMS_CHANNEL_ALIYUN, comment="实际发送渠道")
    template_code: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="模板 code（raw 发送为空）")
    scene: Mapped[str | None] = mapped_column(String(16), nullable=True, comment="场景（选项集值）")
    content: Mapped[str | None] = mapped_column(Text, nullable=True, comment="脱敏后的正文")
    status: Mapped[str] = mapped_column(
        String(16), default=DELIVERY_STATUS_PENDING, comment="状态（pending/success/failed/skipped）"
    )
    error_msg: Mapped[str | None] = mapped_column(String(512), nullable=True, comment="失败原因摘要")
    attempts: Mapped[int] = mapped_column(Integer, default=0, comment="已尝试次数")
    user_id: Mapped[int | None] = mapped_column(SnowflakeId, nullable=True, comment="收件用户 ID（可空）")
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True, comment="幂等键（可空）")
    job_id: Mapped[int | None] = mapped_column(SnowflakeId, nullable=True, comment="发送作业 ID（可空）")
    sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="发送成功时间（UTC）")
