"""通知域表模型骨架：站内信（`sys_notification`，真实建表以《数据库设计》为准）。

站内信为个人维度、查看即已读；通知内容按收件人语言运行时渲染，类型取值随通知公告阶段确定。
本任务只声明结构、不建表、不迁移；表结构以《数据库设计》数据表文件为唯一事实源。
"""

from sqlalchemy import BigInteger, Boolean, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from bms_core.models.base import BaseModel


class SysNotification(BaseModel):
    """站内信（`sys_notification`）：个人维度、查看即已读（真实建表以《数据库设计》为准）。

    通知内容按收件人语言运行时渲染；类型取值随通知公告阶段确定，本任务只声明结构、不建表。
    表结构以《数据库设计》数据表文件为唯一事实源。
    """

    __tablename__ = "sys_notification"

    user_id: Mapped[int] = mapped_column(BigInteger, index=True, comment="收件用户 ID（逻辑外键 → sys_user.id）")
    title: Mapped[str] = mapped_column(String(256), comment="标题")
    content: Mapped[str] = mapped_column(Text, comment="正文（已按收件人 locale 渲染）")
    type: Mapped[str] = mapped_column(String(32), index=True, comment="通知类型")
    biz_type: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="业务类型（如 approval）")
    biz_id: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="业务标识（供跳转与去重）")
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, index=True, comment="是否已读")
