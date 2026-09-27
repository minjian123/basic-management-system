"""idp 能力域真实实现：钉钉（DingTalk）免登客户端（新版 OAuth2 扫码登录 + 用户信息解析）。

- `DingtalkIdentityProvider`（`plugin_name = "dingtalk"`）：`authorize` 走新版 OAuth2 授权入口
  （`login.dingtalk.com/oauth2/auth`）；`exchange_token` 以授权码调 `v1.0/oauth2/userAccessToken` 换用户级
  访问令牌；`userinfo` 携带 `x-acs-dingtalk-access-token` 调 `v1.0/contact/users/me` 取身份
  （`unionId` 优先，回落 `openId`）。
- `DingtalkIdentityProviderFactory`：显式工厂（读取 `[identity_provider]`；`client_id` / `client_secret`
  缺失拒启）。

口径：仅实现官方主推的新版 OAuth2；旧版 `oapi.dingtalk.com/connect/*` 与 `sns/getuserinfo_bycode` 签名链路
不实现（见任务详细设计「边界与开放项」）。回跳 `code` 与 `authCode` 同值，回调按既有 `code` 参数接收即可。
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import cast
from urllib.parse import urlencode

import httpx

from bms_core.core.config import IdentityProviderSettings, Settings
from bms_core.core.exceptions import DingtalkAuthError, DingtalkUnavailableError, PluginError
from bms_core.core.factory import BasePluginFactory
from bms_core.idp.base import BaseIdentityProvider, IdentityToken, IdentityUser, IdpProbeResult

__all__ = [
    "DingtalkIdentityProvider",
    "DingtalkIdentityProviderFactory",
]

_HTTP_TIMEOUT = 10.0
"""钉钉接口调用超时（秒）。"""

_DEFAULT_LOGIN_URL = "https://login.dingtalk.com/oauth2/auth"
"""新版 OAuth2 授权入口。"""

_DEFAULT_API_BASE_URL = "https://api.dingtalk.com"
"""新版服务端接口基址。"""

_DEFAULT_SCOPE = "openid"
"""授权缺省 scope。"""

_DEFAULT_PROMPT = "consent"
"""授权缺省确认方式（进入授权确认页）。"""


class DingtalkIdentityProvider(BaseIdentityProvider):
    """钉钉客户端：新版 OAuth2 授权跳转 + 用户令牌换取 + 用户信息解析。"""

    plugin_name: str = "dingtalk"

    def __init__(
        self,
        *,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        login_url: str = _DEFAULT_LOGIN_URL,
        api_base_url: str = _DEFAULT_API_BASE_URL,
        scope: str = _DEFAULT_SCOPE,
        prompt: str = _DEFAULT_PROMPT,
        timeout: float = _HTTP_TIMEOUT,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        """初始化。

        Args:
            client_id: Client ID / AppKey。
            client_secret: Client Secret / AppSecret（源为环境变量 / Secret）。
            redirect_uri: 回调地址（须与后台登记一致）。
            login_url: 授权入口。
            api_base_url: 服务端接口基址。
            scope: 授权 scope（`openid` 或 `openid corpid`）。
            prompt: 授权确认方式。
            timeout: 接口调用超时（秒）。
            transport: 出站传输（测试注入 MockTransport；缺省走真实网络）。
        """
        self._client_id = client_id
        self._client_secret = client_secret
        self._redirect_uri = redirect_uri
        self._login_url = login_url or _DEFAULT_LOGIN_URL
        self._api_base_url = (api_base_url or _DEFAULT_API_BASE_URL).rstrip("/")
        self._scope = scope or _DEFAULT_SCOPE
        self._prompt = prompt or _DEFAULT_PROMPT
        self._timeout = timeout
        self._transport = transport

    async def authorize(
        self,
        state: str,
        *,
        nonce: str | None = None,
        code_challenge: str | None = None,
        code_challenge_method: str | None = None,
        service: str | None = None,
    ) -> str:
        """构造钉钉授权入口 URL（`nonce` / PKCE / `service` 忽略）。

        Args:
            state: 防 CSRF 的 state。
            nonce: OIDC nonce（钉钉忽略）。
            code_challenge: PKCE challenge（钉钉忽略）。
            code_challenge_method: PKCE 方法（钉钉忽略）。
            service: 服务地址（钉钉忽略）。

        Returns:
            str: 授权入口 URL。
        """
        del nonce, code_challenge, code_challenge_method, service
        query = {
            "redirect_uri": self._redirect_uri,
            "response_type": "code",
            "client_id": self._client_id,
            "scope": self._scope,
            "state": state,
            "prompt": self._prompt,
        }
        return f"{self._login_url}?{urlencode(query)}"

    async def exchange_token(
        self,
        code: str,
        *,
        code_verifier: str | None = None,
        service: str | None = None,
    ) -> IdentityToken:
        """以授权码换用户级访问令牌。

        Args:
            code: 授权码（回跳 `code` / `authCode`，同值）。
            code_verifier: PKCE code_verifier（钉钉忽略）。
            service: 服务地址（钉钉忽略）。

        Returns:
            IdentityToken: 用户级访问令牌（`userinfo` 据此取用户信息）。

        Raises:
            DingtalkAuthError: 授权码无效 / 用户未授权（4xx）/ 未返回令牌。
            DingtalkUnavailableError: 接口不可达 / 超时 / 5xx / 响应非法。
        """
        del code_verifier, service
        payload = await self._request_json(
            "POST",
            f"{self._api_base_url}/v1.0/oauth2/userAccessToken",
            json_body={
                "clientId": self._client_id,
                "clientSecret": self._client_secret,
                "code": code,
                "grantType": "authorization_code",
            },
        )
        access_token = _as_str(payload.get("accessToken"))
        if not access_token:
            raise DingtalkAuthError("钉钉未返回访问令牌")
        return IdentityToken(
            access_token=access_token,
            token_type="Bearer",
            expires_in=_as_int(payload.get("expireIn")),
            refresh_token=_as_optional_str(payload.get("refreshToken")),
        )

    async def userinfo(self, access_token: str) -> IdentityUser:
        """以用户级访问令牌取用户信息（`unionId` 优先，回落 `openId`）。

        Args:
            access_token: 用户级访问令牌。

        Returns:
            IdentityUser: 身份源用户（`idp_key` 取 Client ID）。

        Raises:
            DingtalkAuthError: 令牌无效（4xx）/ 未返回身份标识。
            DingtalkUnavailableError: 接口不可达 / 超时 / 5xx / 响应非法。
        """
        payload = await self._request_json(
            "GET",
            f"{self._api_base_url}/v1.0/contact/users/me",
            headers={"x-acs-dingtalk-access-token": access_token},
        )
        subject = _as_str(payload.get("unionId")) or _as_str(payload.get("openId"))
        if not subject:
            raise DingtalkAuthError("钉钉未返回用户身份标识")
        nick = _as_str(payload.get("nick")) or subject
        return IdentityUser(
            subject=subject,
            username=nick,
            name=nick,
            email=_as_optional_str(payload.get("email")),
            idp_key=self._client_id,
        )

    async def probe(self) -> IdpProbeResult:
        """连通性探测：调 `userAccessToken`（占位 `code`），端点可达即为 True。

        无有效 `code` 时钉钉返回 4xx（属预期），据此判定端点可达；网络不可达 / 5xx 记为不可达。
        `detail` 只记摘要（不校验凭据真伪，真实凭据验证归真实联调）。

        Returns:
            IdpProbeResult: 端点可达为 True；网络 / 服务异常为 False。
        """
        url = f"{self._api_base_url}/v1.0/oauth2/userAccessToken"
        body = {
            "clientId": self._client_id,
            "clientSecret": self._client_secret,
            "code": "__connectivity_probe__",
            "grantType": "authorization_code",
        }
        try:
            async with httpx.AsyncClient(timeout=self._timeout, transport=self._transport) as client:
                response = await client.post(url, json=body)
        except httpx.HTTPError:
            return IdpProbeResult(reachable=False, protocol="dingtalk", detail="钉钉接口不可达")
        if response.status_code >= 500:
            return IdpProbeResult(
                reachable=False,
                protocol="dingtalk",
                status=response.status_code,
                detail="钉钉接口服务异常",
            )
        return IdpProbeResult(
            reachable=True,
            protocol="dingtalk",
            status=response.status_code,
            detail="钉钉端点可达（未带有效 code，仅探活）",
        )

    async def _request_json(
        self,
        method: str,
        url: str,
        *,
        json_body: Mapping[str, str] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> Mapping[str, object]:
        """调钉钉接口并解析 JSON 对象（按状态码区分授权失败与不可达）。

        Args:
            method: HTTP 方法。
            url: 接口 URL。
            json_body: 请求体（POST）。
            headers: 请求头。

        Returns:
            Mapping[str, object]: 响应 JSON 对象。

        Raises:
            DingtalkAuthError: 4xx（授权码 / 令牌无效）。
            DingtalkUnavailableError: 网络 / 超时 / 5xx / 响应非 JSON 对象。
        """
        try:
            async with httpx.AsyncClient(timeout=self._timeout, transport=self._transport) as client:
                response = await client.request(method, url, json=json_body, headers=headers)
        except httpx.HTTPError as exc:
            raise DingtalkUnavailableError(f"钉钉接口调用失败：{url}") from exc
        if response.status_code >= 500:
            raise DingtalkUnavailableError(f"钉钉接口服务异常：{url}")
        if response.status_code >= 400:
            raise DingtalkAuthError(f"钉钉接口拒绝请求：{url}")
        try:
            payload: object = response.json()
        except ValueError as exc:
            raise DingtalkUnavailableError(f"钉钉接口响应非合法 JSON：{url}") from exc
        if not isinstance(payload, Mapping):
            raise DingtalkUnavailableError(f"钉钉接口响应非对象：{url}")
        return cast("Mapping[str, object]", payload)


class DingtalkIdentityProviderFactory(BasePluginFactory[DingtalkIdentityProvider]):
    """钉钉身份源工厂（读取 `[identity_provider]`；`client_id` / `client_secret` 缺失拒启）。"""

    plugin_key: str = "identity_provider"
    plugin_name: str = "dingtalk"

    def __init__(self, settings: Settings) -> None:
        """初始化。

        Args:
            settings: 应用配置。
        """
        self._settings = settings

    def create(self, options: None = None) -> DingtalkIdentityProvider:
        """构造钉钉身份源实例。

        Args:
            options: 未使用（零参口径）。

        Returns:
            DingtalkIdentityProvider: 钉钉客户端实例。

        Raises:
            PluginError: `client_id` / `client_secret` 缺失（40002）。
        """
        del options
        config: IdentityProviderSettings = self._settings.identity_provider
        missing = [
            name
            for name, value in (
                ("dingtalk_client_id", config.dingtalk_client_id),
                ("dingtalk_client_secret", config.dingtalk_client_secret),
            )
            if not value
        ]
        if missing:
            raise PluginError(
                "钉钉身份源配置缺失："
                + "、".join(missing)
                + "（secret 经 BMS_IDENTITY_PROVIDER__DINGTALK_CLIENT_SECRET 注入）"
            )
        return DingtalkIdentityProvider(
            client_id=config.dingtalk_client_id,
            client_secret=config.dingtalk_client_secret,
            redirect_uri=config.redirect_uri,
            login_url=config.dingtalk_login_url,
            api_base_url=config.dingtalk_api_base_url,
            scope=config.dingtalk_scope,
            prompt=config.dingtalk_prompt,
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


def _as_optional_str(value: object) -> str | None:
    """归一化可选字符串字段。

    Args:
        value: 原始值。

    Returns:
        str | None: 非空字符串或 None。
    """
    return value if isinstance(value, str) and value else None
