"""oauth 能力域：OIDC Provider（BMS 兼作 IdP）服务端契约。

- 常量：协议取值（`OIDC_DEFAULT_SCOPES` / `OIDC_RESPONSE_TYPE_CODE` / 两类令牌 `typ` / 受众）与默认 TTL。
- 数据契约：`IdTokenSpec` / `AccessTokenSpec`（签发请求）、`OidcAccessClaims`（access token 校验结果）。
- `BaseOidcProvider`：能力域中间层契约（`key = plugin_key = "oidc_provider"`）——`issue_id_token` /
  `issue_access_token` / `verify_access_token` / `jwks`。
- `build_discovery_document`：OIDC Discovery 1.0 文档构造（标准字段，端点由调用方按 issuer 派生）。
- `get_oidc_provider`：依赖注入提供者（应用级单例；公共依赖经 `app/api/deps.py` 统一导出）。

口径：本域为**服务端**（BMS 对外发布 OIDC 能力），与 `idp/`（BMS 作为客户端接外部 IdP）互补；
ID Token 与 IdP access token 复用 `[security]` 用户令牌密钥体系（`usr-` kid），仅以 `iss`（按租户派生的
issuer）与 `aud`（ID Token 为 `client_id`、access token 为 `userinfo`）区分，与用户令牌 `aud=api`、
服务令牌 `aud=service` 互不串用。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import cast

from fastapi import Request

from bms_core.core.config import Settings
from bms_core.core.objects import BaseOidcTokenSpecContract, BaseTokenClaimsContract
from bms_core.core.plugin import DEFAULT_CONTRACT_VERSION, NULL_PLUGIN_NAME, BasePluggable, resolve_plugin

__all__ = [
    "DEFAULT_AUTHORIZATION_CODE_TTL",
    "DEFAULT_IDP_ACCESS_TTL",
    "DEFAULT_ID_TOKEN_TTL",
    "OIDC_ACCESS_AUDIENCE",
    "OIDC_CODE_NAMESPACE",
    "OIDC_DEFAULT_SCOPES",
    "OIDC_GRANT_AUTHORIZATION_CODE",
    "OIDC_PROVIDER_KEY",
    "OIDC_RESPONSE_TYPE_CODE",
    "OIDC_SCOPE_EMAIL",
    "OIDC_SCOPE_OPENID",
    "OIDC_SCOPE_PROFILE",
    "OIDC_TOKEN_TYPE_ACCESS",
    "OIDC_TOKEN_TYPE_ID",
    "AccessTokenSpec",
    "BaseOidcProvider",
    "IdTokenSpec",
    "OidcAccessClaims",
    "build_discovery_document",
    "get_oidc_provider",
]

OIDC_PROVIDER_KEY = "oidc_provider"
"""能力域键（注册表键 / 配置分区名）。"""

OIDC_SCOPE_OPENID = "openid"
"""OIDC 必备 scope。"""

OIDC_SCOPE_PROFILE = "profile"
"""用户档案 scope（`preferred_username` / `name`）。"""

OIDC_SCOPE_EMAIL = "email"
"""邮箱 scope（保留；本期 `sys_user` 无 email，暂不产出声明）。"""

OIDC_DEFAULT_SCOPES: tuple[str, ...] = (OIDC_SCOPE_OPENID, OIDC_SCOPE_PROFILE, OIDC_SCOPE_EMAIL)
"""默认支持的 scope 集合。"""

OIDC_RESPONSE_TYPE_CODE = "code"
"""支持的响应类型（仅授权码）。"""

OIDC_GRANT_AUTHORIZATION_CODE = "authorization_code"
"""支持的授权类型（本期仅授权码）。"""

OIDC_TOKEN_TYPE_ID = "id_token"
"""ID Token 的 `typ` 声明取值。"""

OIDC_TOKEN_TYPE_ACCESS = "idp_access"
"""IdP access token 的 `typ` 声明取值（供 `/userinfo`；与用户 `access` 区分）。"""

OIDC_ACCESS_AUDIENCE = "userinfo"
"""IdP access token 受众（仅供 `/userinfo` 消费）。"""

OIDC_CODE_NAMESPACE = "oidccode"
"""授权码在流程状态存储中的命名空间（与 SSO `state` 隔离）。"""

DEFAULT_AUTHORIZATION_CODE_TTL = 60
"""授权码默认 TTL（秒；一次性短效）。"""

DEFAULT_ID_TOKEN_TTL = 300
"""ID Token 默认 TTL（秒）。"""

DEFAULT_IDP_ACCESS_TTL = 300
"""IdP access token 默认 TTL（秒）。"""


@dataclass(frozen=True)
class IdTokenSpec(BaseOidcTokenSpecContract):
    """ID Token 签发请求（`aud=client_id`）。"""

    subject: str
    """用户主体（BMS 用户 id 字符串）。"""

    client_id: str
    """受众（第三方客户端标识）。"""

    issuer: str
    """签发方（按租户派生的 issuer）。"""

    nonce: str = ""
    """授权请求透传的 nonce（可选；写入 ID Token 供 RP 校验重放）。"""

    auth_time: int = 0
    """用户认证时间（Unix 秒；0 表示不写）。"""

    preferred_username: str = ""
    """偏好用户名（可选声明）。"""

    name: str = ""
    """显示名（可选声明）。"""

    ttl: int | None = None
    """有效期覆盖（秒；None 取实现默认 TTL）。"""


@dataclass(frozen=True)
class AccessTokenSpec(BaseOidcTokenSpecContract):
    """IdP access token 签发请求（`aud=userinfo`）。"""

    subject: str
    """用户主体（BMS 用户 id 字符串）。"""

    tenant_code: str = ""
    """租户编码（claims `tenant_id`）。"""

    client_id: str = ""
    """客户端标识（claims `client_id`）。"""

    issuer: str = ""
    """签发方（按租户派生的 issuer）。"""

    scopes: tuple[str, ...] = ()
    """授权范围（claims `scope`，空格分隔）。"""

    ttl: int | None = None
    """有效期覆盖（秒；None 取实现默认 TTL）。"""


@dataclass(frozen=True)
class OidcAccessClaims(BaseTokenClaimsContract):
    """IdP access token 校验结果（`/userinfo` 消费）。"""

    subject: str
    """用户主体（`sub`）。"""

    tenant_code: str = ""
    """租户编码（claims `tenant_id`）。"""

    client_id: str = ""
    """客户端标识（claims `client_id`）。"""

    scopes: tuple[str, ...] = ()
    """授权范围。"""

    expires_at: int = 0
    """过期时间（`exp`，Unix 秒）。"""

    issued_at: int = 0
    """签发时间（`iat`，Unix 秒）。"""

    token_id: str = ""
    """令牌 id（`jti`）。"""

    payload: Mapping[str, object] = field(default_factory=dict[str, object])
    """完整声明载荷（只读映射）。"""


class BaseOidcProvider(BasePluggable, ABC):
    """OIDC Provider 契约：ID Token / access token 签发与校验、JWKS 公开。"""

    key: str = OIDC_PROVIDER_KEY
    plugin_key: str = OIDC_PROVIDER_KEY
    plugin_name: str = NULL_PLUGIN_NAME
    contract_version: str = DEFAULT_CONTRACT_VERSION

    @abstractmethod
    async def issue_id_token(self, spec: IdTokenSpec) -> str:
        """签发 ID Token（`aud=client_id` / `typ=id_token`）。

        Args:
            spec: 签发请求。

        Returns:
            str: 紧凑 JWT。

        Raises:
            ConfigError: 未配置签名私钥 / `active_kid` 非法（40001）。
        """

    @abstractmethod
    async def issue_access_token(self, spec: AccessTokenSpec) -> str:
        """签发 IdP access token（`aud=userinfo` / `typ=idp_access`）。

        Args:
            spec: 签发请求。

        Returns:
            str: 紧凑 JWT。

        Raises:
            ConfigError: 未配置签名私钥 / `active_kid` 非法（40001）。
        """

    @abstractmethod
    def verify_access_token(self, token: str, *, issuer: str) -> OidcAccessClaims:
        """本地校验 IdP access token（签名 / `exp` / `iss` / `aud=userinfo` / `typ=idp_access`）。

        Args:
            token: JWT 紧凑串。
            issuer: 期望签发方（按租户派生；防跨租户串用）。

        Returns:
            OidcAccessClaims: 校验通过的身份声明。

        Raises:
            AuthError: 验签 / 声明 / 类型校验失败（20001 / 401）。
        """

    @abstractmethod
    def jwks(self) -> Mapping[str, object]:
        """取公开 JWKS 文档（只含公钥）。

        Returns:
            Mapping[str, object]: `{"keys": [公钥 JWK, ...]}`。
        """


def build_discovery_document(
    *,
    issuer: str,
    authorization_endpoint: str,
    token_endpoint: str,
    userinfo_endpoint: str,
    jwks_uri: str,
    scopes: Sequence[str] = OIDC_DEFAULT_SCOPES,
    algorithms: Sequence[str] = ("RS256", "ES256"),
) -> dict[str, object]:
    """构造 OIDC Discovery 1.0 文档（标准字段；端点由调用方按 issuer 派生）。

    Args:
        issuer: 签发方（按租户派生）。
        authorization_endpoint: 授权端点。
        token_endpoint: 令牌端点。
        userinfo_endpoint: 用户信息端点。
        jwks_uri: JWKS 端点。
        scopes: 支持的 scope 集合。
        algorithms: ID Token 签名算法白名单。

    Returns:
        dict[str, object]: Discovery 文档。
    """
    return {
        "issuer": issuer,
        "authorization_endpoint": authorization_endpoint,
        "token_endpoint": token_endpoint,
        "userinfo_endpoint": userinfo_endpoint,
        "jwks_uri": jwks_uri,
        "scopes_supported": list(scopes),
        "response_types_supported": [OIDC_RESPONSE_TYPE_CODE],
        "response_modes_supported": ["query"],
        "grant_types_supported": [OIDC_GRANT_AUTHORIZATION_CODE],
        "subject_types_supported": ["public"],
        "id_token_signing_alg_values_supported": list(algorithms),
        "token_endpoint_auth_methods_supported": ["client_secret_basic", "client_secret_post", "none"],
        "code_challenge_methods_supported": ["S256"],
        "claims_supported": [
            "sub",
            "iss",
            "aud",
            "exp",
            "iat",
            "auth_time",
            "nonce",
            "preferred_username",
            "name",
        ],
    }


def get_oidc_provider(request: Request) -> BaseOidcProvider:
    """取应用级 OIDC Provider（依赖注入提供者）。

    Args:
        request: 请求对象。

    Returns:
        BaseOidcProvider: 应用装配的 Provider 实例。
    """
    settings = cast("Settings", request.app.state.settings)
    return cast(
        "BaseOidcProvider",
        resolve_plugin(
            OIDC_PROVIDER_KEY,
            settings.oidc_provider.provider,
            expected_version=BaseOidcProvider.contract_version,
        ),
    )
