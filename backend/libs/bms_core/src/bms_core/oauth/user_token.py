"""oauth 能力域：用户双 token（access / refresh）自签契约。

- 受众 / 类型常量：`TOKEN_AUDIENCE_API`（用户受众，复用 `token.py`）、`USER_TOKEN_TYPE_ACCESS` /
  `USER_TOKEN_TYPE_REFRESH`。
- `UserTokenSpec`：用户令牌签发请求（主体 / 会话 id / 租户 / scope）。
- `UserTokenPair`：双 token 签发结果（access + refresh 同 `jti`，TTL / scopes 回填）。
- `BaseUserTokenIssuer`：能力域中间层契约（`key = plugin_key = "user_token"`）——异步 `issue_pair`（自签双 token）/
  `jwks`（公开 JWKS 文档）/ `verify`（本地验签 + 类型强校验）。
- `get_user_token_issuer`：依赖注入提供者（应用级单例；公共依赖经 `app/api/deps.py` 统一导出）。

口径：用户令牌由 BMS 自签（identity 服务持有签名密钥），`aud=api`、`iss` 为 BMS；access 短时（30 分钟）供网关
校验，refresh 长时（14 天）供刷新轮换（归 01_03/01_04）；access 与 refresh 的 `jti` 同值 = 会话 id（与
`sys_session` / Redis 会话标记口径一致）。自签密钥私钥只经环境变量 / Secret 注入（`[security].keys`），
公钥经 `/.well-known/jwks.json`（identity 宿主）随服务令牌公钥一并分发；服务 JWT（`aud=service`）见同域
`token.py` / `jwt.py`，通用编解码原语见 `bms_core/security/`。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass
from typing import cast

from fastapi import Request

from bms_core.core.base import BaseObject
from bms_core.core.config import Settings
from bms_core.core.plugin import DEFAULT_CONTRACT_VERSION, NULL_PLUGIN_NAME, BasePluggable, resolve_plugin
from bms_core.idp.base import IdentityClaims
from bms_core.oauth.base import TOKEN_TYPE_BEARER

__all__ = [
    "DEFAULT_USER_TOKEN_ISSUER",
    "USER_TOKEN_KID_PREFIX",
    "USER_TOKEN_TYPE_ACCESS",
    "USER_TOKEN_TYPE_REFRESH",
    "BaseUserTokenIssuer",
    "UserTokenPair",
    "UserTokenSpec",
    "get_user_token_issuer",
]

USER_TOKEN_KID_PREFIX = "usr-"
"""用户令牌密钥 kid 前缀（与服务令牌密钥区分用途；JWKS 合并发布时按 kid 命中）。"""

USER_TOKEN_TYPE_ACCESS = "access"
"""用户 access 令牌类型（claims `type`）。"""

USER_TOKEN_TYPE_REFRESH = "refresh"
"""用户 refresh 令牌类型（claims `type`）。"""

DEFAULT_USER_TOKEN_ISSUER = "bms"
"""用户令牌自签默认签发方（`iss`；与服务令牌同源标识，生产建议配置稳定 URI）。"""


@dataclass(frozen=True)
class UserTokenSpec(BaseObject):
    """用户令牌签发请求（access 与 refresh 一次签出、同 `jti`）。"""

    subject: str
    """用户主体（`sub`；本地登录为内部用户标识，SSO 为映射后主体）。"""

    session_id: str
    """会话 id（access 与 refresh 的 `jti` 同值；与 `sys_session` / Redis 会话标记同口径）。"""

    tenant_id: str | None = None
    """租户编码（claims `tenant_id`，可选）。"""

    scopes: tuple[str, ...] = ()
    """授权范围（claims `scope`，空格分隔；可选，缺省不写）。"""


@dataclass(frozen=True)
class UserTokenPair(BaseObject):
    """用户双 token 签发结果（access + refresh）。"""

    access_token: str
    """访问令牌（紧凑 JWT）。"""

    refresh_token: str
    """刷新令牌（紧凑 JWT）。"""

    token_type: str = TOKEN_TYPE_BEARER
    """令牌类型（响应口径）。"""

    expires_in: int = 0
    """access 有效期（秒）。"""

    refresh_expires_in: int = 0
    """refresh 有效期（秒）。"""

    session_id: str = ""
    """会话 id（= `jti`，回显供调用方落会话记录）。"""

    scopes: tuple[str, ...] = ()
    """生效的授权范围。"""


class BaseUserTokenIssuer(BasePluggable, ABC):
    """用户双 token 自签契约：签发 / JWKS 公开 / 本地验签（类型强校验）。"""

    key: str = "user_token"
    plugin_key: str = "user_token"
    plugin_name: str = NULL_PLUGIN_NAME
    contract_version: str = DEFAULT_CONTRACT_VERSION

    @abstractmethod
    async def issue_pair(self, spec: UserTokenSpec) -> UserTokenPair:
        """签发用户双 token（access + refresh，同 `jti`）。

        Args:
            spec: 签发请求（主体 / 会话 id / 租户 / scope）。

        Returns:
            UserTokenPair: 双 token 结果（TTL / scopes / 会话 id 回填）。

        Raises:
            ParamError: 主体 / 会话 id 为空（10001）。
            ConfigError: 未配置签名私钥 / active_kid 非法（40001）。
        """

    @abstractmethod
    def jwks(self) -> Mapping[str, object]:
        """取公开 JWKS 文档（只含公钥）。

        Returns:
            Mapping[str, object]: `{"keys": [公钥 JWK, ...]}`。
        """

    @abstractmethod
    def verify(self, token: str, *, expected_type: str) -> IdentityClaims:
        """本地验签用户令牌（签名 / `exp` / `iss` / `aud=api` / 类型 / 主体与会话 id）。

        Args:
            token: JWT 紧凑串。
            expected_type: 期望令牌类型（`access` / `refresh`；必填，防默认放行）。

        Returns:
            IdentityClaims: 验签后的身份声明（`payload` 含扩展 claims）。

        Raises:
            AuthError: 验签 / 声明 / 类型校验失败（20001 / 401）。
        """


def get_user_token_issuer(request: Request) -> BaseUserTokenIssuer:
    """取应用级用户令牌签发者（依赖注入提供者）。

    Args:
        request: 请求对象。

    Returns:
        BaseUserTokenIssuer: 应用装配的签发者实例。
    """
    settings = cast("Settings", request.app.state.settings)
    return cast(
        "BaseUserTokenIssuer",
        resolve_plugin(
            "user_token",
            settings.user_token.provider,
            expected_version=BaseUserTokenIssuer.contract_version,
        ),
    )
