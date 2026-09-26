"""oauth 能力域真实实现：用户双 token（access / refresh）自签（joserfc，RS256 / ES256）。

- `JwtUserTokenIssuer`（`plugin_name = "jwt"`）：按 `active_kid` 选私钥一次签出 access 与 refresh（同 `jti`）；
  `jwks` 输出全部公钥；`verify` 经本地 JWKS 验签并强校验 `exp` / `iss` / `aud=api` / 类型 / 主体与会话 id。
- `JwtUserTokenIssuerFactory`：显式工厂（读 `[user_token].issuer` 与 `[security]` 密钥 / TTL；构造不因无密钥而拒，
  签发时无可用私钥才报 `ConfigError`）。
- 密钥 kid 强制 `usr-` 前缀（用途区分；JWKS 合并发布时按 kid 命中）；密钥材料复用 `oauth/keys.py`。

口径：私钥只经环境变量 / Secret 注入（`BMS_SECURITY__KEYS`），配置只放非敏感项与公钥。
"""

from __future__ import annotations

import time
from collections.abc import Iterable, Mapping, Sequence

from joserfc import jwt
from joserfc.jwk import ECKey, RSAKey

from bms_core.core.config import Settings
from bms_core.core.exceptions import AuthError, ConfigError, ParamError
from bms_core.core.factory import BasePluginFactory
from bms_core.idp.base import IdentityClaims
from bms_core.idp.jwks import DEFAULT_ALGORITHMS, DEFAULT_LEEWAY, verify_jwt
from bms_core.oauth.keys import TokenKey, build_jwks, to_key_set
from bms_core.oauth.token import TOKEN_AUDIENCE_API
from bms_core.oauth.user_token import (
    DEFAULT_USER_TOKEN_ISSUER,
    USER_TOKEN_KID_PREFIX,
    USER_TOKEN_TYPE_ACCESS,
    USER_TOKEN_TYPE_REFRESH,
    BaseUserTokenIssuer,
    UserTokenPair,
    UserTokenSpec,
)

__all__ = [
    "JwtUserTokenIssuer",
    "JwtUserTokenIssuerFactory",
]

_SECONDS_PER_MINUTE = 60
_SECONDS_PER_DAY = 86400


class JwtUserTokenIssuer(BaseUserTokenIssuer):
    """用户双 token 自签实现：joserfc 签名 + 本地 JWKS 验签（多密钥并行轮换）。"""

    plugin_name: str = "jwt"

    def __init__(
        self,
        *,
        issuer: str = DEFAULT_USER_TOKEN_ISSUER,
        keys: Iterable[TokenKey],
        active_kid: str = "",
        access_ttl: int,
        refresh_ttl: int,
        algorithms: Sequence[str] = DEFAULT_ALGORITHMS,
        leeway: int = DEFAULT_LEEWAY,
    ) -> None:
        """初始化。

        Args:
            issuer: 自签签发方（用户令牌 `iss`）。
            keys: 密钥集（kid → 密钥材料；kid 必须带 `usr-` 前缀）。
            active_kid: 当前签名密钥 kid（多把签名私钥时必填）。
            access_ttl: access 有效期（秒）。
            refresh_ttl: refresh 有效期（秒）。
            algorithms: 允许算法白名单（默认仅 RS256 / ES256）。
            leeway: 时间声明容差（秒）。

        Raises:
            ConfigError: 密钥 kid 缺 `usr-` 前缀 / 密钥材料非法（40001）。
        """
        self._issuer = issuer
        self._access_ttl = access_ttl
        self._refresh_ttl = refresh_ttl
        self._active_kid = active_kid
        self._algorithms = tuple(algorithms)
        self._leeway = leeway
        self._keys = tuple(keys)
        for key in self._keys:
            if not key.kid.startswith(USER_TOKEN_KID_PREFIX):
                raise ConfigError(f"用户令牌密钥 kid 必须带 {USER_TOKEN_KID_PREFIX} 前缀：{key.kid}")
        self._signing: dict[str, RSAKey | ECKey] = {key.kid: key.signing_key() for key in self._keys if key.can_sign}
        self._signing_algorithms: dict[str, str] = {key.kid: key.algorithm for key in self._keys if key.can_sign}
        self._key_set = to_key_set(self._keys)
        self._jwks = build_jwks(self._keys)

    async def issue_pair(self, spec: UserTokenSpec) -> UserTokenPair:
        """签发用户双 token（access + refresh；同 `jti`）。

        Args:
            spec: 签发请求（主体 / 会话 id / 租户 / scope）。

        Returns:
            UserTokenPair: 双 token 结果。

        Raises:
            ParamError: 主体 / 会话 id 为空（10001）。
            ConfigError: 未配置签名私钥 / active_kid 非法（40001）。
        """
        subject = spec.subject.strip()
        session_id = spec.session_id.strip()
        if not subject or not session_id:
            raise ParamError("用户令牌签发缺少主体或会话 id")
        kid, key = self._signing_key()
        now = int(time.time())
        header = {"alg": self._signing_algorithms[kid], "kid": kid}
        access = jwt.encode(
            header,
            self._claims(
                subject=subject,
                session_id=session_id,
                token_type=USER_TOKEN_TYPE_ACCESS,
                ttl=self._access_ttl,
                tenant_id=spec.tenant_id,
                scopes=spec.scopes,
                now=now,
            ),
            key,
        )
        refresh = jwt.encode(
            header,
            self._claims(
                subject=subject,
                session_id=session_id,
                token_type=USER_TOKEN_TYPE_REFRESH,
                ttl=self._refresh_ttl,
                tenant_id=spec.tenant_id,
                scopes=spec.scopes,
                now=now,
            ),
            key,
        )
        return UserTokenPair(
            access_token=access,
            refresh_token=refresh,
            expires_in=self._access_ttl,
            refresh_expires_in=self._refresh_ttl,
            session_id=session_id,
            scopes=spec.scopes,
        )

    def jwks(self) -> Mapping[str, object]:
        """取公开 JWKS 文档（只含公钥，按 kid 排序）。

        Returns:
            Mapping[str, object]: `{"keys": [公钥 JWK, ...]}`。
        """
        return self._jwks

    def verify(self, token: str, *, expected_type: str) -> IdentityClaims:
        """本地验签用户令牌（签名 / `exp` / `iss` / `aud=api` / 类型 / 主体与会话 id）。

        Args:
            token: JWT 紧凑串。
            expected_type: 期望令牌类型（`access` / `refresh`）。

        Returns:
            IdentityClaims: 验签后的身份声明。

        Raises:
            AuthError: 验签 / 声明 / 类型校验失败（20001 / 401）。
        """
        claims = verify_jwt(
            token,
            self._key_set,
            issuer=self._issuer,
            audience=TOKEN_AUDIENCE_API,
            algorithms=self._algorithms,
            leeway=self._leeway,
        )
        payload = claims.payload
        if str(payload.get("type") or "") != expected_type:
            raise AuthError("令牌类型不符")
        if not claims.subject or not str(payload.get("jti") or ""):
            raise AuthError("令牌声明缺失")
        return claims

    def _claims(
        self,
        *,
        subject: str,
        session_id: str,
        token_type: str,
        ttl: int,
        tenant_id: str | None,
        scopes: Sequence[str],
        now: int,
    ) -> dict[str, object]:
        """构造用户令牌声明（固定 claims + 可选扩展）。

        Args:
            subject: 用户主体。
            session_id: 会话 id（`jti`）。
            token_type: 令牌类型（`access` / `refresh`）。
            ttl: 有效期（秒）。
            tenant_id: 租户编码（可选）。
            scopes: 授权范围。
            now: 当前时刻（Unix 秒）。

        Returns:
            dict[str, object]: 声明。
        """
        claims: dict[str, object] = {
            "iss": self._issuer,
            "sub": subject,
            "aud": TOKEN_AUDIENCE_API,
            "jti": session_id,
            "type": token_type,
            "exp": now + ttl,
            "iat": now,
        }
        if tenant_id:
            claims["tenant_id"] = tenant_id
        if scopes:
            claims["scope"] = " ".join(scopes)
        return claims

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
                raise ConfigError(f"用户令牌 active_kid 未配置私钥：{self._active_kid}")
            return self._active_kid, key
        if len(self._signing) == 1:
            return next(iter(self._signing.items()))
        if not self._signing:
            raise ConfigError("用户令牌未配置签名私钥（经 BMS_SECURITY__KEYS 注入）")
        raise ConfigError(f"用户令牌存在多把签名私钥，须显式配置 active_kid：{sorted(self._signing)}")


class JwtUserTokenIssuerFactory(BasePluginFactory[JwtUserTokenIssuer]):
    """用户令牌自签工厂（读 `[user_token].issuer` 与 `[security]` 密钥 / TTL；构造不因无密钥而拒）。"""

    plugin_key: str = "user_token"
    plugin_name: str = "jwt"

    def __init__(self, settings: Settings) -> None:
        """初始化。

        Args:
            settings: 应用配置。
        """
        self._settings = settings

    def create(self, options: None = None) -> JwtUserTokenIssuer:
        """构造用户令牌自签实例。

        Args:
            options: 未使用（零参口径）。

        Returns:
            JwtUserTokenIssuer: 自签实例。
        """
        config = self._settings.user_token
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
        return JwtUserTokenIssuer(
            issuer=config.issuer or DEFAULT_USER_TOKEN_ISSUER,
            keys=keys,
            active_kid=security.active_kid,
            access_ttl=security.access_token_expire_minutes * _SECONDS_PER_MINUTE,
            refresh_ttl=security.refresh_token_expire_days * _SECONDS_PER_DAY,
        )
