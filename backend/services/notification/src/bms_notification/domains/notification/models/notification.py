"""通知域表模型：站内信（`sys_notification`）。

站内信为个人维度、查看即已读；通知内容按收件人语言运行时渲染，类型取固定四类。
表结构以《数据库设计》数据表文件 `sys_notification.md` 为唯一事实源。
"""

from sqlalchemy import Boolean, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from bms_core.models.base import BaseModel, SnowflakeId
from bms_core.notification.types import (
    NOTIFICATION_TYPE_ALERT,
    NOTIFICATION_TYPE_APPROVAL,
    NOTIFICATION_TYPE_IMPORT,
    NOTIFICATION_TYPE_SYSTEM,
    NOTIFICATION_TYPES,
)

__all__ = [
    "NOTIFICATION_TYPES",
    "NOTIFICATION_TYPE_ALERT",
    "NOTIFICATION_TYPE_APPROVAL",
    "NOTIFICATION_TYPE_IMPORT",
    "NOTIFICATION_TYPE_SYSTEM",
    "SysNotification",
]


class SysNotification(BaseModel):
    """站内信（`sys_notification`）：个人维度、查看即已读。

    通知内容按收件人语言运行时渲染；业务类型与业务标识供前端跳转。
    表结构以《数据库设计》数据表文件为唯一事实源。
    """

    __tablename__ = "sys_notification"
    __table_args__ = (
        Index("idx_sys_notification_user_id_created_at", "user_id", "created_at"),
        Index("idx_sys_notification_user_id_is_read", "user_id", "is_read"),
        Index("idx_sys_notification_user_id_type", "user_id", "type"),
    )

    user_id: Mapped[int] = mapped_column(SnowflakeId, comment="收件用户 ID（逻辑外键 → sys_user.id）")
    title: Mapped[str] = mapped_column(String(256), comment="标题")
    content: Mapped[str] = mapped_column(Text, default="", comment="正文（已按收件人 locale 渲染）")
    type: Mapped[str] = mapped_column(String(32), default=NOTIFICATION_TYPE_SYSTEM, comment="通知类型")
    biz_type: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="业务类型（如 approval）")
    biz_id: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="业务标识（供跳转）")
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, comment="是否已读")
