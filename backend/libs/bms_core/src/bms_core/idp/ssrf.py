"""idp 能力域：外部 IdP 出站 URL 校验（SSRF 防护）。

- `validate_outbound_url`：服务端出站地址（OIDC `issuer` / CAS `cas_server_url` / 企微与钉钉
  `api_base_url`）协议白名单（http/https）+ 主机静态校验（禁 `localhost` / 字面内网 / 回环 /
  链路本地 / 保留地址）；`allow_private_hosts=True` 时跳过主机校验（企业内网 IdP 合法场景）。
- `validate_browser_url`：浏览器跳转地址（`redirect_uri` / `login_url` / `oauth_url`）仅校验
  http/https 协议与主机存在（非服务端出站，不做内网校验）。

口径：**不做 DNS 解析后私网校验**（避免 TOCTOU 与部署复杂度；「域名解析到内网」为已知残留）。
"""

from __future__ import annotations

import ipaddress
from urllib.parse import urlsplit

from bms_core.core.exceptions import IdpConfigInvalidError

__all__ = [
    "validate_browser_url",
    "validate_outbound_url",
]

_ALLOWED_SCHEMES: frozenset[str] = frozenset({"http", "https"})
"""允许的 URL 协议（出站与浏览器跳转）。"""


def validate_outbound_url(url: str, *, allow_private_hosts: bool) -> str:
    """校验服务端出站 URL（协议 + 主机静态校验）。

    Args:
        url: 出站地址（如 `https://idp.example.com/realms/bms`）。
        allow_private_hosts: 是否允许私网 / 回环主机（企业内网 IdP 场景）。

    Returns:
        str: 去空白后的地址。

    Raises:
        IdpConfigInvalidError: 地址为空 / 协议非 http(s) / 缺主机 / 命中禁止主机（`20064`）。
    """
    text = _normalize_url(url)
    parts = urlsplit(text)
    if parts.scheme.lower() not in _ALLOWED_SCHEMES:
        raise IdpConfigInvalidError("出站地址协议不受支持（仅 http / https）")
    host = (parts.hostname or "").lower()
    if not host:
        raise IdpConfigInvalidError("出站地址缺主机名")
    if allow_private_hosts:
        return text
    if host == "localhost" or host.endswith(".localhost"):
        raise IdpConfigInvalidError("出站地址禁止本机主机")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return text
    if not address.is_global:
        raise IdpConfigInvalidError("出站地址禁止内网 / 保留地址")
    return text


def validate_browser_url(url: str) -> str:
    """校验浏览器跳转地址（仅 http/https 协议 + 主机存在）。

    Args:
        url: 跳转地址（`redirect_uri` / `login_url` / `oauth_url`）。

    Returns:
        str: 去空白后的地址。

    Raises:
        IdpConfigInvalidError: 地址为空 / 协议非 http(s) / 缺主机（`20064`）。
    """
    text = _normalize_url(url)
    parts = urlsplit(text)
    if parts.scheme.lower() not in _ALLOWED_SCHEMES:
        raise IdpConfigInvalidError("跳转地址协议不受支持（仅 http / https）")
    if not (parts.hostname or ""):
        raise IdpConfigInvalidError("跳转地址缺主机名")
    return text


def _normalize_url(url: object) -> str:
    """归一化 URL 输入（须为非空字符串）。

    Args:
        url: 原始值。

    Returns:
        str: 去空白后的地址。

    Raises:
        IdpConfigInvalidError: 值为空或非字符串（`20064`）。
    """
    if not isinstance(url, str) or not url.strip():
        raise IdpConfigInvalidError("地址不能为空")
    return url.strip()
