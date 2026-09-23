"""身份源能力域：外部 IdP 适配契约（OIDC 真实实现见 `idp/oidc.py`；CAS / 企业微信 / 钉钉随认证阶段回补）。

- `IDP_PROTOCOLS`：协议清单（`oidc` / `cas` / `wecom` / `dingtalk`）。
- `IdentityToken` / `IdentityUser` / `IdentityClaims`：令牌 / 用户 / 验签声明数据契约（frozen dataclass）。
- `BaseIdentityProvider`：能力域中间层契约（`key = "identity_provider"`）——异步 `authorize` /
  `exchange_token` / `userinfo` + 可选票据校验 `verify_token`（默认不支持该协议）。
- `get_identity_provider`：依赖注入提供者（应用级单例；公共依赖经 `app/api/deps.py` 统一导出）。

口径：本域为**客户端侧**（BMS 作为客户端接外部 IdP）；BMS 兼作服务端（对外 OIDC Provider / Client Credentials）
归 `bms_core/oauth/`。外部身份映射以 `idp_key`（来源）+ `subject`（= 外部 `sub`，映射表 `sys_user_identity`）唯一定位；
JIT 建号与完整登录链路归阶段六，本域只提供可信身份声明（不做建号副作用）。
"""

from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import cast

from fastapi import Request

from bms_core.core.base import BaseObject
from bms_core.core.config import Settings
from bms_core.core.exceptions import ConfigError
from bms_core.core.plugin import DEFAULT_CONTRACT_VERSION, NULL_PLUGIN_NAME, BasePluggable, resolve_plugin

__all__ = [
    "IDP_PROTOCOLS",
    "BaseIdentityProvider",
    "IdentityClaims",
    "IdentityToken",
    "IdentityUser",
    "get_identity_provider",
]

IDP_PROTOCOLS: tuple[str, ...] = ("oidc", "cas", "wecom", "dingtalk")
"""协议清单（OIDC / CAS / 企业微信 / 钉钉）；占位期仅登记不校验。"""


@dataclass(frozen=True)
class IdentityToken(BaseObject):
    """身份源令牌。"""

    access_token: str
    """访问令牌。"""

    token_type: str = "Bearer"
    """令牌类型。"""

    expires_in: int = 0
    """有效期（秒）。"""

    id_token: str | None = None
    """OIDC ID Token（JWT；经 JWKS 验签后即得身份声明）。"""

    refresh_token: str | None = None
    """刷新令牌（可选）。"""


@dataclass(frozen=True)
class IdentityUser(BaseObject):
    """身份源用户。"""

    subject: str
    """外部唯一标识（供 `sys_user_identity` 映射 / JIT 建号；`idp_key + subject` 唯一定位）。"""

    username: str
    """用户名。"""

    email: str | None = None
    """邮箱（可选）。"""

    tenant: str | None = None
    """租户（可选）。"""

    idp_key: str = ""
    """身份来源标识（外部身份映射键；OIDC 缺省取 issuer）。"""


@dataclass(frozen=True)
class IdentityClaims(BaseObject):
    """票据校验后的身份声明（JWT 经 JWKS 验签结果；`payload` 为完整声明）。"""

    subject: str
    """主体标识（`sub`）。"""

    idp_key: str = ""
    """身份来源标识（外部身份映射键；OIDC 缺省取 issuer）。"""

    issuer: str = ""
    """签发方（`iss`）。"""

    audience: tuple[str, ...] = ()
    """受众（`aud`）。"""

    expires_at: int = 0
    """过期时间（`exp`，Unix 秒）。"""

    issued_at: int = 0
    """签发时间（`iat`，Unix 秒）。"""

    payload: Mapping[str, object] = field(default_factory=dict[str, object])
    """完整声明载荷（只读映射）。"""


class BaseIdentityProvider(BasePluggable, ABC):
    """身份源契约：授权 / 换取令牌 / 拉取用户信息。"""

    key: str = "identity_provider"
    plugin_key: str = "identity_provider"
    plugin_name: str = NULL_PLUGIN_NAME
    contract_version: str = DEFAULT_CONTRACT_VERSION

    @abstractmethod
    async def authorize(self, state: str) -> str:
        """构造授权入口 URL。

        Args:
            state: 防 CSRF 的 state（由调用方生成并持有，回调校验）。

        Returns:
            str: 授权入口 URL。
        """

    @abstractmethod
    async def exchange_token(self, code: str) -> IdentityToken:
        """用授权码换取令牌（真实实现经 `BaseHttpClient` 调 token 端点）。

        Args:
            code: 授权码。

        Returns:
            IdentityToken: 身份源令牌。
        """

    @abstractmethod
    async def userinfo(self, access_token: str) -> IdentityUser:
        """拉取用户信息（真实实现经 `BaseHttpClient` 调 userinfo 端点）。

        Args:
            access_token: 访问令牌。

        Returns:
            IdentityUser: 身份源用户。
        """

    async def verify_token(self, token: str, *, audience: str | None = None) -> IdentityClaims:
        """校验票据（JWT 经 JWKS 验签）并返回身份声明。

        默认实现表示「本协议不支持 JWT 票据校验」（如 CAS / 企业微信 / 钉钉等非 JWT 协议），
        OIDC 等 JWT 型身份源覆盖本方法（校验签名、`exp` / `iss` / `aud`）。

        Args:
            token: 待校验票据（JWT 紧凑串）。
            audience: 期望受众（可选；给定则要求命中 `aud`）。

        Returns:
            IdentityClaims: 验签后的身份声明。

        Raises:
            ConfigError: 该身份源协议不支持 JWT 票据校验（40001）。
        """
        raise ConfigError(f"身份源协议不支持 JWT 票据校验：{self.key}")


def get_identity_provider(request: Request) -> BaseIdentityProvider:
    """取应用级身份源（依赖注入提供者）。

    Args:
        request: 请求对象。

    Returns:
        BaseIdentityProvider: 应用装配的身份源实例。
    """
    settings = cast("Settings", request.app.state.settings)
    return cast(
        "BaseIdentityProvider",
        resolve_plugin(
            "identity_provider",
            settings.identity_provider.provider,
            expected_version=BaseIdentityProvider.contract_version,
        ),
    )
