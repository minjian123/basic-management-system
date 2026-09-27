"""租户外部 IdP 配置模型：`sys_identity_provider`（认证与身份服务租户库 `bms_identity_{code}`）。

- 数据所有权：**认证与身份服务**（租户级外部 IdP 配置；协议类型 / 端点 / 凭据引用）。
- 凭据零明文：`config` 内密钥类字段只存引用（`env:变量名`，预留 `secret:标识`）。
- 表结构以《数据库设计》数据表文件为唯一事实源（`sys_identity_provider`）；
  02_01 落表 + 入口清单读路径，CRUD / 连通性 / 掩码归 02_06。
"""

from sqlalchemy import Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from bms_core.models.base import BaseModel


class SysIdentityProvider(BaseModel):
    """租户外部 IdP 配置（`sys_identity_provider`）：SSO 登录入口与协议参数载体。"""

    __tablename__ = "sys_identity_provider"
    __table_args__ = (
        UniqueConstraint("idp_key", "deleted_at", name="uq_sys_identity_provider_idp_key_deleted_at"),
        Index("idx_sys_identity_provider_status_sort", "status", "sort"),
    )

    name: Mapped[str] = mapped_column(String(64), comment="显示名（登录页入口文案）")
    idp_key: Mapped[str] = mapped_column(String(64), comment="租户内稳定标识 slug（路由参数 {idp_key}）")
    type: Mapped[str] = mapped_column(String(32), comment="协议类型（IDP_PROTOCOLS：oidc/cas/wecom/dingtalk）")
    icon: Mapped[str | None] = mapped_column(String(255), nullable=True, comment="图标（空回退默认样式）")
    config: Mapped[str] = mapped_column(Text, comment="协议配置 JSON（密钥类只存引用，零明文）")
    status: Mapped[str] = mapped_column(String(16), default="enabled", comment="状态（enabled/disabled）")
    sort: Mapped[int] = mapped_column(Integer, default=0, comment="登录页排序（升序）")
