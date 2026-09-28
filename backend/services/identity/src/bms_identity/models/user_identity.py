"""SSO 全局身份映射模型：`sys_user_identity`（平台库 `bms_platform`）。

- 数据所有权：**认证与身份服务**；落平台库的依据：SSO 回调在租户定位前即需按外部身份
  命中映射（由映射行反查租户 / 用户），故不随租户库分片。
- 映射键 `idp_key = {tenant_id}:{provider_key}`：跨租户共享 IdP 不冲突、issuer 变更不破坏映射。
- 表结构以《数据库设计》数据表文件为唯一事实源（`sys_user_identity`）；
  02_01 落表 + 读路径，JIT 建号与映射写路径归 02_02。
"""

from sqlalchemy import BigInteger, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from bms_core.models.base import BaseModel


class SysUserIdentity(BaseModel):
    """SSO 全局身份映射（`sys_user_identity`）：外部身份 → 租户 / 本地用户。"""

    __tablename__ = "sys_user_identity"
    __table_args__ = (
        UniqueConstraint("idp_key", "external_id", "deleted_at", name="uq_sys_user_identity_idp_external_deleted_at"),
        Index("idx_sys_user_identity_user_id", "user_id"),
    )

    idp_key: Mapped[str] = mapped_column(String(160), comment="映射键（{tenant_id}:{provider_key}）")
    external_id: Mapped[str] = mapped_column(String(255), comment="外部身份主体（OIDC 取 sub）")
    tenant_id: Mapped[str] = mapped_column(String(64), comment="租户主键（雪花 id 字符串；10_04 改 BIGINT）")
    user_id: Mapped[int] = mapped_column(BigInteger, comment="用户 ID（逻辑外键 → org 服务 sys_user.id）")
