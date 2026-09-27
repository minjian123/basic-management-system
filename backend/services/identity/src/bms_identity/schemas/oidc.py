"""认证与身份服务 schemas 层：OIDC Provider 与客户端管理契约。

- OIDC 端点（token / userinfo）为标准 JSON，响应体契约仅作类型提示与文档；
- 客户端管理接口走平台统一响应体（`ApiResponse`）。
"""

from pydantic import Field

from bms_core.schemas.base import BaseSchema


class ClientCreateRequest(BaseSchema):
    """客户端注册请求。"""

    name: str = Field(min_length=1, max_length=128, description="应用名称")
    redirect_uris: list[str] = Field(default_factory=list[str], description="回调地址白名单（精确匹配）")
    grant_types: list[str] = Field(
        default_factory=lambda: ["authorization_code"], description="授权类型（client_credentials/authorization_code）"
    )
    scopes: list[str] = Field(default_factory=lambda: ["openid"], description="允许申请的 scope 集合")
    ip_whitelist: list[str] = Field(default_factory=list[str], description="来源 IP / CIDR 白名单（开放接口阶段十用）")
    public: bool = Field(default=False, description="是否公共客户端（不生成 secret；授权码流程强制 PKCE）")


class ClientItem(BaseSchema):
    """客户端列表 / 详情项（永不包含 secret 与哈希）。"""

    id: int = Field(description="主键")
    client_id: str = Field(description="客户端标识")
    name: str = Field(description="应用名称")
    redirect_uris: list[str] = Field(default_factory=list[str], description="回调地址白名单")
    grant_types: list[str] = Field(default_factory=list[str], description="授权类型")
    scopes: list[str] = Field(default_factory=list[str], description="scope 集合")
    ip_whitelist: list[str] = Field(default_factory=list[str], description="IP / CIDR 白名单")
    status: str = Field(description="状态（enabled/disabled）")


class ClientCreated(BaseSchema):
    """客户端创建 / 重置凭据响应（`client_secret` 仅本次明文返回）。"""

    client_id: str = Field(description="客户端标识")
    client_secret: str = Field(description="客户端密钥明文（仅本次返回；请妥善保存）")
    name: str = Field(description="应用名称")
    redirect_uris: list[str] = Field(default_factory=list[str], description="回调地址白名单")
    grant_types: list[str] = Field(default_factory=list[str], description="授权类型")
    scopes: list[str] = Field(default_factory=list[str], description="scope 集合")
    ip_whitelist: list[str] = Field(default_factory=list[str], description="IP / CIDR 白名单")
    status: str = Field(description="状态")


class ClientStatusRequest(BaseSchema):
    """客户端启停请求。"""

    status: str = Field(description="目标状态（enabled/disabled）")


class ClientSecretReset(BaseSchema):
    """客户端密钥重置响应（新明文仅本次返回）。"""

    client_id: str = Field(description="客户端标识")
    client_secret: str = Field(description="新密钥明文（仅本次返回；旧密钥即时失效）")


class TokenResponse(BaseSchema):
    """OIDC 令牌响应（标准 OAuth2；本期无 `refresh_token`）。"""

    access_token: str = Field(description="IdP access token（供 /userinfo）")
    token_type: str = Field(default="Bearer", description="令牌类型")
    expires_in: int = Field(description="access token 有效期（秒）")
    id_token: str = Field(description="ID Token（JWT）")
    scope: str = Field(default="", description="生效 scope（空格分隔）")


class UserInfoResponse(BaseSchema):
    """OIDC userinfo 响应（标准字段；本期不含 email）。"""

    sub: str = Field(description="用户主体（BMS 用户 id）")
    preferred_username: str = Field(default="", description="偏好用户名")
    name: str = Field(default="", description="显示名")
