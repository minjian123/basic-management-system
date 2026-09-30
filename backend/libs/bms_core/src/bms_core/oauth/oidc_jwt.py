"""oauth 能力域真实实现：OIDC Provider（BMS 兼作 IdP）自签 ID Token / access token（joserfc）。

- `JwtOidcProvider`（`plugin_name = "jwt"`）：复用 `[security]` 用户令牌密钥体系（`usr-` kid 强制），
  按 `active_kid` 选私钥签发 ID Token（`aud=client_id` / `typ=id_token`）与 IdP access token
  （`aud=userinfo` / `typ=idp_access`）；`verify_access_token` 经本地 JWKS 全校验并强校验 `typ`。
- `JwtOidcProviderFactory`：显式工厂（读 `[oidc_provider]` TTL 与 `[security]` 密钥 / `active_kid`；
  构造不因无密钥而拒，签发时无可用私钥才 `ConfigError`）；`issuer` 由调用方按租户派生后传入。

口径：私钥只经环境变量 / Secret 注入（`BMS_SECURITY__KEYS`）；`kid` 复用 `usr-` 前缀，JWKS 与用户令牌同源。
"""

from __future__ import annotations

import secrets
import time
from collections.abc import Iterable, Mapping, Sequence

from joserfc import jwt
from joserfc.jwk import ECKey, RSAKey

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.config import Settings
from bms_core.core.exceptions import AuthError, ConfigError, ParamError
from bms_core.core.factory import BasePluginFactory
from bms_core.idp.jwks import DEFAULT_ALGORITHMS, DEFAULT_LEEWAY, verify_jwt
from bms_core.oauth.keys import TokenKey, build_jwks, to_key_set
from bms_core.oauth.oidc_provider import (
    DEFAULT_ID_TOKEN_TTL,
    DEFAULT_IDP_ACCESS_TTL,
    OIDC_ACCESS_AUDIENCE,
    OIDC_PROVIDER_KEY,
    OIDC_TOKEN_TYPE_ACCESS,
    OIDC_TOKEN_TYPE_ID,
    AccessTokenSpec,
    BaseOidcProvider,
    IdTokenSpec,
    OidcAccessClaims,
)
from bms_core.oauth.user_token import USER_TOKEN_KID_PREFIX

__all__ = [
    "JwtOidcProvider",
    "JwtOidcProviderFactory",
]


class JwtOidcProvider(BaseOidcProvider):
    """OIDC Provider 自签实现：joserfc 签名 + 本地 JWKS 验签（复用用户令牌密钥）。"""

    plugin_name: str = "jwt"

    def __init__(
        self,
        *,
        keys: Iterable[TokenKey],
        active_kid: str = "",
        id_token_ttl: int = DEFAULT_ID_TOKEN_TTL,
        access_ttl: int = DEFAULT_IDP_ACCESS_TTL,
        algorithms: Sequence[str] = DEFAULT_ALGORITHMS,
        leeway: int = DEFAULT_LEEWAY,
    ) -> None:
        """初始化。

        Args:
            keys: 密钥集（kid 必须带 `usr-` 前缀；与服务 / 用户令牌共用 `[security].keys`）。
            active_kid: 当前签名密钥 kid（多把签名私钥时必填）。
            id_token_ttl: ID Token 默认有效期（秒）。
            access_ttl: IdP access token 默认有效期（秒）。
            algorithms: 允许算法白名单（默认仅 RS256 / ES256）。
            leeway: 时间声明容差（秒）。

        Raises:
            ConfigError: 密钥 kid 缺 `usr-` 前缀 / 密钥材料非法（40001）。
        """
        self._id_token_ttl = id_token_ttl
        self._access_ttl = access_ttl
        self._active_kid = active_kid
        self._algorithms = tuple(algorithms)
        self._leeway = leeway
        self._keys = tuple(keys)
        for key in self._keys:
            if not key.kid.startswith(USER_TOKEN_KID_PREFIX):
                raise ConfigError(f"OIDC Provider 密钥 kid 必须带 {USER_TOKEN_KID_PREFIX} 前缀：{key.kid}")
        self._signing: dict[str, RSAKey | ECKey] = {key.kid: key.signing_key() for key in self._keys if key.can_sign}
        self._signing_algorithms: dict[str, str] = {key.kid: key.algorithm for key in self._keys if key.can_sign}
        self._key_set = to_key_set(self._keys)
        self._jwks = build_jwks(self._keys)

    async def issue_id_token(self, spec: IdTokenSpec) -> str:
        """签发 ID Token（`aud=client_id` / `typ=id_token`）。

        Args:
            spec: 签发请求。

        Returns:
            str: 紧凑 JWT。

        Raises:
            ParamError: 主体 / 客户端 / 签发方为空（10001）。
            ConfigError: 未配置签名私钥 / `active_kid` 非法（40001）。
        """
        subject = spec.subject.strip()
        client_id = spec.client_id.strip()
        issuer = spec.issuer.strip()
        if not subject or not client_id or not issuer:
            raise ParamError("ID Token 签发缺少主体 / 客户端 / 签发方")
        kid, key = self._signing_key()
        now = int(time.time())
        claims: dict[str, object] = {
            "iss": issuer,
            "sub": subject,
            "aud": client_id,
            "typ": OIDC_TOKEN_TYPE_ID,
            "iat": now,
            "exp": now + (spec.ttl or self._id_token_ttl),
        }
        if spec.auth_time:
            claims["auth_time"] = spec.auth_time
        if spec.nonce:
            claims["nonce"] = spec.nonce
        if spec.preferred_username:
            claims["preferred_username"] = spec.preferred_username
        if spec.name:
            claims["name"] = spec.name
        return jwt.encode({"alg": self._signing_algorithms[kid], "kid": kid}, claims, key)

    async def issue_access_token(self, spec: AccessTokenSpec) -> str:
        """签发 IdP access token（`aud=userinfo` / `typ=idp_access`）。

        Args:
            spec: 签发请求。

        Returns:
            str: 紧凑 JWT。

        Raises:
            ParamError: 主体 / 签发方为空（10001）。
            ConfigError: 未配置签名私钥 / `active_kid` 非法（40001）。
        """
        subject = spec.subject.strip()
        issuer = spec.issuer.strip()
        if not subject or not issuer:
            raise ParamError("IdP access token 签发缺少主体 / 签发方")
        kid, key = self._signing_key()
        now = int(time.time())
        claims: dict[str, object] = {
            "iss": issuer,
            "sub": subject,
            "aud": OIDC_ACCESS_AUDIENCE,
            "typ": OIDC_TOKEN_TYPE_ACCESS,
            "jti": secrets.token_urlsafe(16),
            "iat": now,
            "exp": now + (spec.ttl or self._access_ttl),
        }
        if spec.tenant_id:
            claims["tenant_id"] = spec.tenant_id
        if spec.client_id:
            claims["client_id"] = spec.client_id
        if spec.scopes:
            claims["scope"] = " ".join(spec.scopes)
        return jwt.encode({"alg": self._signing_algorithms[kid], "kid": kid}, claims, key)

    def verify_access_token(self, token: str, *, issuer: str) -> OidcAccessClaims:
        """本地校验 IdP access token（签名 / `exp` / `iss` / `aud=userinfo` / `typ`）。

        Args:
            token: JWT 紧凑串。
            issuer: 期望签发方（按租户派生）。

        Returns:
            OidcAccessClaims: 校验通过的身份声明。

        Raises:
            AuthError: 验签 / 声明 / 类型校验失败（20001 / 401）。
        """
        claims = verify_jwt(
            token,
            self._key_set,
            issuer=issuer,
            audience=OIDC_ACCESS_AUDIENCE,
            algorithms=ConcurrentStableList(self._algorithms),
            leeway=self._leeway,
        )
        payload = claims.payload
        if str(payload.get("typ") or "") != OIDC_TOKEN_TYPE_ACCESS:
            raise AuthError("令牌类型不符")
        if not claims.subject:
            raise AuthError("令牌声明缺失")
        tenant_id = payload.get("tenant_id")
        client_id = payload.get("client_id")
        raw_scope = payload.get("scope")
        scopes = tuple(item for item in str(raw_scope).split() if item) if isinstance(raw_scope, str) else ()
        return OidcAccessClaims(
            subject=claims.subject,
            tenant_id=tenant_id if isinstance(tenant_id, str) else "",
            client_id=client_id if isinstance(client_id, str) else "",
            scopes=scopes,
            expires_at=claims.expires_at,
            issued_at=claims.issued_at,
            token_id=str(payload.get("jti") or ""),
            payload=payload,
        )

    def jwks(self) -> Mapping[str, object]:
        """取公开 JWKS 文档（只含公钥，按 kid 排序）。

        Returns:
            Mapping[str, object]: `{"keys": [公钥 JWK, ...]}`。
        """
        return self._jwks

    def _signing_key(self) -> tuple[str, RSAKey | ECKey]:
        """解析当前签名密钥（active_kid 优先，单密钥自动）。

        Returns:
            tuple[str, RSAKey | ECKey]: (kid, 私钥对象)。

        Raises:
            ConfigError: 未配置私钥 / active_kid 非法 / 多密钥未指定（40001）。
        """
        if self._active_kid:
            key = self._signing.get(self._active_kid)
            if key is None:
                raise ConfigError(f"OIDC Provider active_kid 未配置私钥：{self._active_kid}")
            return self._active_kid, key
        if len(self._signing) == 1:
            return next(iter(self._signing.items()))
        if not self._signing:
            raise ConfigError("OIDC Provider 未配置签名私钥（经 BMS_SECURITY__KEYS 注入）")
        raise ConfigError(f"OIDC Provider 存在多把签名私钥，须显式配置 active_kid：{sorted(self._signing)}")


class JwtOidcProviderFactory(BasePluginFactory[JwtOidcProvider]):
    """OIDC Provider 自签工厂（读 `[oidc_provider]` TTL 与 `[security]` 密钥 / `active_kid`）。"""

    plugin_key: str = OIDC_PROVIDER_KEY
    plugin_name: str = "jwt"

    def __init__(self, settings: Settings) -> None:
        """初始化。

        Args:
            settings: 应用配置。
        """
        self._settings = settings

    def create(self, options: None = None) -> JwtOidcProvider:
        """构造 OIDC Provider 实例。

        Args:
            options: 未使用（零参口径）。

        Returns:
            JwtOidcProvider: 自签实例。
        """
        config = self._settings.oidc_provider
        security = self._settings.security
        keys = [
            TokenKey(
                kid=kid,
                algorithm=entry.algorithm,
                public_key=entry.public_key,
                private_key=entry.private_key,
            )
            for kid, entry in security.keys.items()
        ]
        return JwtOidcProvider(
            keys=keys,
            active_kid=security.active_kid,
            id_token_ttl=config.id_token_ttl_seconds,
            access_ttl=config.access_token_ttl_seconds,
        )
