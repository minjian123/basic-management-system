"""idp 能力域真实实现：OIDC 客户端（Discovery / 授权 / 换码 / userinfo / JWKS 票据校验）。

- `OidcIdentityProvider`（`plugin_name = "oidc"`）：以 `issuer` 为发现基点，经 `httpx` 调 OIDC 端点；
  Discovery 元数据与 JWKS 各自缓存；`verify_token` 经 `idp/jwks.py` 按 JWKS 验签并校验 `exp` / `iss` / `aud`。
- `OidcIdentityProviderFactory`：显式工厂（读取 `[identity_provider]`；配置不全启动期拒启）。

口径：本实现只做**客户端侧**（BMS 接外部 IdP）；完整登录链路（回调路由 / state 与 nonce / PKCE）与
JIT 建号归阶段六；BMS 兼作 OIDC Provider 归 `bms_core/oauth/`。客户端凭据一律经构造注入（源为环境变量 / Secret）。
"""

from __future__ import annotations

import time
from collections.abc import Mapping
from dataclasses import replace
from typing import cast
from urllib.parse import urlencode

import httpx

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.config import IdentityProviderSettings, Settings
from bms_core.core.exceptions import AuthError, ConfigError, PluginError, ServiceUnavailableError
from bms_core.core.factory import BasePluginFactory
from bms_core.idp.base import BaseIdentityProvider, IdentityClaims, IdentityToken, IdentityUser, IdpProbeResult
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
        scopes: ConcurrentStableList[str] | None = None,
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
        self._scopes = tuple(_DEFAULT_SCOPES if scopes is None else scopes)
        self._discovery_cache_ttl = discovery_cache_ttl
        self._timeout = timeout
        self._transport = transport
        self._metadata_cache: tuple[float, ConcurrentStableDict[str, object]] | None = None
        self._jwks = JwksCache(ttl=jwks_cache_ttl, timeout=timeout, transport=transport)

    async def authorize(
        self,
        state: str,
        *,
        nonce: str | None = None,
        code_challenge: str | None = None,
        code_challenge_method: str | None = None,
        service: str | None = None,
    ) -> str:
        """构造授权入口 URL（授权码流程；state / nonce 由调用方生成并持有、回调校验）。

        Args:
            state: 防 CSRF 的 state。
            nonce: OIDC nonce（可选；写入授权请求，回调校验 ID Token `nonce` 声明）。
            code_challenge: PKCE challenge（可选；`S256` 为 `BASE64URL(SHA256(verifier))`）。
            code_challenge_method: PKCE 方法（可选；缺省 `S256`）。
            service: 服务地址（OIDC 忽略；仅 CAS 等协议使用）。

        Returns:
            str: 授权入口 URL。

        Raises:
            ConfigError: Discovery 文档缺 `authorization_endpoint`（40001）。
        """
        del service
        metadata = await self._metadata()
        endpoint = _require_str(metadata, "authorization_endpoint", self._issuer)
        query: ConcurrentStableDict[str, str] = ConcurrentStableDict(
            {
                "response_type": "code",
                "client_id": self._client_id,
                "redirect_uri": self._redirect_uri,
                "scope": " ".join(self._scopes),
                "state": state,
            }
        )
        if nonce:
            query.set("nonce", nonce)
        if code_challenge:
            query.set("code_challenge", code_challenge)
            query.set("code_challenge_method", code_challenge_method or "S256")
        separator = "&" if "?" in endpoint else "?"
        return f"{endpoint}{separator}{urlencode(query)}"

    async def exchange_token(
        self,
        code: str,
        *,
        code_verifier: str | None = None,
        service: str | None = None,
    ) -> IdentityToken:
        """用授权码换取令牌（含 ID Token / 刷新令牌）。

        Args:
            code: 授权码。
            code_verifier: PKCE code_verifier（可选；授权时提交了 `code_challenge` 则必传）。
            service: 服务地址（OIDC 忽略；仅 CAS 等协议使用）。

        Returns:
            IdentityToken: 令牌响应。

        Raises:
            ConfigError: Discovery 文档缺 `token_endpoint`（40001）。
            ServiceUnavailableError: 令牌端点不可达 / 非 2xx（10007 / 503）。
        """
        metadata = await self._metadata()
        endpoint = _require_str(metadata, "token_endpoint", self._issuer)
        del service
        data: ConcurrentStableDict[str, str] = ConcurrentStableDict(
            {
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": self._redirect_uri,
                "client_id": self._client_id,
                "client_secret": self._client_secret,
            }
        )
        if code_verifier:
            data.set("code_verifier", code_verifier)
        payload = await self._request_json(endpoint, method="POST", data=data)
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
            headers=ConcurrentStableDict({"Authorization": f"Bearer {access_token}"}),
        )
        return IdentityUser(
            subject=str(payload.get("sub", "")),
            username=str(payload.get("preferred_username") or payload.get("name") or payload.get("email") or ""),
            email=_as_optional_str(payload.get("email")),
            idp_key=self._issuer,
        )

    async def verify_token(
        self,
        token: str,
        *,
        audience: str | None = None,
        nonce: str | None = None,
    ) -> IdentityClaims:
        """经 JWKS 验签票据并校验声明（`exp` / `iss` / 可选 `aud` / 可选 `nonce`）。

        `kid` 未命中 / 验签失败时强制刷新一次 JWKS 再试（容忍密钥轮换）。

        Args:
            token: JWT 紧凑串。
            audience: 期望受众（可选；给定则要求命中 `aud`）。
            nonce: 期望 nonce（可选；给定则要求 ID Token `nonce` 声明一致）。

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
        if nonce is not None and str(claims.payload.get("nonce") or "") != nonce:
            raise AuthError("OIDC ID Token nonce 校验失败")
        return replace(claims, idp_key=self._issuer)

    async def probe(self) -> IdpProbeResult:
        """连通性探测：拉取 Discovery 文档并校验关键字段。

        Returns:
            IdpProbeResult: 可达且文档合规为 True；否则 False（`detail` 只记摘要）。
        """
        url = f"{self._issuer}/.well-known/openid-configuration"
        try:
            async with httpx.AsyncClient(timeout=self._timeout, transport=self._transport) as client:
                response = await client.get(url)
        except httpx.HTTPError:
            return IdpProbeResult(reachable=False, protocol="oidc", detail="Discovery 端点不可达")
        if not response.is_success:
            return IdpProbeResult(
                reachable=False,
                protocol="oidc",
                status=response.status_code,
                detail="Discovery 端点返回非 2xx",
            )
        try:
            payload: object = response.json()
        except ValueError:
            return IdpProbeResult(
                reachable=False,
                protocol="oidc",
                status=response.status_code,
                detail="Discovery 响应非合法 JSON",
            )
        if not isinstance(payload, Mapping):
            return IdpProbeResult(
                reachable=False,
                protocol="oidc",
                status=response.status_code,
                detail="Discovery 响应非对象",
            )
        metadata = cast("Mapping[str, object]", payload)
        required = ("issuer", "authorization_endpoint", "token_endpoint")
        if any(not isinstance(metadata.get(key), str) for key in required):
            return IdpProbeResult(
                reachable=False,
                protocol="oidc",
                status=response.status_code,
                detail="Discovery 文档缺关键字段",
            )
        return IdpProbeResult(reachable=True, protocol="oidc", status=response.status_code, detail="Discovery 正常")

    async def _metadata(self) -> ConcurrentStableDict[str, object]:
        """取 Discovery 元数据（进程内缓存，TTL 内命中）。

        Returns:
            ConcurrentStableDict[str, object]: `/.well-known/openid-configuration` 文档。

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
        data: ConcurrentStableDict[str, str] | None = None,
        headers: ConcurrentStableDict[str, str] | None = None,
    ) -> ConcurrentStableDict[str, object]:
        """调 OIDC 端点并解析 JSON 对象。

        Args:
            url: 端点 URL。
            method: HTTP 方法（GET / POST）。
            data: 表单数据（POST）。
            headers: 请求头。

        Returns:
            ConcurrentStableDict[str, object]: 响应 JSON 对象。

        Raises:
            ServiceUnavailableError: 网络 / 非 2xx（10007 / 503）。
            ConfigError: 响应体非 JSON 对象（40001）。
        """
        try:
            async with httpx.AsyncClient(timeout=self._timeout, transport=self._transport) as client:
                response = await client.request(
                    method,
                    url,
                    data=None if data is None else dict(data),
                    headers=None if headers is None else dict(headers),
                )
                response.raise_for_status()
                payload: object = response.json()
        except httpx.HTTPError as exc:
            raise ServiceUnavailableError(f"OIDC 端点调用失败：{url}") from exc
        if not isinstance(payload, Mapping):
            raise ConfigError(f"OIDC 端点响应非对象：{url}")
        return ConcurrentStableDict(cast("Mapping[str, object]", payload))


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


def _require_str(metadata: ConcurrentStableDict[str, object], key: str, issuer: str) -> str:
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
