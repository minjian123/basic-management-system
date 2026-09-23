"""idp 能力域真实实现：OIDC 客户端（Discovery / 授权 / 换码 / userinfo / JWKS 票据校验）。

- `OidcIdentityProvider`（`plugin_name = "oidc"`）：以 `issuer` 为发现基点，经 `httpx` 调 OIDC 端点；
  Discovery 元数据与 JWKS 各自缓存；`verify_token` 经 `idp/jwks.py` 按 JWKS 验签并校验 `exp` / `iss` / `aud`。
- `OidcIdentityProviderFactory`：显式工厂（读取 `[identity_provider]`；配置不全启动期拒启）。

口径：本实现只做**客户端侧**（BMS 接外部 IdP）；完整登录链路（回调路由 / state 与 nonce / PKCE）与
JIT 建号归阶段六；BMS 兼作 OIDC Provider 归 `bms_core/oauth/`。客户端凭据一律经构造注入（源为环境变量 / Secret）。
"""

from __future__ import annotations

import time
from collections.abc import Mapping, Sequence
from dataclasses import replace
from typing import cast
from urllib.parse import urlencode

import httpx

from bms_core.core.config import IdentityProviderSettings, Settings
from bms_core.core.exceptions import AuthError, ConfigError, PluginError, ServiceUnavailableError
from bms_core.core.factory import BasePluginFactory
from bms_core.idp.base import BaseIdentityProvider, IdentityClaims, IdentityToken, IdentityUser
from bms_core.idp.jwks import DEFAULT_JWKS_TTL, JwksCache, verify_jwt

__all__ = [
    "OidcIdentityProvider",
    "OidcIdentityProviderFactory",
]

_HTTP_TIMEOUT = 10.0
"""OIDC 端点调用超时（秒）。"""

_DEFAULT_SCOPES: tuple[str, ...] = ("openid", "profile", "email")
"""缺省请求 scope。"""


class OidcIdentityProvider(BaseIdentityProvider):
    """OIDC 客户端：发现 / 授权 / 换码 / userinfo / JWKS 验签。"""

    plugin_name: str = "oidc"

    def __init__(
        self,
        *,
        issuer: str,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        scopes: Sequence[str] = _DEFAULT_SCOPES,
        discovery_cache_ttl: float = 3600.0,
        jwks_cache_ttl: float = DEFAULT_JWKS_TTL,
        timeout: float = _HTTP_TIMEOUT,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        """初始化。

        Args:
            issuer: OIDC issuer（如 `http://idp:8090/realms/bms`）。
            client_id: OIDC 客户端标识。
            client_secret: OIDC 客户端密钥（源为环境变量 / Secret）。
            redirect_uri: 授权回调地址（须注册于 IdP）。
            scopes: 请求 scope。
            discovery_cache_ttl: Discovery 元数据缓存 TTL（秒）。
            jwks_cache_ttl: JWKS 缓存 TTL（秒）。
            timeout: 端点调用超时（秒）。
            transport: 出站传输（测试注入 MockTransport；缺省走真实网络）。
        """
        self._issuer = issuer.rstrip("/")
        self._client_id = client_id
        self._client_secret = client_secret
        self._redirect_uri = redirect_uri
        self._scopes = tuple(scopes)
        self._discovery_cache_ttl = discovery_cache_ttl
        self._timeout = timeout
        self._transport = transport
        self._metadata_cache: tuple[float, Mapping[str, object]] | None = None
        self._jwks = JwksCache(ttl=jwks_cache_ttl, timeout=timeout, transport=transport)

    async def authorize(self, state: str) -> str:
        """构造授权入口 URL（授权码流程；state 由调用方生成并持有、回调校验）。

        Args:
            state: 防 CSRF 的 state。

        Returns:
            str: 授权入口 URL。

        Raises:
            ConfigError: Discovery 文档缺 `authorization_endpoint`（40001）。
        """
        metadata = await self._metadata()
        endpoint = _require_str(metadata, "authorization_endpoint", self._issuer)
        query = urlencode(
            {
                "response_type": "code",
                "client_id": self._client_id,
                "redirect_uri": self._redirect_uri,
                "scope": " ".join(self._scopes),
                "state": state,
            }
        )
        separator = "&" if "?" in endpoint else "?"
        return f"{endpoint}{separator}{query}"

    async def exchange_token(self, code: str) -> IdentityToken:
        """用授权码换取令牌（含 ID Token / 刷新令牌）。

        Args:
            code: 授权码。

        Returns:
            IdentityToken: 令牌响应。

        Raises:
            ConfigError: Discovery 文档缺 `token_endpoint`（40001）。
            ServiceUnavailableError: 令牌端点不可达 / 非 2xx（10007 / 503）。
        """
        metadata = await self._metadata()
        endpoint = _require_str(metadata, "token_endpoint", self._issuer)
        payload = await self._request_json(
            endpoint,
            method="POST",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": self._redirect_uri,
                "client_id": self._client_id,
                "client_secret": self._client_secret,
            },
        )
        return IdentityToken(
            access_token=str(payload.get("access_token", "")),
            token_type=str(payload.get("token_type", "Bearer")),
            expires_in=_as_int(payload.get("expires_in")),
            id_token=_as_optional_str(payload.get("id_token")),
            refresh_token=_as_optional_str(payload.get("refresh_token")),
        )

    async def userinfo(self, access_token: str) -> IdentityUser:
        """拉取用户信息（`idp_key` 取 issuer，供外部身份映射）。

        Args:
            access_token: 访问令牌。

        Returns:
            IdentityUser: 身份源用户。

        Raises:
            ConfigError: Discovery 文档缺 `userinfo_endpoint`（40001）。
            ServiceUnavailableError: userinfo 端点不可达 / 非 2xx（10007 / 503）。
        """
        metadata = await self._metadata()
        endpoint = _require_str(metadata, "userinfo_endpoint", self._issuer)
        payload = await self._request_json(
            endpoint,
            method="GET",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        return IdentityUser(
            subject=str(payload.get("sub", "")),
            username=str(payload.get("preferred_username") or payload.get("name") or payload.get("email") or ""),
            email=_as_optional_str(payload.get("email")),
            idp_key=self._issuer,
        )

    async def verify_token(self, token: str, *, audience: str | None = None) -> IdentityClaims:
        """经 JWKS 验签票据并校验声明（`exp` / `iss` / 可选 `aud`）。

        `kid` 未命中 / 验签失败时强制刷新一次 JWKS 再试（容忍密钥轮换）。

        Args:
            token: JWT 紧凑串。
            audience: 期望受众（可选；给定则要求命中 `aud`）。

        Returns:
            IdentityClaims: 验签后的身份声明（`idp_key` 取 issuer）。

        Raises:
            ServiceUnavailableError: JWKS 不可达（10007 / 503）。
            AuthError: 验签 / 声明校验失败（20001 / 401）。
        """
        jwks_uri = _require_str(await self._metadata(), "jwks_uri", self._issuer)
        key_set = await self._jwks.get(jwks_uri)
        try:
            claims = verify_jwt(token, key_set, issuer=self._issuer, audience=audience)
        except AuthError:
            key_set = await self._jwks.get(jwks_uri, force=True)
            claims = verify_jwt(token, key_set, issuer=self._issuer, audience=audience)
        return replace(claims, idp_key=self._issuer)

    async def _metadata(self) -> Mapping[str, object]:
        """取 Discovery 元数据（进程内缓存，TTL 内命中）。

        Returns:
            Mapping[str, object]: `/.well-known/openid-configuration` 文档。

        Raises:
            ServiceUnavailableError: 发现端点不可达 / 非 2xx（10007 / 503）。
            ConfigError: 发现文档非对象（40001）。
        """
        now = time.monotonic()
        cached = self._metadata_cache
        if cached is not None and cached[0] > now:
            return cached[1]
        metadata = await self._request_json(
            f"{self._issuer}/.well-known/openid-configuration",
            method="GET",
        )
        self._metadata_cache = (now + self._discovery_cache_ttl, metadata)
        return metadata

    async def _request_json(
        self,
        url: str,
        *,
        method: str,
        data: Mapping[str, str] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> Mapping[str, object]:
        """调 OIDC 端点并解析 JSON 对象。

        Args:
            url: 端点 URL。
            method: HTTP 方法（GET / POST）。
            data: 表单数据（POST）。
            headers: 请求头。

        Returns:
            Mapping[str, object]: 响应 JSON 对象。

        Raises:
            ServiceUnavailableError: 网络 / 非 2xx（10007 / 503）。
            ConfigError: 响应体非 JSON 对象（40001）。
        """
        try:
            async with httpx.AsyncClient(timeout=self._timeout, transport=self._transport) as client:
                response = await client.request(method, url, data=data, headers=headers)
                response.raise_for_status()
                payload: object = response.json()
        except httpx.HTTPError as exc:
            raise ServiceUnavailableError(f"OIDC 端点调用失败：{url}") from exc
        if not isinstance(payload, Mapping):
            raise ConfigError(f"OIDC 端点响应非对象：{url}")
        return cast("Mapping[str, object]", payload)


class OidcIdentityProviderFactory(BasePluginFactory[OidcIdentityProvider]):
    """OIDC 身份源工厂（读取 `[identity_provider]`；配置不全拒启）。"""

    plugin_key: str = "identity_provider"
    plugin_name: str = "oidc"

    def __init__(self, settings: Settings) -> None:
        """初始化。

        Args:
            settings: 应用配置。
        """
        self._settings = settings

    def create(self, options: None = None) -> OidcIdentityProvider:
        """构造 OIDC 身份源实例。

        Args:
            options: 未使用（零参口径）。

        Returns:
            OidcIdentityProvider: OIDC 客户端实例。

        Raises:
            PluginError: issuer / client_id / client_secret 缺失（40002）。
        """
        config: IdentityProviderSettings = self._settings.identity_provider
        missing = [
            name
            for name, value in (
                ("issuer", config.issuer),
                ("client_id", config.client_id),
                ("client_secret", config.client_secret),
            )
            if not value
        ]
        if missing:
            raise PluginError(
                "OIDC 身份源配置缺失：" + "、".join(missing) + "（secret 经 BMS_IDENTITY_PROVIDER__CLIENT_SECRET 注入）"
            )
        return OidcIdentityProvider(
            issuer=config.issuer,
            client_id=config.client_id,
            client_secret=config.client_secret,
            redirect_uri=config.redirect_uri,
            scopes=config.scopes,
            discovery_cache_ttl=config.discovery_cache_ttl,
            jwks_cache_ttl=config.jwks_cache_ttl,
        )


def _require_str(metadata: Mapping[str, object], key: str, issuer: str) -> str:
    """取 Discovery 文档中的字符串字段。

    Args:
        metadata: Discovery 文档。
        key: 字段名。
        issuer: issuer（错误提示用）。

    Returns:
        str: 字段值。

    Raises:
        ConfigError: 字段缺失或非字符串（40001）。
    """
    value = metadata.get(key)
    if not isinstance(value, str) or not value:
        raise ConfigError(f"OIDC Discovery 文档缺字段 {key}：{issuer}")
    return value


def _as_int(value: object) -> int:
    """归一化数值字段。

    Args:
        value: 原始值。

    Returns:
        int: 数值（非法 / 缺失取 0）。
    """
    return int(value) if isinstance(value, (int, float)) else 0


def _as_optional_str(value: object) -> str | None:
    """归一化可选字符串字段。

    Args:
        value: 原始值。

    Returns:
        str | None: 字符串或 None。
    """
    return str(value) if isinstance(value, str) and value else None
