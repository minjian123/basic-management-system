"""oauth 能力域缺省实现（Null Object）：占位返回、无副作用（02-3 自 app.oauth.base.py 迁入）。"""

from collections.abc import Iterable

from app.core.capability import BaseNullObject
from app.oauth.base import NULL_ACCESS_TOKEN, BaseOAuthServer, BaseScopeChecker, ClientCredentials, OAuthToken

__all__ = [
    "NullOAuthServer",
    "NullScopeChecker",
]


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
