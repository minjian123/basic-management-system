"""用户↔租户可达关系模型：`sys_user_tenant`（平台服务库 `bms_tenant`）。

- 语义：一行 = 某租户（`tenant_id`，用户归属租户）内的某用户（`user_id`）可访问目标租户
  （`target_tenant_id`）；每个用户恒有一行指向其归属租户自身（「自有租户」）。
- 跨租户「同一用户」标识＝组合键 `(tenant_id, user_id)`；不引入平台级账号 ID、
  不假设跨租户同名同人（`username` 仅租户内唯一）。
- 数据所有权：**租户与配置服务**（写方唯一）；其他服务经「关系数据源」远端实现调用本服务内部端点。
- 表结构以《数据库设计》数据表文件为唯一事实源（`sys_user_tenant`）。
"""

from sqlalchemy import BigInteger, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from bms_core.models.base import BaseModel


class SysUserTenant(BaseModel):
    """用户↔租户可达关系表（`sys_user_tenant`）：可访问性数据承载（平台服务库）。

    唯一约束 `(tenant_id, user_id, target_tenant_id, deleted_at)` 是「同一用户对同一目标租户唯一」
    的事实源，其前缀 `(tenant_id, user_id)` 覆盖读路径主查询，不另建普通索引。
    """

    __tablename__ = "sys_user_tenant"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "user_id",
            "target_tenant_id",
            "deleted_at",
            name="uq_sys_user_tenant_tenant_user_target_deleted_at",
        ),
    )

    tenant_id: Mapped[int] = mapped_column(BigInteger, comment="归属租户主键（同库逻辑外键 → sys_tenant.id，只持值）")
    user_id: Mapped[int] = mapped_column(
        BigInteger, comment="用户主键（跨服务逻辑外键 → org 服务 sys_user.id，只持值）"
    )
    target_tenant_id: Mapped[int] = mapped_column(
        BigInteger, comment="可访问目标租户主键（同库逻辑外键 → sys_tenant.id，只持值）"
    )
    source: Mapped[str] = mapped_column(
        String(32),
        comment="写入来源（super_admin / admin_create / import / sso_jit / self_register / self_heal）",
    )
    status: Mapped[str] = mapped_column(
        String(16), default="active", comment="状态（active / disabled；回收置 disabled，彻底移除才软删）"
    )
