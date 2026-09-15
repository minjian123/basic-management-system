"""身份源能力域：外部 IdP 适配契约（真实 authlib OIDC / CAS / 企业微信 / 钉钉随认证阶段回补）。

- `IDP_PROTOCOLS`：协议清单（`oidc` / `cas` / `wecom` / `dingtalk`）。
- `IdentityToken` / `IdentityUser`：身份源令牌与用户数据契约（frozen dataclass）。
- `BaseIdentityProvider`：能力域中间层契约（`key = "identity_provider"`）——异步 `authorize` /
  `exchange_token` / `userinfo`。
- `get_identity_provider`：依赖注入提供者（应用级单例；公共依赖经 `app/api/deps.py` 统一导出）。

口径：本域为**客户端侧**（BMS 作为客户端接外部 IdP）；BMS 兼作服务端（对外 OIDC Provider / Client Credentials）
归 02-3-13（`app/oauth`）。真实实现经 02-4-6 `BaseHttpClient` 调外部 IdP 端点；JIT 建号（`sys_user_identity`）、
双 token 签发与会话生命周期归认证阶段上层。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import cast

from fastapi import Request

from app.core.base import BaseObject
from app.core.plugin import DEFAULT_CONTRACT_VERSION, NULL_PLUGIN_NAME, BasePluggable

__all__ = [
    "IDP_PROTOCOLS",
    "BaseIdentityProvider",
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


@dataclass(frozen=True)
class IdentityUser(BaseObject):
    """身份源用户。"""

    subject: str
    """外部唯一标识（供 `sys_user_identity` 映射 / JIT 建号）。"""

    username: str
    """用户名。"""

    email: str | None = None
    """邮箱（可选）。"""

    tenant: str | None = None
    """租户（可选）。"""


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


def get_identity_provider(request: Request) -> BaseIdentityProvider:
    """取应用级身份源（依赖注入提供者）。

    Args:
        request: 请求对象。

    Returns:
        BaseIdentityProvider: 应用装配的身份源实例。
    """
    return cast("BaseIdentityProvider", request.app.state.identity_provider)
