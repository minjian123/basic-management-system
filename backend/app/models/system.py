"""系统平台表模型骨架：任务定义与执行记录（调度入库在阶段六回补落地）、用户偏好与站内信表声明。"""

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class SysTask(BaseModel):
    """任务定义（`sys_task`）：调度配置与执行体登记。"""

    __tablename__ = "sys_task"
    __table_args__ = (UniqueConstraint("name", "deleted_at", name="uq_sys_task_name_deleted_at"),)

    name: Mapped[str] = mapped_column(String(128), comment="任务名（唯一）")
    handler: Mapped[str] = mapped_column(String(256), comment="执行体（调用路径）")
    cron: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="调度表达式（NULL=手动触发）")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, comment="是否启用")


class SysTaskLog(BaseModel):
    """任务执行记录（`sys_task_log`）。"""

    __tablename__ = "sys_task_log"

    task_id: Mapped[int] = mapped_column(BigInteger, index=True, comment="任务定义 ID")
    status: Mapped[str] = mapped_column(String(16), comment="执行状态")
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="开始时间（UTC）")
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="结束时间（UTC）")
    result: Mapped[str | None] = mapped_column(Text, nullable=True, comment="执行结果 / 异常摘要")


class SysUserPreference(BaseModel):
    """用户偏好（`sys_user_preference`）：用户维度、键唯一（真实建表以《数据库设计》为准）。

    偏好只作展示与交互状态（向导开关 / 列表个性化 / 通知偏好 / 工作台布局）；值存 JSON 字符串，
    跨方言安全（避免 MySQL 专用 `JSON`）。表结构以《数据库设计》数据表文件为唯一事实源。
    """

    __tablename__ = "sys_user_preference"
    __table_args__ = (
        UniqueConstraint("user_id", "pref_key", "deleted_at", name="uq_sys_user_preference_user_key_deleted_at"),
    )

    user_id: Mapped[int] = mapped_column(BigInteger, index=True, comment="用户 ID（逻辑外键 → sys_user.id）")
    pref_key: Mapped[str] = mapped_column(String(128), comment="偏好键（域.键，如 list.user_form）")
    pref_value: Mapped[str] = mapped_column(Text, comment="偏好值（JSON 字符串）")


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
