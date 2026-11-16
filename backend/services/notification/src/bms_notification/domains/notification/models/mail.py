"""邮件域表模型：`sys_mail_template` / `sys_mail_template_i18n` / `sys_mail_log`。

- 邮件模板主题 / 正文逐语言存附表，主表两列为系统默认语言派生快照；
- 发送日志只存元数据（主题 / 模板 / 状态 / 错误），**不存正文**（正文在作业负载短保留）；
- 表结构以《数据库设计》数据表文件为唯一事实源。
"""

from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from bms_core.models.base import BaseModel, SnowflakeId
from bms_notification.domains.notification.delivery_constants import (
    DELIVERY_STATUS_PENDING,
    MAIL_LOG_CHANNEL,
)
from bms_notification.domains.notification.mail_constants import MAIL_TEMPLATE_STATUS_ENABLED

__all__ = ["SysMailLog", "SysMailTemplate", "SysMailTemplateI18n"]


class SysMailTemplate(BaseModel):
    """邮件模板主表（`sys_mail_template`）：code 租户内唯一、创建后不可改。"""

    __tablename__ = "sys_mail_template"
    __table_args__ = (
        UniqueConstraint("code", "deleted_at", name="uq_sys_mail_template_code_deleted_at"),
        Index("idx_sys_mail_template_status", "status"),
    )

    code: Mapped[str] = mapped_column(String(64), comment="模板 code（租户内唯一；创建后不可改）")
    name: Mapped[str] = mapped_column(String(128), comment="模板名称")
    subject: Mapped[str] = mapped_column(String(256), comment="主题（默认语言派生快照）")
    content: Mapped[str] = mapped_column(Text, default="", comment="正文 Jinja2 / HTML（默认语言派生快照）")
    status: Mapped[str] = mapped_column(
        String(16), default=MAIL_TEMPLATE_STATUS_ENABLED, comment="状态（enabled/disabled）"
    )
    remark: Mapped[str | None] = mapped_column(String(255), nullable=True, comment="备注")


class SysMailTemplateI18n(BaseModel):
    """邮件模板多语言附表（`sys_mail_template_i18n`）：`(template_id, locale, deleted_at)` 唯一。"""

    __tablename__ = "sys_mail_template_i18n"
    __table_args__ = (
        UniqueConstraint(
            "template_id",
            "locale",
            "deleted_at",
            name="uq_sys_mail_template_i18n_template_locale_deleted_at",
        ),
    )

    template_id: Mapped[int] = mapped_column(SnowflakeId, comment="模板 ID（逻辑外键 → sys_mail_template.id）")
    locale: Mapped[str] = mapped_column(String(16), comment="语言标识（如 zh-CN）")
    subject: Mapped[str] = mapped_column(String(256), comment="该语言主题")
    content: Mapped[str] = mapped_column(Text, default="", comment="该语言正文（Jinja2 / HTML）")


class SysMailLog(BaseModel):
    """邮件发送记录（`sys_mail_log`）：只存元数据，不存正文。"""

    __tablename__ = "sys_mail_log"
    __table_args__ = (
        UniqueConstraint("idempotency_key", "deleted_at", name="uq_sys_mail_log_idempotency_key_deleted_at"),
        Index("idx_sys_mail_log_status_created_at", "status", "created_at"),
        Index("idx_sys_mail_log_template_code", "template_code"),
        Index("idx_sys_mail_log_user_id", "user_id"),
    )

    recipient: Mapped[str | None] = mapped_column(String(255), nullable=True, comment="收件邮箱（缺失时为空）")
    subject: Mapped[str | None] = mapped_column(String(256), nullable=True, comment="渲染后的主题")
    template_code: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="模板 code（raw 发送为空）")
    channel: Mapped[str] = mapped_column(String(16), default=MAIL_LOG_CHANNEL, comment="发送渠道（smtp）")
    status: Mapped[str] = mapped_column(
        String(16), default=DELIVERY_STATUS_PENDING, comment="状态（pending/success/failed/skipped）"
    )
    error_msg: Mapped[str | None] = mapped_column(String(512), nullable=True, comment="失败原因摘要")
    attempts: Mapped[int] = mapped_column(Integer, default=0, comment="已尝试次数")
    locale: Mapped[str | None] = mapped_column(String(16), nullable=True, comment="渲染语言")
    user_id: Mapped[int | None] = mapped_column(SnowflakeId, nullable=True, comment="收件用户 ID（可空）")
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True, comment="幂等键（可空）")
    job_id: Mapped[int | None] = mapped_column(SnowflakeId, nullable=True, comment="发送作业 ID（可空）")
    sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="发送成功时间（UTC）")
