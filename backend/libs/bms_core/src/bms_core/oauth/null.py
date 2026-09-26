"""oauth 能力域缺省实现（Null Object）：占位返回、无副作用（02-3 自 bms_core.oauth.base.py 迁入）。

- `NullOAuthServer` / `NullScopeChecker`：开放接口服务端与 scope 校验占位。
- `NullServiceTokenIssuer` / `NullTokenVerifier`：服务 JWT 自签与统一校验占位（07_02；不签真 JWT、不验签）。
- `NullUserTokenIssuer`：用户双 token 自签占位（01_02；**fail-closed**，不签真 JWT、验签恒拒）。
"""

from collections.abc import Iterable, Mapping

from bms_core.core.capability import BaseNullObject
from bms_core.core.exceptions import AuthError, ConfigError
from bms_core.idp.base import IdentityClaims
from bms_core.oauth.base import NULL_ACCESS_TOKEN, BaseOAuthServer, BaseScopeChecker, ClientCredentials, OAuthToken
from bms_core.oauth.token import BaseServiceTokenIssuer, ServiceTokenSpec
from bms_core.oauth.user_token import BaseUserTokenIssuer, UserTokenPair, UserTokenSpec
from bms_core.oauth.verify import BaseTokenVerifier, VerifiedToken

__all__ = [
    "NullOAuthServer",
    "NullScopeChecker",
    "NullServiceTokenIssuer",
    "NullTokenVerifier",
    "NullUserTokenIssuer",
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


class NullServiceTokenIssuer(BaseServiceTokenIssuer, BaseNullObject):
    """占位服务 JWT 签发者：固定占位令牌、空 JWKS、占位声明（不签真 JWT）。"""

    async def issue(self, spec: ServiceTokenSpec) -> OAuthToken:
        """固定返回占位令牌（不签发 JWT）。

        Args:
            spec: 签发请求（占位忽略）。

        Returns:
            OAuthToken: 占位令牌。
        """
        return OAuthToken(access_token=NULL_ACCESS_TOKEN, scopes=spec.scopes)

    def jwks(self) -> Mapping[str, object]:
        """返回空 JWKS 文档（占位无公钥）。

        Returns:
            Mapping[str, object]: `{"keys": []}`。
        """
        return {"keys": []}

    def verify(self, token: str) -> IdentityClaims:
        """返回占位身份声明（不验签；占位来源固定）。

        Args:
            token: 待校验票据（占位忽略）。

        Returns:
            IdentityClaims: 占位声明。
        """
        return IdentityClaims(subject="null-service", issuer="null", audience=("service",))


class NullTokenVerifier(BaseTokenVerifier, BaseNullObject):
    """占位统一校验器：恒定返回占位声明（不验签）。"""

    async def verify(self, token: str, *, audience: str) -> VerifiedToken:
        """返回占位身份声明。

        Args:
            token: 待校验票据（占位忽略）。
            audience: 期望受众（占位回填到受众字段）。

        Returns:
            VerifiedToken: 占位声明。
        """
        return VerifiedToken(subject="null-subject", audience=(audience,))


class NullUserTokenIssuer(BaseUserTokenIssuer, BaseNullObject):
    """占位用户令牌签发者：**fail-closed**（不签真 JWT、验签恒拒、空 JWKS）。"""

    async def issue_pair(self, spec: UserTokenSpec) -> UserTokenPair:
        """拒绝签发用户令牌。

        Args:
            spec: 签发请求（未使用）。

        Raises:
            ConfigError: 未配置真实实现（40001）。
        """
        raise ConfigError("用户令牌实现未配置（user_token 未选定真实实现）")

    def jwks(self) -> Mapping[str, object]:
        """返回空 JWKS 文档（占位无公钥）。

        Returns:
            Mapping[str, object]: `{"keys": []}`。
        """
        return {"keys": []}

    def verify(self, token: str, *, expected_type: str) -> IdentityClaims:
        """拒绝校验（一律视为非法令牌）。

        Args:
            token: JWT 紧凑串（未使用）。
            expected_type: 期望类型（未使用）。

        Raises:
            AuthError: 恒定失败（20001 / 401）。
        """
        raise AuthError("令牌校验失败")
