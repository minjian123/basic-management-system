"""idp 能力域真实实现：CAS 客户端（授权跳转 / serviceValidate 票据校验 / 用户属性解析）。

- `CasIdentityProvider`（`plugin_name = "cas"`）：CAS 无令牌交换——授权后 IdP 以服务票据 `ticket` 回跳，
  客户端凭 `ticket` 调 `serviceValidate`（CAS 3.0 `p3/serviceValidate`，含 attributes）换回主体与属性；
  身份经 `IdentityToken.identity` 一次回填（无独立 userinfo 时序）。
- `CasIdentityProviderFactory`：显式工厂（读取 `[identity_provider]`；`cas_server_url` 缺失拒启）。

口径：`service` 由上层（SSO 链路）按 `{redirect_uri}?state={state}` 统一生成并同时传入授权与校验，
保证两处完全一致（provider 只原样使用）；属性映射内置默认候选 + 行配置 `attribute_map` 覆盖；
XML 解析拒绝 `<!DOCTYPE` / `<!ENTITY` 并限制响应体积（防 XXE / 实体膨胀）。
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from collections.abc import Mapping, Sequence
from typing import cast
from urllib.parse import urlencode

import httpx

from bms_core.core.config import IdentityProviderSettings, Settings
from bms_core.core.exceptions import AuthError, ConfigError, PluginError, ServiceUnavailableError
from bms_core.core.factory import BasePluginFactory
from bms_core.idp.base import BaseIdentityProvider, IdentityToken, IdentityUser

__all__ = [
    "CasIdentityProvider",
    "CasIdentityProviderFactory",
    "normalize_attribute_map",
]

_HTTP_TIMEOUT = 10.0
"""CAS 端点调用超时（秒）。"""

_DEFAULT_LOGIN_PATH = "/login"
"""CAS 默认登录端点路径。"""

_DEFAULT_SERVICE_VALIDATE_PATH = "/p3/serviceValidate"
"""CAS 默认校验端点路径（CAS 3.0，含 attributes）。"""

_MAX_RESPONSE_BYTES = 256 * 1024
"""响应体上限（字节；超限按 IdP 响应非法处理，防超大 / 膨胀响应）。"""

_DEFAULT_ATTRIBUTE_MAP: dict[str, tuple[str, ...]] = {
    "username": ("username", "uid", "userName", "account"),
    "name": ("displayName", "cn", "name"),
    "email": ("email", "mail"),
}
"""属性映射默认候选（行配置 `attribute_map` 同名键覆盖）。"""

_FIELDS = ("username", "name", "email")
"""可映射字段（principal 固定取 `subject`，不可配）。"""


class CasIdentityProvider(BaseIdentityProvider):
    """CAS 客户端：授权跳转 / serviceValidate 票据校验 / 属性映射。"""

    plugin_name: str = "cas"

    def __init__(
        self,
        *,
        server_url: str,
        redirect_uri: str,
        login_path: str = _DEFAULT_LOGIN_PATH,
        service_validate_path: str = _DEFAULT_SERVICE_VALIDATE_PATH,
        attribute_map: Mapping[str, Sequence[str]] | None = None,
        timeout: float = _HTTP_TIMEOUT,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        """初始化。

        Args:
            server_url: CAS 服务基址（如 `https://cas.example.com/cas`；尾斜杠自动去除）。
            redirect_uri: 回调地址（登录时作为 `service` 基址，须与校验时一致）。
            login_path: 登录端点路径（缺省 `/login`）。
            service_validate_path: 校验端点路径（缺省 `/p3/serviceValidate`，CAS 3.0）。
            attribute_map: 属性映射覆盖（`{字段: [候选属性名…]}`；缺省用内置默认）。
            timeout: 端点调用超时（秒）。
            transport: 出站传输（测试注入 MockTransport；缺省走真实网络）。
        """
        self._server_url = server_url.rstrip("/")
        self._redirect_uri = redirect_uri
        self._login_path = login_path or _DEFAULT_LOGIN_PATH
        self._service_validate_path = service_validate_path or _DEFAULT_SERVICE_VALIDATE_PATH
        self._attribute_map = _merge_attribute_map(attribute_map)
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
        """构造 CAS 登录入口 URL（`service` 由上层生成，含 `state`）。

        Args:
            state: 防 CSRF 的 state（已由上层嵌入 `service`，此处忽略）。
            nonce: OIDC nonce（CAS 忽略）。
            code_challenge: PKCE challenge（CAS 忽略）。
            code_challenge_method: PKCE 方法（CAS 忽略）。
            service: 服务地址（`{redirect_uri}?state={state}`）；缺省回退 `redirect_uri`。

        Returns:
            str: CAS 登录入口 URL。
        """
        del state, nonce, code_challenge, code_challenge_method
        target = service or self._redirect_uri
        return f"{self._server_url}{self._login_path}?{urlencode({'service': target})}"

    async def exchange_token(
        self,
        code: str,
        *,
        code_verifier: str | None = None,
        service: str | None = None,
    ) -> IdentityToken:
        """票据校验（`serviceValidate`），一次取回主体与属性。

        Args:
            code: 服务票据（`ticket`）。
            code_verifier: PKCE code_verifier（CAS 忽略）。
            service: 服务地址（须与授权时一致）；缺省回退 `redirect_uri`。

        Returns:
            IdentityToken: `access_token` 为空串，身份经 `identity` 回填。

        Raises:
            AuthError: 票据无效 / 服务未注册（`authenticationFailure`）。
            ServiceUnavailableError: 服务不可达 / 超时 / 响应非法（非 XML / 缺节点 / 超限 / 含 DOCTYPE）。
        """
        del code_verifier
        target = service or self._redirect_uri
        url = f"{self._server_url}{self._service_validate_path}"
        params = {"service": target, "ticket": code}
        try:
            async with httpx.AsyncClient(timeout=self._timeout, transport=self._transport) as client:
                response = await client.get(url, params=params)
                response.raise_for_status()
                content = response.content
        except httpx.HTTPError as exc:
            raise ServiceUnavailableError(f"CAS 校验端点调用失败：{url}") from exc

        root = _parse_response(content)
        failure = _find_local(root, "authenticationFailure")
        if failure is not None:
            raise AuthError(f"CAS 票据校验失败：{failure.get('code') or 'unknown'}")
        success = _find_local(root, "authenticationSuccess")
        if success is None:
            raise ServiceUnavailableError("CAS 校验响应缺 authenticationSuccess")
        principal = _child_text(success, "user")
        if not principal:
            raise ServiceUnavailableError("CAS 校验响应缺 principal")
        attributes = _parse_attributes(success)
        return IdentityToken(access_token="", identity=self._build_identity(principal, attributes))

    async def userinfo(self, access_token: str) -> IdentityUser:
        """CAS 主体随票据校验一次取回，无独立 userinfo 时序。

        Args:
            access_token: 访问令牌（CAS 无此概念）。

        Raises:
            ConfigError: CAS 不支持独立 userinfo（40001）。
        """
        del access_token
        raise ConfigError("CAS 协议不支持独立 userinfo（主体随票据校验一次取回）")

    def _build_identity(self, principal: str, attributes: Mapping[str, str]) -> IdentityUser:
        """按映射规则由 principal 与 attributes 构造身份。

        Args:
            principal: CAS 主体（`cas:user`）。
            attributes: 解析后的属性映射。

        Returns:
            IdentityUser: 归一化身份（`idp_key` 取 CAS 服务基址）。
        """
        username = self._first(attributes, "username") or principal
        name = self._first(attributes, "name") or None
        email = self._first(attributes, "email") or None
        return IdentityUser(
            subject=principal,
            username=username,
            name=name,
            email=email,
            idp_key=self._server_url,
        )

    def _first(self, attributes: Mapping[str, str], field: str) -> str:
        """取字段首个命中的属性值（候选序由 `attribute_map` 决定）。

        Args:
            attributes: 解析后的属性映射。
            field: 字段名（`username` / `name` / `email`）。

        Returns:
            str: 首个非空属性值；无命中返回空串。
        """
        for candidate in self._attribute_map.get(field, ()):
            value = attributes.get(candidate, "").strip()
            if value:
                return value
        return ""


class CasIdentityProviderFactory(BasePluginFactory[CasIdentityProvider]):
    """CAS 身份源工厂（读取 `[identity_provider]`；`cas_server_url` 缺失拒启）。"""

    plugin_key: str = "identity_provider"
    plugin_name: str = "cas"

    def __init__(self, settings: Settings) -> None:
        """初始化。

        Args:
            settings: 应用配置。
        """
        self._settings = settings

    def create(self, options: None = None) -> CasIdentityProvider:
        """构造 CAS 身份源实例。

        Args:
            options: 未使用（零参口径）。

        Returns:
            CasIdentityProvider: CAS 客户端实例。

        Raises:
            PluginError: `cas_server_url` 缺失（40002）。
        """
        del options
        config: IdentityProviderSettings = self._settings.identity_provider
        if not config.cas_server_url:
            raise PluginError("CAS 身份源配置缺失：cas_server_url（BMS_IDENTITY_PROVIDER__CAS_SERVER_URL）")
        return CasIdentityProvider(
            server_url=config.cas_server_url,
            redirect_uri=config.redirect_uri,
            login_path=config.cas_login_path,
            service_validate_path=config.cas_service_validate_path,
            attribute_map=config.attribute_map,
        )


def normalize_attribute_map(raw: object) -> dict[str, tuple[str, ...]]:
    """归一化行配置属性映射覆盖（校验类型）。

    Args:
        raw: 行配置 `attribute_map` 原始值。

    Returns:
        dict[str, tuple[str, ...]]: 字段 → 候选属性名（仅含合法字段；空返回空 dict）。

    Raises:
        ConfigError: 非对象 / 值非字符串数组（40001）。
    """
    if raw is None:
        return {}
    if not isinstance(raw, Mapping):
        raise ConfigError("身份源行配置 attribute_map 必须是对象")
    normalized: dict[str, tuple[str, ...]] = {}
    for key, value in cast("Mapping[object, object]", raw).items():
        field = str(key)
        if field not in _FIELDS:
            continue
        if not isinstance(value, (list, tuple)):
            raise ConfigError(f"身份源行配置 attribute_map.{field} 必须是字符串数组")
        names = tuple(
            str(item).strip() for item in cast("list[object] | tuple[object, ...]", value) if str(item).strip()
        )
        normalized[field] = names
    return normalized


def _merge_attribute_map(overrides: Mapping[str, Sequence[str]] | None) -> dict[str, tuple[str, ...]]:
    """合并默认映射与覆盖（按字段覆盖）。

    Args:
        overrides: 行配置 / 单例配置覆盖。

    Returns:
        dict[str, tuple[str, ...]]: 合并后的字段 → 候选属性名。
    """
    merged = {field: tuple(names) for field, names in _DEFAULT_ATTRIBUTE_MAP.items()}
    if overrides:
        for field, names in overrides.items():
            if field not in _FIELDS:
                continue
            merged[field] = tuple(name for name in names if name)
    return merged


def _parse_response(content: bytes) -> ET.Element:
    """安全解析 CAS 响应 XML（拒绝 DOCTYPE / ENTITY、限制体积）。

    Args:
        content: 原始响应体。

    Returns:
        ET.Element: 根节点。

    Raises:
        ServiceUnavailableError: 超限 / 含 DOCTYPE 或 ENTITY / 非合法 XML。
    """
    if len(content) > _MAX_RESPONSE_BYTES:
        raise ServiceUnavailableError("CAS 响应体超限")
    upper = content.upper()
    if b"<!DOCTYPE" in upper or b"<!ENTITY" in upper:
        raise ServiceUnavailableError("CAS 响应含禁止的 DTD / 实体声明")
    try:
        return ET.fromstring(content)
    except ET.ParseError as exc:
        raise ServiceUnavailableError("CAS 响应非合法 XML") from exc


def _find_local(parent: ET.Element, name: str) -> ET.Element | None:
    """按本地名查找直接子节点（忽略命名空间）。

    Args:
        parent: 父节点。
        name: 本地名。

    Returns:
        ET.Element | None: 命中节点；无则 None。
    """
    for child in parent:
        if _local(child.tag) == name:
            return child
    return None


def _child_text(parent: ET.Element, name: str) -> str:
    """取直接子节点文本（忽略命名空间；去空白）。

    Args:
        parent: 父节点。
        name: 本地名。

    Returns:
        str: 文本；缺失返回空串。
    """
    child = _find_local(parent, name)
    if child is None or child.text is None:
        return ""
    return child.text.strip()


def _parse_attributes(success: ET.Element) -> dict[str, str]:
    """解析 `authenticationSuccess` 下的 attributes（兼容元素名与 `cas:attribute` 两种形态）。

    Args:
        success: `authenticationSuccess` 节点。

    Returns:
        dict[str, str]: 属性名 → 值（多值拼串取首个 token）。
    """
    container = _find_local(success, "attributes")
    if container is None:
        return {}
    attributes: dict[str, str] = {}
    for child in container:
        local = _local(child.tag)
        if local == "attribute":
            name = child.get("name") or ""
            value = child.get("value") or (child.text or "")
        else:
            name = local
            value = child.text or ""
        name = name.strip()
        if not name:
            continue
        attributes.setdefault(name, _first_token(value))
    return attributes


def _first_token(value: str) -> str:
    """取属性值首个 token（CAS 多值常见空格分隔）。

    Args:
        value: 原始属性值。

    Returns:
        str: 首个 token（去空白）。
    """
    text = value.strip()
    if not text:
        return ""
    return text.split()[0]


def _local(tag: object) -> str:
    """取标签本地名（去命名空间前缀）。

    Args:
        tag: 节点标签。

    Returns:
        str: 本地名。
    """
    return str(tag).rsplit("}", 1)[-1]
