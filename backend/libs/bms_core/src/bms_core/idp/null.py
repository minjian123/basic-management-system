"""idp 能力域缺省实现（Null Object）：占位返回、无副作用（02-3 自 bms_core.idp.base.py 迁入）。"""

from bms_core.core.capability import BaseNullObject
from bms_core.idp.base import BaseIdentityProvider, IdentityClaims, IdentityToken, IdentityUser, IdpProbeResult

__all__ = [
    "NullIdentityProvider",
]


class NullIdentityProvider(BaseIdentityProvider, BaseNullObject):
    """占位身份源：固定返回（不连外部 IdP，未接入真实实现时使用）。"""

    async def authorize(
        self,
        state: str,
        *,
        nonce: str | None = None,
        code_challenge: str | None = None,
        code_challenge_method: str | None = None,
        service: str | None = None,
    ) -> str:
        """返回占位授权 URL。

        Args:
            state: 防 CSRF 的 state（占位忽略）。
            nonce: OIDC nonce（占位忽略）。
            code_challenge: PKCE challenge（占位忽略）。
            code_challenge_method: PKCE 方法（占位忽略）。
            service: 服务地址（占位忽略）。

        Returns:
            str: 占位授权 URL。
        """
        return "https://null-idp/authorize"

    async def exchange_token(
        self,
        code: str,
        *,
        code_verifier: str | None = None,
        service: str | None = None,
    ) -> IdentityToken:
        """返回占位令牌。

        Args:
            code: 授权码（占位忽略）。
            code_verifier: PKCE code_verifier（占位忽略）。
            service: 服务地址（占位忽略）。

        Returns:
            IdentityToken: 占位令牌。
        """
        return IdentityToken(access_token="null-idp-token")

    async def userinfo(self, access_token: str) -> IdentityUser:
        """返回占位用户。

        Args:
            access_token: 访问令牌（占位忽略）。

        Returns:
            IdentityUser: 占位用户。
        """
        return IdentityUser(subject="null-idp-subject", username="null-idp-user", idp_key="null")

    async def verify_token(
        self,
        token: str,
        *,
        audience: str | None = None,
        nonce: str | None = None,
    ) -> IdentityClaims:
        """返回占位身份声明（不验签；占位来源固定）。

        Args:
            token: 待校验票据（占位忽略）。
            audience: 期望受众（占位忽略）。
            nonce: 期望 nonce（占位忽略）。

        Returns:
            IdentityClaims: 占位声明。
        """
        return IdentityClaims(subject="null-idp-subject", idp_key="null")

    async def probe(self) -> IdpProbeResult:
        """占位身份源无可探测端点（fail-closed）。

        Returns:
            IdpProbeResult: 恒不可达。
        """
        return IdpProbeResult(reachable=False, protocol="null", detail="占位身份源不可探测")
