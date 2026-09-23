"""oauth 能力域统一校验内核：按期望受众分流校验双类 JWT。

- `VerifiedToken`：校验通过后的令牌身份声明（含扩展 claims：类型 / 服务标识 / 租户 / scope / jti）。
- `BaseTokenVerifier`：能力域中间层契约（`key = plugin_key = "token_verifier"`）——异步 `verify(token, *, audience)`。
- `UnifiedTokenVerifier`（`plugin_name = "unified"`）：按期望受众分流——`service` → 本地 JWKS（`service_token`）；
  `api` → IdP JWKS（`identity_provider`，复用 07_01 `verify_token`）；`aud` / `iss` / `exp` 不符即拒。
- `get_token_verifier`：依赖注入提供者。

口径：**受众是「期望输入」而非从票据自读**——校验方声明期望受众，内核据此选定 JWKS 与 issuer，天然实现
`aud` 隔离（用户 token `aud=api` 以 `service` 期望校验时因 `iss` / 键不匹配被拒）。失败转
`AuthError`（20001 / 401）、IdP 不可达转 `ServiceUnavailableError`（10007 / 503）、受众非法转 `ParamError`（10001）。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import cast

from fastapi import Request

from bms_core.core.base import BaseObject
from bms_core.core.config import Settings
from bms_core.core.exceptions import ParamError
from bms_core.core.factory import BasePluginFactory
from bms_core.core.plugin import DEFAULT_CONTRACT_VERSION, NULL_PLUGIN_NAME, BasePluggable, resolve_plugin
from bms_core.idp.base import BaseIdentityProvider, IdentityClaims
from bms_core.oauth.token import (
    TOKEN_AUDIENCE_API,
    TOKEN_AUDIENCE_SERVICE,
    BaseServiceTokenIssuer,
)

__all__ = [
    "BaseTokenVerifier",
    "UnifiedTokenVerifier",
    "UnifiedTokenVerifierFactory",
    "VerifiedToken",
    "get_token_verifier",
]


@dataclass(frozen=True)
class VerifiedToken(BaseObject):
    """校验通过后的令牌身份声明（双类 JWT 归一契约）。"""

    subject: str
    """主体标识（`sub`；用户标识或服务标识）。"""

    token_type: str = ""
    """令牌类型（claims `typ`；服务 JWT 为 `service`）。"""

    audience: tuple[str, ...] = ()
    """受众（`aud`）。"""

    issuer: str = ""
    """签发方（`iss`）。"""

    scopes: tuple[str, ...] = ()
    """授权范围（claims `scope` 拆分）。"""

    service: str = ""
    """服务标识（服务 JWT 扩展 claim；用户 JWT 为空）。"""

    tenant: str | None = None
    """租户编码（扩展 claim，可选）。"""

    expires_at: int = 0
    """过期时间（`exp`，Unix 秒）。"""

    issued_at: int = 0
    """签发时间（`iat`，Unix 秒）。"""

    token_id: str = ""
    """令牌 id（`jti`）。"""

    payload: Mapping[str, object] = field(default_factory=dict[str, object])
    """完整声明载荷（只读映射）。"""


class BaseTokenVerifier(BasePluggable, ABC):
    """统一校验契约：按期望受众校验双类 JWT 并返回归一身份声明。"""

    key: str = "token_verifier"
    plugin_key: str = "token_verifier"
    plugin_name: str = NULL_PLUGIN_NAME
    contract_version: str = DEFAULT_CONTRACT_VERSION

    @abstractmethod
    async def verify(self, token: str, *, audience: str) -> VerifiedToken:
        """校验令牌并返回身份声明。

        Args:
            token: JWT 紧凑串。
            audience: 期望受众（`api` 用户 / `service` 服务）。

        Returns:
            VerifiedToken: 校验通过的身份声明。

        Raises:
            ParamError: 期望受众未登记（10001）。
            AuthError: 验签 / 过期 / `iss` / `aud` 不符（20001 / 401）。
            ServiceUnavailableError: IdP JWKS 不可达（10007 / 503）。
        """


class UnifiedTokenVerifier(BaseTokenVerifier):
    """统一校验实现：按期望受众分流到本地 JWKS 或 IdP JWKS。"""

    plugin_name: str = "unified"

    def __init__(
        self,
        *,
        service_issuer: BaseServiceTokenIssuer,
        identity_provider: BaseIdentityProvider,
    ) -> None:
        """初始化。

        Args:
            service_issuer: 本地服务 JWT 签发者（提供本地 JWKS 验签）。
            identity_provider: 外部 IdP 客户端（提供用户 JWT 验签）。
        """
        self._service_issuer = service_issuer
        self._identity_provider = identity_provider

    async def verify(self, token: str, *, audience: str) -> VerifiedToken:
        """按期望受众校验令牌。

        Args:
            token: JWT 紧凑串。
            audience: 期望受众（`api` / `service`）。

        Returns:
            VerifiedToken: 校验通过的身份声明。

        Raises:
            ParamError: 期望受众未登记（10001）。
            AuthError: 验签 / 过期 / `iss` / `aud` 不符（20001 / 401）。
            ServiceUnavailableError: IdP JWKS 不可达（10007 / 503）。
        """
        if audience == TOKEN_AUDIENCE_SERVICE:
            claims = self._service_issuer.verify(token)
        elif audience == TOKEN_AUDIENCE_API:
            claims = await self._identity_provider.verify_token(token, audience=TOKEN_AUDIENCE_API)
        else:
            raise ParamError(f"未登记的令牌受众：{audience}")
        return _from_claims(claims)


class UnifiedTokenVerifierFactory(BasePluginFactory[UnifiedTokenVerifier]):
    """统一校验工厂（解析本地服务 JWT 签发者与外部 IdP 客户端）。"""

    plugin_key: str = "token_verifier"
    plugin_name: str = "unified"

    def __init__(self, settings: Settings) -> None:
        """初始化。

        Args:
            settings: 应用配置（`[service_token]` / `[identity_provider]` 选择）。
        """
        self._settings = settings

    def create(self, options: None = None) -> UnifiedTokenVerifier:
        """构造统一校验实例。

        Args:
            options: 未使用（零参口径）。

        Returns:
            UnifiedTokenVerifier: 统一校验实例。
        """
        service_issuer = cast(
            "BaseServiceTokenIssuer",
            resolve_plugin(
                "service_token",
                self._settings.service_token.provider,
                expected_version=BaseServiceTokenIssuer.contract_version,
            ),
        )
        identity_provider = cast(
            "BaseIdentityProvider",
            resolve_plugin(
                "identity_provider",
                self._settings.identity_provider.provider,
                expected_version=BaseIdentityProvider.contract_version,
            ),
        )
        return UnifiedTokenVerifier(service_issuer=service_issuer, identity_provider=identity_provider)


def _from_claims(claims: IdentityClaims) -> VerifiedToken:
    """把验签声明归一为 `VerifiedToken`（拆分 scope / 回读扩展 claims）。

    Args:
        claims: 验签后的身份声明。

    Returns:
        VerifiedToken: 归一身份声明。
    """
    payload = dict(claims.payload)
    raw_scope = payload.get("scope")
    scopes = tuple(item for item in str(raw_scope).split() if item) if isinstance(raw_scope, str) else ()
    tenant = payload.get("tenant")
    return VerifiedToken(
        subject=claims.subject,
        token_type=str(payload.get("typ") or ""),
        audience=claims.audience,
        issuer=claims.issuer,
        scopes=scopes,
        service=str(payload.get("service") or ""),
        tenant=tenant if isinstance(tenant, str) and tenant else None,
        expires_at=claims.expires_at,
        issued_at=claims.issued_at,
        token_id=str(payload.get("jti") or ""),
        payload=payload,
    )


def get_token_verifier(request: Request) -> BaseTokenVerifier:
    """取应用级统一校验器（依赖注入提供者）。

    Args:
        request: 请求对象。

    Returns:
        BaseTokenVerifier: 应用装配的校验器实例。
    """
    settings = cast("Settings", request.app.state.settings)
    return cast(
        "BaseTokenVerifier",
        resolve_plugin(
            "token_verifier",
            settings.token_verifier.provider,
            expected_version=BaseTokenVerifier.contract_version,
        ),
    )
