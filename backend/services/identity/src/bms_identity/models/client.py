"""第三方应用客户端模型：`sys_client`（认证与身份服务租户库 `bms_identity_{code}`）。

- 数据所有权：**认证与身份服务**（BMS 兼作 IdP 的 OIDC 客户端注册；开放接口管理阶段十复用）。
- 凭据零明文：`client_secret_hash` 只存 PBKDF2 哈希（公共客户端为空）；明文仅创建 / 重置响应回显一次。
- 表结构以《数据库设计》数据表文件为唯一事实源（`sys_client`）。
"""

from sqlalchemy import String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from bms_core.models.base import BaseModel


class SysClient(BaseModel):
    """第三方应用客户端（`sys_client`）：OIDC 授权码 / Client Credentials 载体。"""

    __tablename__ = "sys_client"
    __table_args__ = (UniqueConstraint("client_id", "deleted_at", name="uq_sys_client_client_id_deleted_at"),)

    client_id: Mapped[str] = mapped_column(String(64), comment="客户端标识（服务端生成；租户内唯一）")
    client_secret_hash: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="客户端密钥哈希（PBKDF2 自描述串；公共客户端为空）"
    )
    name: Mapped[str] = mapped_column(String(128), comment="应用名称（管理展示）")
    redirect_uris: Mapped[str] = mapped_column(Text, comment="回调地址白名单 JSON 数组（精确匹配）")
    grant_types: Mapped[str] = mapped_column(
        Text, comment="授权类型 JSON 数组（client_credentials/authorization_code）"
    )
    scopes: Mapped[str] = mapped_column(Text, comment="允许申请 scope 集合 JSON 数组")
    ip_whitelist: Mapped[str] = mapped_column(Text, default="[]", comment="来源 IP / CIDR 白名单 JSON 数组")
    status: Mapped[str] = mapped_column(String(16), default="enabled", comment="状态（enabled/disabled）")
