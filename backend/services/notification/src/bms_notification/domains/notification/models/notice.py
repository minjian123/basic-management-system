"""公告域表模型：`sys_notice` / `sys_notice_read` / `sys_notice_i18n`。

- 公告面向租户全员，与个人站内信（`sys_notification`）数据隔离；
- 主表默认文案列是派生快照，逐语言文案存 `sys_notice_i18n`；
- 已读回执一人一条，唯一约束带 `deleted_at`（阶段八贯穿口径）；
- 表结构以《数据库设计》数据表文件为唯一事实源。
"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from bms_core.models.base import BaseModel, SnowflakeId
from bms_notification.domains.notification.notice_constants import (
    NOTICE_PRIORITY_DEFAULT,
    NOTICE_STATUS_DRAFT,
    NOTICE_TYPE_DEFAULT,
)

__all__ = ["SysNotice", "SysNoticeI18n", "SysNoticeRead"]


class SysNotice(BaseModel):
    """公告主表（`sys_notice`）：三态、置顶、发布时间 / 过期时间。

    标题 / 正文为系统默认语言派生快照；逐语言文案见 `SysNoticeI18n`。
    过期扫描只收敛状态并发下线事件，展示与否由读取侧实时校验。
    """

    __tablename__ = "sys_notice"
    __table_args__ = (
        Index("idx_sys_notice_status_top_publish", "status", "is_top", "publish_at"),
        Index("idx_sys_notice_status_expire", "status", "expire_at"),
        Index("idx_sys_notice_type", "type"),
    )

    title: Mapped[str] = mapped_column(String(256), comment="标题（默认语言派生快照）")
    content: Mapped[str] = mapped_column(Text, default="", comment="正文 HTML（已净化；草稿可空）")
    type: Mapped[str] = mapped_column(String(32), default=NOTICE_TYPE_DEFAULT, comment="公告类型（选项集值）")
    priority: Mapped[str] = mapped_column(String(16), default=NOTICE_PRIORITY_DEFAULT, comment="优先级（选项集值）")
    is_top: Mapped[bool] = mapped_column(Boolean, default=False, comment="是否置顶")
    publish_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="发布时间（UTC）")
    expire_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, comment="过期时间（UTC；NULL = 永不过期）"
    )
    status: Mapped[str] = mapped_column(
        String(16), default=NOTICE_STATUS_DRAFT, comment="状态（draft/published/offline）"
    )


class SysNoticeRead(BaseModel):
    """公告已读回执（`sys_notice_read`）：`(notice_id, user_id, deleted_at)` 唯一。"""

    __tablename__ = "sys_notice_read"
    __table_args__ = (
        UniqueConstraint(
            "notice_id",
            "user_id",
            "deleted_at",
            name="uq_sys_notice_read_notice_user_deleted_at",
        ),
        Index("idx_sys_notice_read_user_id", "user_id"),
    )

    notice_id: Mapped[int] = mapped_column(SnowflakeId, comment="公告 ID（逻辑外键 → sys_notice.id）")
    user_id: Mapped[int] = mapped_column(SnowflakeId, comment="阅读用户 ID（逻辑外键 → sys_user.id）")
    read_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="阅读时间（UTC；保留首次）")


class SysNoticeI18n(BaseModel):
    """公告多语言附表（`sys_notice_i18n`）：`(notice_id, locale, deleted_at)` 唯一。"""

    __tablename__ = "sys_notice_i18n"
    __table_args__ = (
        UniqueConstraint(
            "notice_id",
            "locale",
            "deleted_at",
            name="uq_sys_notice_i18n_notice_locale_deleted_at",
        ),
    )

    notice_id: Mapped[int] = mapped_column(SnowflakeId, comment="公告 ID（逻辑外键 → sys_notice.id）")
    locale: Mapped[str] = mapped_column(String(16), comment="语言标识（如 zh-CN）")
    title: Mapped[str] = mapped_column(String(256), comment="该语言标题")
    content: Mapped[str] = mapped_column(Text, default="", comment="该语言正文（HTML，已净化）")
