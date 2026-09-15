"""开放接口能力域：OAuth2 服务端签发 / 撤销与 scope 校验契约（真实 authlib 随系统集成 / 认证阶段回补）。

- `GRANT_TYPES`：授权类型清单（Client Credentials / 授权码 / 刷新），占位期**仅登记不校验**。
- `TOKEN_TYPE_BEARER`：令牌类型（响应 `token_type` / `Authorization` 头）。
- `ClientCredentials` / `OAuthToken`：客户端凭证与令牌响应数据契约（frozen dataclass）。
- `BaseOAuthServer`：能力域中间层契约（`key = "oauth_server"`）——异步 `issue_token`（Client Credentials 签发）/
  `revoke`（独立撤销）。
- `NullOAuthServer`：占位实现——固定返回占位令牌（**不签发、不落库存**）、`revoke` 空操作。
- `BaseScopeChecker`：能力域中间层契约（`key = "scope_checker"`）——同步 `check(granted, required)`
  判定授权面 scope（与内部权限码 `BasePermissionChecker` 分工，开放接口**先 scope 后权限码**）。
- `NullScopeChecker`：占位实现，**恒定允许**（不校验）。
- `get_oauth_server` / `get_scope_checker`：依赖注入提供者（应用级单例；公共依赖经 `app/api/deps.py` 统一导出）。

口径：本域只覆盖**开放接口 client 侧**（Client Credentials）；用户 access / refresh 双 token 归认证阶段（架构 13 §2）；
`app/scope/` 的 `DataScope` 是**数据范围注入**（行级过滤），与本域 OAuth scope（授权面收敛）语义不同，两者不混用。
"""

from abc import ABC, abstractmethod
from collections.abc import Iterable
from dataclasses import dataclass
from typing import cast

from fastapi import Request

from app.core.base import BaseObject
from app.core.capability import BaseNullObject
from app.core.plugin import DEFAULT_CONTRACT_VERSION, NULL_PLUGIN_NAME, BasePluggable

__all__ = [
    "GRANT_TYPES",
    "NULL_ACCESS_TOKEN",
    "TOKEN_TYPE_BEARER",
    "BaseOAuthServer",
    "BaseScopeChecker",
    "ClientCredentials",
    "NullOAuthServer",
    "NullScopeChecker",
    "OAuthToken",
    "get_oauth_server",
    "get_scope_checker",
]

GRANT_TYPES: tuple[str, ...] = ("client_credentials", "authorization_code", "refresh_token")
"""授权类型清单（Client Credentials / OIDC 授权码 / 刷新）；占位期仅登记不校验。"""

TOKEN_TYPE_BEARER = "Bearer"
"""令牌类型（响应 token_type / Authorization 头）。"""

NULL_ACCESS_TOKEN = "null-access-token"
"""占位令牌取值（NullOAuthServer 固定返回，便于断言与调用链贯穿）。"""


@dataclass(frozen=True)
class ClientCredentials(BaseObject):
    """客户端凭证（Client Credentials 签发入参）。"""

    client_id: str
    """客户端标识（`sys_client.client_id`）。"""

    client_secret: str
    """客户端密钥。"""

    scopes: tuple[str, ...] = ()
    """请求授权范围（可选；真实实现按 client 注册范围最小化分配）。"""


@dataclass(frozen=True)
class OAuthToken(BaseObject):
    """令牌响应（OAuth2 令牌语义；占位为固定值）。"""

    access_token: str
    """访问令牌。"""

    token_type: str = TOKEN_TYPE_BEARER
    """令牌类型。"""

    expires_in: int = 0
    """有效期（秒）。"""

    scopes: tuple[str, ...] = ()
    """生效的授权范围。"""


class BaseOAuthServer(BasePluggable, ABC):
    """开放接口服务端契约：Client Credentials 签发 + 独立撤销。"""

    key: str = "oauth_server"
    plugin_key: str = "oauth_server"
    plugin_name: str = NULL_PLUGIN_NAME
    contract_version: str = DEFAULT_CONTRACT_VERSION

    @abstractmethod
    async def issue_token(self, credentials: ClientCredentials) -> OAuthToken:
        """签发访问令牌（Client Credentials）。

        Args:
            credentials: 客户端凭证（含可选请求 scope）。

        Returns:
            OAuthToken: 令牌响应。
        """

    @abstractmethod
    async def revoke(self, token: str) -> None:
        """撤销访问令牌（独立撤销）。

        Args:
            token: 访问令牌（实现内部解析 jti / 黑名单）。
        """


class NullOAuthServer(BaseOAuthServer, BaseNullObject):
    """占位服务端：固定返回占位令牌（不签发、不落库存），撤销空操作。"""

    async def issue_token(self, credentials: ClientCredentials) -> OAuthToken:
        """固定返回占位令牌。

        Args:
            credentials: 客户端凭证（占位忽略）。

        Returns:
            OAuthToken: 占位令牌（NULL_ACCESS_TOKEN / 有效期 0 / 空 scope）。
        """
        return OAuthToken(access_token=NULL_ACCESS_TOKEN)

    async def revoke(self, token: str) -> None:
        """空操作（占位不撤销）。

        Args:
            token: 访问令牌（占位忽略）。
        """


class BaseScopeChecker(BasePluggable, ABC):
    """scope 校验契约：已授权范围是否覆盖接口所需范围。"""

    key: str = "scope_checker"
    plugin_key: str = "scope_checker"
    plugin_name: str = NULL_PLUGIN_NAME
    contract_version: str = DEFAULT_CONTRACT_VERSION

    @abstractmethod
    def check(self, granted: Iterable[str], required: str) -> bool:
        """判定 scope 是否覆盖。

        Args:
            granted: 已授权 scope（来自访问令牌）。
            required: 接口所需 scope。

        Returns:
            bool: 覆盖为 True。
        """


class NullScopeChecker(BaseScopeChecker, BaseNullObject):
    """占位 scope 校验：恒定允许（不校验，未接入真实 scope 体系时使用）。"""

    def check(self, granted: Iterable[str], required: str) -> bool:
        """恒定允许。

        Args:
            granted: 已授权 scope（占位不校验）。
            required: 接口所需 scope（占位不校验）。

        Returns:
            bool: True。
        """
        return True


def get_oauth_server(request: Request) -> BaseOAuthServer:
    """取应用级开放接口服务端（依赖注入提供者）。

    Args:
        request: 请求对象。

    Returns:
        BaseOAuthServer: 应用装配的服务端实例。
    """
    return cast("BaseOAuthServer", request.app.state.oauth_server)


def get_scope_checker(request: Request) -> BaseScopeChecker:
    """取应用级 scope 检查器（依赖注入提供者）。

    Args:
        request: 请求对象。

    Returns:
        BaseScopeChecker: 应用装配的检查器实例。
    """
    return cast("BaseScopeChecker", request.app.state.scope_checker)
