"""阶段一验证模型：验证模型基类与双库路由链路。

- PlatformProbe（sys_migration_probe，平台库）：平台库 schema 与基类链路验证
- TenantProbe（sys_tenant_probe，租户库）：租户库路由、软删除与 (唯一字段, deleted_at) 复合唯一索引验证
阶段二起按模块建立业务表，本模块保留为迁移冒烟验证。
"""

from __future__ import annotations

from sqlalchemy import String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..db.base import AuditMixin, Base, OptimisticLockMixin, SnowflakeIdMixin, SoftDeleteMixin


class PlatformProbe(SnowflakeIdMixin, AuditMixin, Base):
    """平台库验证表。"""

    __tablename__ = "sys_migration_probe"

    name: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[str | None] = mapped_column(String(255), nullable=True)


class TenantProbe(SnowflakeIdMixin, AuditMixin, SoftDeleteMixin, OptimisticLockMixin, Base):
    """租户库验证表：软删除 + 复合唯一索引（未删行 deleted_at 为 NULL，多行 NULL 不冲突）。"""

    __tablename__ = "sys_tenant_probe"
    __table_args__ = (
        UniqueConstraint("name", "deleted_at", name="uq_tenant_probe_name"),
    )

    name: Mapped[str] = mapped_column(String(64), nullable=False)
