"""oauth 能力域：双类 JWT 受众 / 类型常量与服务 JWT 自签契约。

- 受众常量：用户 JWT `aud=api`（BMS 自签，见同域 `user_token.py`）、服务 JWT `aud=service`（BMS 自签）。
- `ServiceTokenSpec`：服务 JWT 签发请求（服务标识 / scope / 租户 / TTL）。
- `BaseServiceTokenIssuer`：能力域中间层契约（`key = plugin_key = "service_token"`）——异步 `issue`（自签）/
  `jwks`（公开 JWKS 文档）/ `verify`（本地验签）。
- `get_service_token_issuer`：依赖注入提供者（应用级单例；公共依赖经 `app/api/deps.py` 统一导出）。

口径：双类 JWT 均由 BMS 自持非对称密钥自签——服务 JWT（短时 + scope + 服务标识）供服务间东西向直连调用；
用户 JWT（access / refresh 双 token，见 `user_token.py`）供用户经网关访问业务 API，`aud` 隔离防串用。
自签密钥私钥只经环境变量 / Secret 注入；公钥经 `/.well-known/jwks.json` 分发。
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
from bms_core.oauth.base import OAuthToken

__all__ = [
    "DEFAULT_SERVICE_TOKEN_ISSUER",
    "DEFAULT_SERVICE_TOKEN_TTL",
    "SERVICE_TOKEN_TYPE",
    "TOKEN_AUDIENCE_API",
    "TOKEN_AUDIENCE_SERVICE",
    "BaseServiceTokenIssuer",
    "ServiceTokenSpec",
    "get_service_token_issuer",
]

TOKEN_AUDIENCE_API = "api"
"""用户 JWT 受众（Keycloak 签发的用户访问令牌）。"""

TOKEN_AUDIENCE_SERVICE = "service"
"""服务 JWT 受众（BMS 自签的服务身份令牌）。"""

SERVICE_TOKEN_TYPE = "service"
"""服务 JWT 类型（claims `typ`）。"""

DEFAULT_SERVICE_TOKEN_ISSUER = "bms"
"""自签服务 JWT 的默认签发方（`iss`；生产建议配置稳定 URI）。"""

DEFAULT_SERVICE_TOKEN_TTL = 300
"""服务 JWT 默认有效期（秒；短时令牌）。"""


@dataclass(frozen=True)
class ServiceTokenSpec(BaseObject):
    """服务 JWT 签发请求。"""

    service: str
    """服务标识（`sub` / `service`；调用方所属服务，如 `platform`）。"""

    scopes: tuple[str, ...] = ()
    """授权范围（`scope`，空格分隔；由调用方按需传）。"""

    tenant: str | None = None
    """租户编码（扩展 claim，可选；服务身份跨租户时留空）。"""

    ttl: int | None = None
    """有效期覆盖（秒；None 取签发者默认 TTL）。"""


class BaseServiceTokenIssuer(BasePluggable, ABC):
    """服务 JWT 自签契约：签发 / JWKS 公开 / 本地验签。"""

    key: str = "service_token"
    plugin_key: str = "service_token"
    plugin_name: str = NULL_PLUGIN_NAME
    contract_version: str = DEFAULT_CONTRACT_VERSION

    @abstractmethod
    async def issue(self, spec: ServiceTokenSpec) -> OAuthToken:
        """签发服务 JWT。

        Args:
            spec: 签发请求（服务标识 / scope / 租户 / TTL）。

        Returns:
            OAuthToken: 令牌响应（`access_token` 为紧凑 JWT，回填 `expires_in` / `scopes`）。

        Raises:
            ConfigError: 未配置私钥 / active_kid 非法（40001）。
        """

    @abstractmethod
    def jwks(self) -> Mapping[str, object]:
        """取公开 JWKS 文档（只含公钥）。

        Returns:
            Mapping[str, object]: `{"keys": [公钥 JWK, ...]}`。
        """

    @abstractmethod
    def verify(self, token: str) -> IdentityClaims:
        """本地验签服务 JWT（签名 + `exp` + `iss` + `aud=service`）。

        Args:
            token: JWT 紧凑串。

        Returns:
            IdentityClaims: 验签后的身份声明（`payload` 含扩展 claims）。

        Raises:
            AuthError: 验签 / 声明校验失败（20001 / 401）。
        """


def get_service_token_issuer(request: Request) -> BaseServiceTokenIssuer:
    """取应用级服务 JWT 签发者（依赖注入提供者）。

    Args:
        request: 请求对象。

    Returns:
        BaseServiceTokenIssuer: 应用装配的签发者实例。
    """
    settings = cast("Settings", request.app.state.settings)
    return cast(
        "BaseServiceTokenIssuer",
        resolve_plugin(
            "service_token",
            settings.service_token.provider,
            expected_version=BaseServiceTokenIssuer.contract_version,
        ),
    )
