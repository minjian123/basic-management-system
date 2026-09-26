"""security 能力域真实实现：JWT 令牌编解码（joserfc；RS256 / ES256 白名单）。

- 密钥复用 `oauth/keys.py` 的 `TokenKey`（算法白名单校验）/ `to_key_set`（按 `kid` 自动选键验签）；
  签名只用 `active_kid` 对应私钥，验签并行接受新旧全部公钥（轮换期口径）。
- `encode` 自动补 `iat`，`expires_in` 非空补 `exp`；`aud` / `iss` / `typ` 等业务声明由调用方传入。
- `decode` 校验签名 / 算法白名单 / `exp`（带容差）；失败统一抛 `AuthError`（不区分原因对外）。
- 私钥只经环境变量 / Secret 注入（`[security].keys.<kid>.private_key` → `BMS_SECURITY__KEYS`）。
"""

from __future__ import annotations

import time
from collections.abc import Iterable, Sequence

from joserfc import jwt
from joserfc.errors import JoseError
from joserfc.jwk import ECKey, RSAKey

from bms_core.core.config import Settings
from bms_core.core.exceptions import AuthError, ConfigError
from bms_core.core.factory import BasePluginFactory
from bms_core.idp.jwks import DEFAULT_ALGORITHMS, DEFAULT_LEEWAY
from bms_core.oauth.keys import TokenKey, to_key_set
from bms_core.security.base import BaseTokenCodec

__all__ = [
    "JwtTokenCodec",
    "JwtTokenCodecFactory",
]


class JwtTokenCodec(BaseTokenCodec):
    """JWT 编解码实现（joserfc；多密钥并行验签、`active_kid` 签发）。"""

    plugin_name: str = "jwt"

    def __init__(
        self,
        *,
        keys: Iterable[TokenKey],
        active_kid: str = "",
        algorithms: Sequence[str] = DEFAULT_ALGORITHMS,
        leeway: int = DEFAULT_LEEWAY,
    ) -> None:
        """初始化。

        Args:
            keys: 密钥集（`kid` → 密钥材料；验签用全部公钥）。
            active_kid: 当前签名密钥 `kid`（多把私钥时必填；仅一把私钥时可为空）。
            algorithms: 算法白名单（默认仅 RS256 / ES256）。
            leeway: `exp` 容差（秒）。
        """
        self._algorithms = tuple(algorithms)
        self._leeway = leeway
        self._keys = tuple(keys)
        self._signing: dict[str, RSAKey | ECKey] = {key.kid: key.signing_key() for key in self._keys if key.can_sign}
        self._signing_algorithms: dict[str, str] = {key.kid: key.algorithm for key in self._keys if key.can_sign}
        self._key_set = to_key_set(self._keys)
        self._active_kid = active_kid

    def encode(self, claims: dict[str, object], *, expires_in: int | None = None) -> str:
        """签发 JWT（补 `iat`；`expires_in` 非空补 `exp`）。

        Args:
            claims: 声明（`sub` / `aud` / `iss` / `type` 等由调用方给定）。
            expires_in: 有效期（秒；None 不写 `exp`）。

        Returns:
            str: JWT 紧凑串。

        Raises:
            ConfigError: 未配置可用签名私钥 / `active_kid` 非法（40001）。
        """
        kid, key = self._signing_key()
        now = int(time.time())
        payload = dict(claims)
        payload.setdefault("iat", now)
        if expires_in is not None:
            payload["exp"] = now + expires_in
        return jwt.encode({"alg": self._signing_algorithms[kid], "kid": kid}, payload, key)

    def decode(self, token: str) -> dict[str, object]:
        """校验并解析 JWT（签名 / 算法白名单 / `exp`）。

        Args:
            token: JWT 紧凑串。

        Returns:
            dict[str, object]: 声明。

        Raises:
            AuthError: 验签 / 声明校验失败（20001 / 401）。
        """
        try:
            decoded = jwt.decode(token, self._key_set, algorithms=list(self._algorithms))
        except (JoseError, ValueError, TypeError) as exc:
            raise AuthError("令牌校验失败") from exc
        claims = dict(decoded.claims)
        expires_at = claims.get("exp")
        if expires_at is not None:
            if not isinstance(expires_at, int | float) or isinstance(expires_at, bool):
                raise AuthError("令牌校验失败")
            if int(expires_at) < int(time.time()) - self._leeway:
                raise AuthError("令牌已过期")
        return claims

    def _signing_key(self) -> tuple[str, RSAKey | ECKey]:
        """取当前签名密钥。

        Returns:
            tuple[str, RSAKey | ECKey]: (`kid`, 私钥)。

        Raises:
            ConfigError: 无可用私钥 / `active_kid` 未命中（40001）。
        """
        if self._active_kid:
            key = self._signing.get(self._active_kid)
            if key is None:
                raise ConfigError(f"令牌签名密钥未配置或无私钥：active_kid={self._active_kid!r}")
            return self._active_kid, key
        if len(self._signing) == 1:
            kid = next(iter(self._signing))
            return kid, self._signing[kid]
        raise ConfigError("令牌签名密钥未指定（[security].active_kid 缺失或有多把私钥）")


class JwtTokenCodecFactory(BasePluginFactory[JwtTokenCodec]):
    """JWT 编解码工厂（读 `[security].keys` / `active_kid`；密钥为空即拒）。"""

    plugin_key: str = "token_codec"
    plugin_name: str = "jwt"

    def __init__(self, settings: Settings) -> None:
        """初始化。

        Args:
            settings: 应用配置（`[security]` 密钥集）。
        """
        self._settings = settings

    def create(self, options: None = None) -> JwtTokenCodec:
        """构造 JWT 编解码实现（密钥为空允许装配，使用时 fail-closed）。

        Args:
            options: 未使用（零参口径）。

        Returns:
            JwtTokenCodec: 编解码实现。

        Raises:
            ConfigError: 密钥材料非法（算法非白名单 / 公私钥缺失；40001）。
        """
        settings = self._settings.security
        keys = [
            TokenKey(
                kid=kid,
                algorithm=item.algorithm,
                public_key=item.public_key,
                private_key=item.private_key,
            )
            for kid, item in settings.keys.items()
        ]
        return JwtTokenCodec(keys=keys, active_kid=settings.active_kid)
