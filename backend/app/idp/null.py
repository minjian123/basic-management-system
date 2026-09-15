"""idp 能力域缺省实现（Null Object）：占位返回、无副作用（02-3 自 app.idp.base.py 迁入）。"""

from app.core.capability import BaseNullObject
from app.idp.base import BaseIdentityProvider, IdentityToken, IdentityUser

__all__ = [
    "NullIdentityProvider",
]


class NullIdentityProvider(BaseIdentityProvider, BaseNullObject):
    """占位身份源：固定返回（不连外部 IdP，未接入真实实现时使用）。"""

    async def authorize(self, state: str) -> str:
        """返回占位授权 URL。

        Args:
            state: 防 CSRF 的 state（占位忽略）。

        Returns:
            str: 占位授权 URL。
        """
        return "https://null-idp/authorize"

    async def exchange_token(self, code: str) -> IdentityToken:
        """返回占位令牌。

        Args:
            code: 授权码（占位忽略）。

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
        return IdentityUser(subject="null-idp-subject", username="null-idp-user")
