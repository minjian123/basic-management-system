"""idp 能力域真实实现：企业微信（WeCom）免登客户端（扫码 / 内嵌 H5 授权 + 成员身份解析）。

- `WecomIdentityProvider`（`plugin_name = "wecom"`）：`authorize` 支持 `mode="qr"`（PC 扫码，官方新版
  登录链接 `login.work.weixin.qq.com/wwlogin/sso/login`）与 `mode="oauth"`（企微内置 Webview / 移动端 H5
  网页授权 `open.weixin.qq.com/connect/oauth2/authorize`）；`exchange_token` 以应用 `access_token`
  （`gettoken`，进程内缓存）调 `cgi-bin/auth/getuserinfo` 取成员身份（企业成员 `userid`，非成员回落 `openid`），
  经 `IdentityToken.identity` 一次回填（无独立 userinfo 时序）。
- `WecomIdentityProviderFactory`：显式工厂（读取 `[identity_provider]`；`corp_id` / `agent_id` / `secret`
  缺失拒启）。

口径：扫码登录与网页授权回跳的 `code` 均走同一换身份接口；扫码 `code` 不返回 `user_ticket`，本期不取敏感信息。
"""

from __future__ import annotations

import time
from collections.abc import Mapping
from typing import cast
from urllib.parse import urlencode

import httpx

from bms_core.core.config import IdentityProviderSettings, Settings
from bms_core.core.exceptions import (
    ConfigError,
    PluginError,
    WecomAuthError,
    WecomConfigError,
    WecomUnavailableError,
)
from bms_core.core.factory import BasePluginFactory
from bms_core.idp.base import BaseIdentityProvider, IdentityToken, IdentityUser, IdpProbeResult

__all__ = [
    "WecomIdentityProvider",
    "WecomIdentityProviderFactory",
]

_HTTP_TIMEOUT = 10.0
"""企业微信接口调用超时（秒）。"""

_DEFAULT_LOGIN_URL = "https://login.work.weixin.qq.com/wwlogin/sso/login"
"""扫码登录入口（`mode=qr`）。"""

_DEFAULT_OAUTH_URL = "https://open.weixin.qq.com/connect/oauth2/authorize"
"""网页授权入口（`mode=oauth`）。"""

_DEFAULT_API_BASE_URL = "https://qyapi.weixin.qq.com"
"""服务端接口基址。"""

_DEFAULT_SCOPE = "snsapi_base"
"""网页授权缺省 scope（静默授权，仅取 `userid`）。"""

_DEFAULT_LOGIN_TYPE = "CorpApp"
"""扫码登录缺省登录类型（企业自建 / 代开发应用）。"""

_TOKEN_SKEW = 120.0
"""应用令牌提前过期余量（秒；避免临界时刻使用失效令牌）。"""

_DEFAULT_TOKEN_TTL = 7200.0
"""应用令牌缺省有效期（秒；`expires_in` 缺失时回落）。"""


class WecomIdentityProvider(BaseIdentityProvider):
    """企业微信客户端：扫码 / 内嵌 H5 授权跳转 + `code` 换成员身份。"""

    plugin_name: str = "wecom"

    def __init__(
        self,
        *,
        corp_id: str,
        agent_id: str,
        secret: str,
        redirect_uri: str,
        mode: str = "qr",
        login_url: str = _DEFAULT_LOGIN_URL,
        oauth_url: str = _DEFAULT_OAUTH_URL,
        api_base_url: str = _DEFAULT_API_BASE_URL,
        scope: str = _DEFAULT_SCOPE,
        login_type: str = _DEFAULT_LOGIN_TYPE,
        timeout: float = _HTTP_TIMEOUT,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        """初始化。

        Args:
            corp_id: 企业 CorpID（授权 `appid`）。
            agent_id: 应用 AgentID（扫码与 H5 授权携带）。
            secret: 应用密钥（源为环境变量 / Secret）。
            redirect_uri: 回调地址（须为应用配置的可信域名）。
            mode: 授权形态（`qr` 扫码 / `oauth` 内嵌 H5）。
            login_url: 扫码登录入口（`mode=qr`）。
            oauth_url: 网页授权入口（`mode=oauth`）。
            api_base_url: 服务端接口基址。
            scope: 网页授权 scope（`mode=oauth`）。
            login_type: 扫码登录类型（`mode=qr`）。
            timeout: 接口调用超时（秒）。
            transport: 出站传输（测试注入 MockTransport；缺省走真实网络）。
        """
        self._corp_id = corp_id
        self._agent_id = agent_id
        self._secret = secret
        self._redirect_uri = redirect_uri
        self._mode = mode or "qr"
        self._login_url = login_url or _DEFAULT_LOGIN_URL
        self._oauth_url = oauth_url or _DEFAULT_OAUTH_URL
        self._api_base_url = (api_base_url or _DEFAULT_API_BASE_URL).rstrip("/")
        self._scope = scope or _DEFAULT_SCOPE
        self._login_type = login_type or _DEFAULT_LOGIN_TYPE
        self._timeout = timeout
        self._transport = transport
        self._token_cache: tuple[float, str] | None = None

    async def authorize(
        self,
        state: str,
        *,
        nonce: str | None = None,
        code_challenge: str | None = None,
        code_challenge_method: str | None = None,
        service: str | None = None,
    ) -> str:
        """构造授权入口 URL（扫码或内嵌 H5；`nonce` / PKCE / `service` 忽略）。

        Args:
            state: 防 CSRF 的 state。
            nonce: OIDC nonce（企微忽略）。
            code_challenge: PKCE challenge（企微忽略）。
            code_challenge_method: PKCE 方法（企微忽略）。
            service: 服务地址（企微忽略）。

        Returns:
            str: 授权入口 URL。
        """
        del nonce, code_challenge, code_challenge_method, service
        if self._mode == "oauth":
            query: dict[str, str] = {
                "appid": self._corp_id,
                "redirect_uri": self._redirect_uri,
                "response_type": "code",
                "scope": self._scope,
                "state": state,
                "agentid": self._agent_id,
            }
            return f"{self._oauth_url}?{urlencode(query)}#wechat_redirect"
        query = {
            "login_type": self._login_type,
            "appid": self._corp_id,
            "agentid": self._agent_id,
            "redirect_uri": self._redirect_uri,
            "state": state,
        }
        return f"{self._login_url}?{urlencode(query)}"

    async def exchange_token(
        self,
        code: str,
        *,
        code_verifier: str | None = None,
        service: str | None = None,
    ) -> IdentityToken:
        """以 `code` 换成员身份（`gettoken` + `getuserinfo`，一次取回）。

        Args:
            code: 授权码（扫码 / 网页授权回跳携带）。
            code_verifier: PKCE code_verifier（企微忽略）。
            service: 服务地址（企微忽略）。

        Returns:
            IdentityToken: `access_token` 为空串，身份经 `identity` 回填。

        Raises:
            WecomConfigError: 应用凭据无效（`gettoken` 返回凭据类 `errcode`）。
            WecomAuthError: `code` 无效 / 用户未授权（`getuserinfo` 返回 `errcode`）/ 未返回身份标识。
            WecomUnavailableError: 接口不可达 / 超时 / 非 2xx / 响应非法。
        """
        del code_verifier, service
        access_token = await self._access_token()
        payload = await self._get(
            f"{self._api_base_url}/cgi-bin/auth/getuserinfo",
            params={"access_token": access_token, "code": code},
        )
        errcode = _as_int(payload.get("errcode"))
        if errcode != 0:
            raise WecomAuthError(f"企业微信获取用户身份失败：errcode={errcode}")
        subject = _as_str(payload.get("userid")) or _as_str(payload.get("openid"))
        if not subject:
            raise WecomAuthError("企业微信未返回用户身份标识")
        return IdentityToken(
            access_token="",
            identity=IdentityUser(subject=subject, username=subject, idp_key=self._corp_id),
        )

    async def userinfo(self, access_token: str) -> IdentityUser:
        """企微主体随 `code` 换取一次取回，无独立 userinfo 时序。

        Args:
            access_token: 访问令牌（企微无此概念）。

        Raises:
            ConfigError: 企业微信不支持独立 userinfo（40001）。
        """
        del access_token
        raise ConfigError("企业微信协议不支持独立 userinfo（主体随 code 换取一次取回）")

    async def probe(self) -> IdpProbeResult:
        """连通性探测：调 `gettoken` 验证应用凭据与端点可达性。

        凭据有效（`errcode == 0`）为可达；接口可达但凭据 / 配置异常（`errcode != 0`）记为不可达，
        `detail` 记 errcode 数值（不透传原始报文）。

        Returns:
            IdpProbeResult: 凭据有效且可达为 True；否则 False（`detail` 只记摘要）。
        """
        url = f"{self._api_base_url}/cgi-bin/gettoken"
        try:
            async with httpx.AsyncClient(timeout=self._timeout, transport=self._transport) as client:
                response = await client.get(url, params={"corpid": self._corp_id, "corpsecret": self._secret})
                response.raise_for_status()
                payload: object = response.json()
        except httpx.HTTPError, ValueError:
            return IdpProbeResult(reachable=False, protocol="wecom", detail="企业微信接口不可达")
        if not isinstance(payload, Mapping):
            return IdpProbeResult(reachable=False, protocol="wecom", detail="企业微信响应非对象")
        errcode = _as_int(cast("Mapping[str, object]", payload).get("errcode"))
        if errcode == 0:
            return IdpProbeResult(reachable=True, protocol="wecom", status=200, detail="gettoken 正常（凭据有效）")
        return IdpProbeResult(
            reachable=False,
            protocol="wecom",
            status=200,
            detail=f"接口可达但凭据 / 配置异常（errcode={errcode}）",
        )

    async def _access_token(self) -> str:
        """取应用 `access_token`（进程内缓存，命中且未过期复用）。

        Returns:
            str: 应用 `access_token`。

        Raises:
            WecomConfigError: 凭据无效 / 未返回令牌。
            WecomUnavailableError: 接口不可达 / 超时 / 非 2xx / 响应非法。
        """
        now = time.monotonic()
        cached = self._token_cache
        if cached is not None and cached[0] > now:
            return cached[1]
        payload = await self._get(
            f"{self._api_base_url}/cgi-bin/gettoken",
            params={"corpid": self._corp_id, "corpsecret": self._secret},
        )
        errcode = _as_int(payload.get("errcode"))
        if errcode != 0:
            raise WecomConfigError(f"企业微信获取 access_token 失败：errcode={errcode}")
        token = _as_str(payload.get("access_token"))
        if not token:
            raise WecomConfigError("企业微信未返回 access_token")
        expires_in = _as_int(payload.get("expires_in"))
        effective = float(expires_in) if expires_in > 0 else _DEFAULT_TOKEN_TTL
        self._token_cache = (now + max(effective - _TOKEN_SKEW, 1.0), token)
        return token

    async def _get(self, url: str, *, params: Mapping[str, str]) -> Mapping[str, object]:
        """调企微接口并解析 JSON 对象。

        Args:
            url: 接口 URL。
            params: 查询参数。

        Returns:
            Mapping[str, object]: 响应 JSON 对象。

        Raises:
            WecomUnavailableError: 网络 / 非 2xx / 响应非 JSON 对象。
        """
        try:
            async with httpx.AsyncClient(timeout=self._timeout, transport=self._transport) as client:
                response = await client.get(url, params=params)
                response.raise_for_status()
                payload: object = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise WecomUnavailableError(f"企业微信接口调用失败：{url}") from exc
        if not isinstance(payload, Mapping):
            raise WecomUnavailableError(f"企业微信接口响应非对象：{url}")
        return cast("Mapping[str, object]", payload)


class WecomIdentityProviderFactory(BasePluginFactory[WecomIdentityProvider]):
    """企业微信身份源工厂（读取 `[identity_provider]`；`corp_id` / `agent_id` / `secret` 缺失拒启）。"""

    plugin_key: str = "identity_provider"
    plugin_name: str = "wecom"

    def __init__(self, settings: Settings) -> None:
        """初始化。

        Args:
            settings: 应用配置。
        """
        self._settings = settings

    def create(self, options: None = None) -> WecomIdentityProvider:
        """构造企业微信身份源实例。

        Args:
            options: 未使用（零参口径）。

        Returns:
            WecomIdentityProvider: 企业微信客户端实例。

        Raises:
            PluginError: `corp_id` / `agent_id` / `secret` 缺失（40002）。
        """
        del options
        config: IdentityProviderSettings = self._settings.identity_provider
        missing = [
            name
            for name, value in (
                ("wecom_corp_id", config.wecom_corp_id),
                ("wecom_agent_id", config.wecom_agent_id),
                ("wecom_secret", config.wecom_secret),
            )
            if not value
        ]
        if missing:
            raise PluginError(
                "企业微信身份源配置缺失："
                + "、".join(missing)
                + "（secret 经 BMS_IDENTITY_PROVIDER__WECOM_SECRET 注入）"
            )
        return WecomIdentityProvider(
            corp_id=config.wecom_corp_id,
            agent_id=config.wecom_agent_id,
            secret=config.wecom_secret,
            redirect_uri=config.redirect_uri,
            mode=config.wecom_mode,
            login_url=config.wecom_login_url,
            oauth_url=config.wecom_oauth_url,
            api_base_url=config.wecom_api_base_url,
            scope=config.wecom_scope,
            login_type=config.wecom_login_type,
        )


def _as_int(value: object) -> int:
    """归一化数值字段。

    Args:
        value: 原始值。

    Returns:
        int: 数值（非法 / 缺失取 0）。
    """
    return int(value) if isinstance(value, (int, float)) else 0


def _as_str(value: object) -> str:
    """归一化字符串字段。

    Args:
        value: 原始值。

    Returns:
        str: 字符串值（非字符串 / 缺失返回空串）。
    """
    return value if isinstance(value, str) else ""
