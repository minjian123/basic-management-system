"""OIDC JWKS 获取与缓存 + JWT 验签助手（idp 能力域票据校验内核）。

- `JwksCache`：按 `jwks_uri` 拉取并缓存 JWK Set（TTL 内命中；`force` 强制刷新，供 `kid` 未命中重试）。
- `verify_jwt`：按 `kid` 选键、限算法（默认仅 RS256 / ES256）验签 + 校验 `exp` / `iss` / `aud`，返回 `IdentityClaims`。
- 失败语义：签名 / 过期 / `iss` / `aud` 不符 → `AuthError`（20001 / 401）；JWKS 不可达 →
  `ServiceUnavailableError`（10007 / 503）。

口径：JOSE 引擎取 **authlib 官方拆分包 `joserfc`**（authlib 1.8 的 JOSE 实现；`authlib.jose` 已弃用）。
仅接受非对称算法白名单，防「允许对称 + 非对称混用」导致的签名绕过（CVE-2016-10555 类）。
"""

from __future__ import annotations

import time
from collections.abc import Collection, Mapping
from typing import cast

import httpx
from joserfc import jwt
from joserfc.errors import JoseError
from joserfc.jwk import KeySet, KeySetSerialization
from joserfc.jwt import JWTClaimsRegistry

from bms_core.core.base import BaseObject
from bms_core.core.exceptions import AuthError, ServiceUnavailableError
from bms_core.idp.base import IdentityClaims

__all__ = [
    "DEFAULT_ALGORITHMS",
    "DEFAULT_JWKS_TTL",
    "DEFAULT_LEEWAY",
    "JwksCache",
    "verify_jwt",
]

DEFAULT_ALGORITHMS: tuple[str, ...] = ("RS256", "ES256")
"""允许的签名算法白名单（仅非对称；对称算法禁用防签名绕过）。"""

DEFAULT_JWKS_TTL = 300.0
"""JWKS 缓存 TTL（秒）。"""

DEFAULT_LEEWAY = 30
"""声明时间校验容差（秒；容忍 IdP 与本地时钟偏差）。"""

_HTTP_TIMEOUT = 10.0
"""JWKS 拉取超时（秒）。"""


class JwksCache(BaseObject):
    """JWK Set 拉取与缓存（按 `jwks_uri` 缓存，TTL 内命中）。"""

    def __init__(
        self,
        *,
        ttl: float = DEFAULT_JWKS_TTL,
        timeout: float = _HTTP_TIMEOUT,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        """初始化。

        Args:
            ttl: 缓存有效期（秒）。
            timeout: 拉取超时（秒）。
            transport: 出站传输（测试注入 MockTransport；缺省走真实网络）。
        """
        self._ttl = ttl
        self._timeout = timeout
        self._transport = transport
        self._cache: dict[str, tuple[float, KeySet]] = {}

    async def get(self, jwks_uri: str, *, force: bool = False) -> KeySet:
        """取 JWK Set（缓存命中直接返回；`force` 跳过缓存刷新）。

        Args:
            jwks_uri: JWKS 端点。
            force: 强制刷新（用于 `kid` 未命中 / 密钥轮换重试）。

        Returns:
            KeySet: 解析后的 JWK Set。

        Raises:
            ServiceUnavailableError: JWKS 端点不可达 / 响应非 2xx（10007 / 503）。
            AuthError: JWKS 内容非法无法解析（20001 / 401）。
        """
        now = time.monotonic()
        cached = self._cache.get(jwks_uri)
        if cached is not None and not force and cached[0] > now:
            return cached[1]
        data = await self._fetch(jwks_uri)
        try:
            key_set = KeySet.import_key_set(cast("KeySetSerialization", data))
        except (JoseError, ValueError, TypeError) as exc:
            raise AuthError("JWKS 解析失败") from exc
        self._cache[jwks_uri] = (now + self._ttl, key_set)
        return key_set

    async def _fetch(self, jwks_uri: str) -> Mapping[str, object]:
        """拉取 JWKS JSON。

        Args:
            jwks_uri: JWKS 端点。

        Returns:
            Mapping[str, object]: JWKS 文档。

        Raises:
            ServiceUnavailableError: 网络 / 状态码异常（10007 / 503）。
            AuthError: 响应体非法 JSON（20001 / 401）。
        """
        try:
            async with httpx.AsyncClient(timeout=self._timeout, transport=self._transport) as client:
                response = await client.get(jwks_uri)
                response.raise_for_status()
                payload = response.json()
        except httpx.HTTPError as exc:
            raise ServiceUnavailableError(f"JWKS 拉取失败：{jwks_uri}") from exc
        if not isinstance(payload, Mapping):
            raise AuthError("JWKS 响应非对象")
        return cast("Mapping[str, object]", payload)


def verify_jwt(
    token: str,
    key_set: KeySet,
    *,
    issuer: str,
    audience: str | None = None,
    algorithms: Collection[str] = DEFAULT_ALGORITHMS,
    leeway: int = DEFAULT_LEEWAY,
) -> IdentityClaims:
    """验签 JWT 并校验声明（`exp` / `iss` / 可选 `aud`）。

    Args:
        token: JWT 紧凑串。
        key_set: JWK Set（按 `kid` 自动选键）。
        issuer: 期望签发方（`iss`）。
        audience: 期望受众（`aud`；给定则要求命中）。
        algorithms: 允许的签名算法白名单。
        leeway: 时间声明容差（秒）。

    Returns:
        IdentityClaims: 验签后的身份声明。

    Raises:
        AuthError: 签名 / 算法 / 声明校验失败（20001 / 401）。
    """
    try:
        decoded = jwt.decode(token, key_set, algorithms=list(algorithms))
    except (JoseError, ValueError, TypeError) as exc:
        raise AuthError("票据验签失败") from exc
    claims = dict(decoded.claims)
    registry = (
        JWTClaimsRegistry(
            iss={"essential": True, "value": issuer},
            exp={"essential": True},
            aud={"essential": True, "values": [audience]},
            leeway=leeway,
        )
        if audience is not None
        else JWTClaimsRegistry(
            iss={"essential": True, "value": issuer},
            exp={"essential": True},
            leeway=leeway,
        )
    )
    try:
        registry.validate(claims)
    except (JoseError, ValueError, TypeError) as exc:
        raise AuthError("票据声明校验失败") from exc
    return IdentityClaims(
        subject=str(claims.get("sub", "")),
        issuer=str(claims.get("iss", "")),
        audience=_audience_claim(claims.get("aud")),
        expires_at=_int_claim(claims.get("exp")),
        issued_at=_int_claim(claims.get("iat")),
        payload=claims,
    )


def _audience_claim(value: object) -> tuple[str, ...]:
    """归一化 `aud` 声明（字符串或字符串数组）。

    Args:
        value: `aud` 声明原始值。

    Returns:
        tuple[str, ...]: 受众集合。
    """
    if isinstance(value, str):
        return (value,)
    if isinstance(value, list):
        return tuple(str(item) for item in cast("list[object]", value))
    return ()


def _int_claim(value: object) -> int:
    """归一化数值声明（`exp` / `iat`）。

    Args:
        value: 声明原始值。

    Returns:
        int: 数值（非法 / 缺失取 0）。
    """
    return int(value) if isinstance(value, (int, float)) else 0
