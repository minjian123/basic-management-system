"""edge 能力域真实实现：入站服务 JWT 校验信任（`aud=service`）。

- `ServiceJwtEdgeTrust`（`plugin_name = "service_jwt"`）：读入站 `Authorization: Bearer`，经
  `BaseServiceTokenIssuer.verify` 本地 JWKS 验签服务 JWT（校验签名 / `exp` / `iss` / `aud=service`）；
  验签通过即判定「可信来源」，并按身份头 + 服务 JWT claims 解析 `EdgeIdentity`。
- 信任口径：**唯一依据是有效服务 JWT**——不再信任可伪造的网关标记头（`X-Gateway-Identity`）；直连
  后端伪造标记 / 身份头（无有效服务 JWT）一律不信任，`[edge].require_gateway_identity` 开时 401。
- 身份解析：`service_identity` 取服务 JWT `sub`（北南向为网关注入的 `gateway`、东西向为调用方服务标识）；
  租户优先取身份头（网关注入）、缺省回落服务 JWT `tenant` claim；用户主体 / scope / 内部 id 取身份头。
- `ServiceJwtEdgeTrustFactory`：解析 `[service_token]` 实例构造本实现；**provider 为空（null 占位）时
  拒绝装配**（`PluginError`，避免「占位验签 = 恒定信任」的安全漏洞）。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from typing import cast

from bms_core.core.config import Settings
from bms_core.core.exceptions import AuthError, PluginError
from bms_core.core.factory import BasePluginFactory
from bms_core.core.plugin import resolve_plugin
from bms_core.edge.base import BaseEdgeTrust, EdgeIdentity, EdgeTrustDecision
from bms_core.idp.base import IdentityClaims
from bms_core.oauth.token import BaseServiceTokenIssuer

__all__ = [
    "ServiceJwtEdgeTrust",
    "ServiceJwtEdgeTrustFactory",
]

_AUTHORIZATION_HEADER = "authorization"
"""鉴权头名（大小写不敏感读取）。"""

_BEARER_PREFIX = "bearer "
"""Bearer 令牌前缀（大小写不敏感）。"""


class ServiceJwtEdgeTrust(BaseEdgeTrust):
    """服务 JWT 信任实现：本地验签入站服务 JWT 判定可信来源。"""

    plugin_name: str = "service_jwt"

    def __init__(self, *, issuer: BaseServiceTokenIssuer) -> None:
        """初始化。

        Args:
            issuer: 服务 JWT 签发者（提供本地 JWKS 验签）。
        """
        self._issuer = issuer

    def evaluate(self, headers: Mapping[str, str]) -> EdgeTrustDecision:
        """按入站服务 JWT 判定信任并解析身份。

        Args:
            headers: 请求头映射（`str -> str`；键大小写不敏感）。

        Returns:
            EdgeTrustDecision: 服务 JWT 有效 → 信任 + 身份；缺失 / 无效 → 不信任（不抛错）。
        """
        token = _bearer_token(headers)
        if token is None:
            return EdgeTrustDecision(trusted=False, reason="missing service token")
        try:
            claims = self._issuer.verify(token)
        except AuthError as exc:
            return EdgeTrustDecision(trusted=False, reason=str(exc))
        base = EdgeIdentity.from_headers(headers)
        identity = replace(
            base,
            tenant_code=base.tenant_code or _claim_tenant(claims),
            service_identity=claims.subject or base.service_identity,
        )
        return EdgeTrustDecision(trusted=True, identity=identity, reason="service token verified")


class ServiceJwtEdgeTrustFactory(BasePluginFactory[ServiceJwtEdgeTrust]):
    """服务 JWT 信任实现工厂（解析 `[service_token]`；provider 为空即拒）。"""

    plugin_key: str = "edge"
    plugin_name: str = "service_jwt"

    def __init__(self, settings: Settings) -> None:
        """初始化。

        Args:
            settings: 应用配置（`[service_token]` 选择）。
        """
        self._settings = settings

    def create(self, options: None = None) -> ServiceJwtEdgeTrust:
        """构造服务 JWT 信任实现。

        Args:
            options: 未使用（零参口径）。

        Returns:
            ServiceJwtEdgeTrust: 服务 JWT 信任实现。

        Raises:
            PluginError: `[service_token].provider` 为空（无真实验签来源，fail-closed）。
        """
        provider = self._settings.service_token.provider
        if not provider:
            raise PluginError("service_jwt 边缘信任需要真实服务 JWT 签发者（[service_token].provider 不得为空）")
        issuer = cast(
            "BaseServiceTokenIssuer",
            resolve_plugin(
                "service_token",
                provider,
                expected_version=BaseServiceTokenIssuer.contract_version,
            ),
        )
        return ServiceJwtEdgeTrust(issuer=issuer)


def _bearer_token(headers: Mapping[str, str]) -> str | None:
    """取入站 Bearer 令牌（大小写不敏感）。

    Args:
        headers: 请求头映射。

    Returns:
        str | None: 令牌紧凑串；缺失 / 非 Bearer 为 None。
    """
    raw = {key.lower(): value for key, value in headers.items()}.get(_AUTHORIZATION_HEADER, "")
    if not raw or not raw.lower().startswith(_BEARER_PREFIX):
        return None
    token = raw[len(_BEARER_PREFIX) :].strip()
    return token or None


def _claim_tenant(claims: IdentityClaims) -> str | None:
    """取服务 JWT 的租户声明。

    Args:
        claims: 验签后的身份声明。

    Returns:
        str | None: 租户编码；缺失 / 非字符串为空。
    """
    raw = claims.payload.get("tenant")
    return raw if isinstance(raw, str) and raw else None
