"""oauth 能力域真实实现：服务 JWT 自签（joserfc，RS256 / ES256）。

- `JwtServiceTokenIssuer`（`plugin_name = "jwt"`）：按 `active_kid` 选私钥签短时服务 JWT；`jwks` 输出全部公钥；
  `verify` 经本地 JWKS 验签并校验 `exp` / `iss` / `aud=service`（复用 `idp/jwks.py` 助手）。
- `JwtServiceTokenIssuerFactory`：显式工厂（读取 `[service_token]`；构造不因无密钥而拒——校验方只需公钥，
  签发时无可用私钥才报 `ConfigError`）。

口径：私钥只经环境变量 / Secret 注入（`BMS_SERVICE_TOKEN__KEYS` 等），配置只放非敏感项与公钥。
"""

from __future__ import annotations

import time
from collections.abc import Iterable, Mapping, Sequence
from typing import cast
from uuid import uuid4

from joserfc import jwt
from joserfc.jwk import ECKey, RSAKey

from bms_core.core.config import ServiceTokenSettings, Settings
from bms_core.core.exceptions import ConfigError
from bms_core.core.factory import BasePluginFactory
from bms_core.idp.base import IdentityClaims
from bms_core.idp.jwks import DEFAULT_ALGORITHMS, verify_jwt
from bms_core.oauth.base import OAuthToken
from bms_core.oauth.keys import TokenKey, build_jwks, to_key_set
from bms_core.oauth.token import (
    DEFAULT_SERVICE_TOKEN_ISSUER,
    DEFAULT_SERVICE_TOKEN_TTL,
    SERVICE_TOKEN_TYPE,
    TOKEN_AUDIENCE_SERVICE,
    BaseServiceTokenIssuer,
    ServiceTokenSpec,
)

__all__ = [
    "JwtServiceTokenIssuer",
    "JwtServiceTokenIssuerFactory",
]


class JwtServiceTokenIssuer(BaseServiceTokenIssuer):
    """服务 JWT 自签实现：joserfc 签名 + 本地 JWKS 验签。"""

    plugin_name: str = "jwt"

    def __init__(
        self,
        *,
        issuer: str = DEFAULT_SERVICE_TOKEN_ISSUER,
        keys: Iterable[TokenKey],
        active_kid: str = "",
        ttl: int = DEFAULT_SERVICE_TOKEN_TTL,
        algorithms: Sequence[str] = DEFAULT_ALGORITHMS,
    ) -> None:
        """初始化。

        Args:
            issuer: 自签签发方（服务 JWT `iss`）。
            keys: 密钥集（kid → 密钥材料）。
            active_kid: 当前签名密钥 kid（多把签名私钥时必填）。
            ttl: 默认有效期（秒）。
            algorithms: 允许算法白名单（默认仅 RS256 / ES256）。
        """
        self._issuer = issuer
        self._ttl = ttl
        self._active_kid = active_kid
        self._algorithms = tuple(algorithms)
        self._keys = tuple(keys)
        self._signing: dict[str, RSAKey | ECKey] = {key.kid: key.signing_key() for key in self._keys if key.can_sign}
        self._signing_algorithms: dict[str, str] = {key.kid: key.algorithm for key in self._keys if key.can_sign}
        self._key_set = to_key_set(self._keys)
        self._jwks = build_jwks(self._keys)

    async def issue(self, spec: ServiceTokenSpec) -> OAuthToken:
        """签发服务 JWT（固定 + 扩展 claims）。

        Args:
            spec: 签发请求。

        Returns:
            OAuthToken: 令牌响应（`access_token` 为紧凑 JWT）。

        Raises:
            ConfigError: 未配置签名私钥 / active_kid 非法（40001）。
        """
        kid, key = self._signing_key()
        ttl = spec.ttl if spec.ttl is not None else self._ttl
        now = int(time.time())
        claims: dict[str, object] = {
            "iss": self._issuer,
            "sub": spec.service,
            "aud": TOKEN_AUDIENCE_SERVICE,
            "exp": now + ttl,
            "iat": now,
            "jti": uuid4().hex,
            "scope": " ".join(spec.scopes),
            "typ": SERVICE_TOKEN_TYPE,
            "service": spec.service,
        }
        if spec.tenant:
            claims["tenant"] = spec.tenant
        token = jwt.encode({"alg": self._signing_algorithms[kid], "kid": kid}, claims, key)
        return OAuthToken(access_token=token, expires_in=ttl, scopes=spec.scopes)

    def jwks(self) -> Mapping[str, object]:
        """取公开 JWKS 文档（只含公钥，按 kid 排序）。

        Returns:
            Mapping[str, object]: `{"keys": [公钥 JWK, ...]}`。
        """
        return cast("Mapping[str, object]", self._jwks)

    def verify(self, token: str) -> IdentityClaims:
        """本地验签服务 JWT（签名 / `exp` / `iss` / `aud=service`）。

        Args:
            token: JWT 紧凑串。

        Returns:
            IdentityClaims: 验签后的身份声明。

        Raises:
            AuthError: 验签 / 声明校验失败（20001 / 401）。
        """
        return verify_jwt(
            token,
            self._key_set,
            issuer=self._issuer,
            audience=TOKEN_AUDIENCE_SERVICE,
            algorithms=self._algorithms,
        )

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
                raise ConfigError(f"服务令牌 active_kid 未配置私钥：{self._active_kid}")
            return self._active_kid, key
        if len(self._signing) == 1:
            return next(iter(self._signing.items()))
        if not self._signing:
            raise ConfigError("服务令牌未配置签名私钥（经 BMS_SERVICE_TOKEN__KEYS 注入）")
        raise ConfigError(f"服务令牌存在多把签名私钥，须显式配置 active_kid：{sorted(self._signing)}")


class JwtServiceTokenIssuerFactory(BasePluginFactory[JwtServiceTokenIssuer]):
    """服务 JWT 自签工厂（读取 `[service_token]`；构造不因无密钥而拒）。"""

    plugin_key: str = "service_token"
    plugin_name: str = "jwt"

    def __init__(self, settings: Settings) -> None:
        """初始化。

        Args:
            settings: 应用配置。
        """
        self._settings = settings

    def create(self, options: None = None) -> JwtServiceTokenIssuer:
        """构造服务 JWT 自签实例。

        Args:
            options: 未使用（零参口径）。

        Returns:
            JwtServiceTokenIssuer: 自签实例。
        """
        config: ServiceTokenSettings = self._settings.service_token
        keys = [
            TokenKey(
                kid=kid,
                algorithm=entry.algorithm,
                public_key=entry.public_key,
                private_key=entry.private_key,
            )
            for kid, entry in config.keys.items()
        ]
        return JwtServiceTokenIssuer(
            issuer=config.issuer or DEFAULT_SERVICE_TOKEN_ISSUER,
            keys=keys,
            active_kid=config.active_kid,
            ttl=config.ttl_seconds,
        )
