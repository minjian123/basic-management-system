"""idp 能力域：外部 IdP 行配置的声明式 schema（写入校验 / 凭据脱敏）。

- `validate_provider_config`：按协议声明式校验 `sys_identity_provider.config`（必填 / 类型 / 枚举 /
  **未知键拒绝** / 密钥引用 / 出站 URL SSRF），返回归一化后的新字典。
- `mask_provider_config`：响应层**确定性脱敏**——敏感键（密钥引用）值替换为「引用前缀 + `***`」，
  其余键原样返回；`has_secret` 供前端展示「凭据已配置」而不解析掩码值。

口径：密钥类**只接受 `env:变量名` 引用**（`secret:` 为域 04_03 预留、写入即拒）；未知键拒绝避免脏配置。
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import cast

from bms_core.core.base import BaseObject
from bms_core.core.exceptions import IdpConfigInvalidError
from bms_core.idp.ssrf import validate_browser_url, validate_outbound_url

__all__ = [
    "has_secret",
    "mask_provider_config",
    "validate_provider_config",
]

_SECRET_REF_RE = re.compile(r"env:[A-Za-z_][A-Za-z0-9_]*")
"""密钥引用允许形态：`env:变量名`（`secret:` 预留，写入即拒）。"""


@dataclass(frozen=True)
class _KeyRule(BaseObject):
    """配置键规格：值类型 + 可选枚举取值。"""

    kind: str
    values: tuple[str, ...] = ()


_SHARED_KEYS: dict[str, _KeyRule] = {
    "jit_enabled": _KeyRule("bool"),
    "allowed_email_domains": _KeyRule("str_list"),
}
"""四协议通用键（02_02 JIT 消费）。"""

_PROTOCOL_SPECS: dict[str, dict[str, _KeyRule]] = {
    "oidc": {
        "issuer": _KeyRule("outbound_url"),
        "client_id": _KeyRule("str"),
        "client_secret_ref": _KeyRule("secret_ref"),
        "scopes": _KeyRule("str_list"),
        "redirect_uri": _KeyRule("client_url"),
        "discovery_cache_ttl": _KeyRule("number"),
        "jwks_cache_ttl": _KeyRule("number"),
        **_SHARED_KEYS,
    },
    "cas": {
        "cas_server_url": _KeyRule("outbound_url"),
        "cas_login_path": _KeyRule("str"),
        "cas_service_validate_path": _KeyRule("str"),
        "attribute_map": _KeyRule("str_map"),
        "redirect_uri": _KeyRule("client_url"),
        **_SHARED_KEYS,
    },
    "wecom": {
        "corp_id": _KeyRule("str"),
        "agent_id": _KeyRule("str"),
        "secret_ref": _KeyRule("secret_ref"),
        "mode": _KeyRule("enum", ("qr", "oauth")),
        "login_url": _KeyRule("client_url"),
        "oauth_url": _KeyRule("client_url"),
        "api_base_url": _KeyRule("outbound_url"),
        "scope": _KeyRule("str"),
        "login_type": _KeyRule("str"),
        "redirect_uri": _KeyRule("client_url"),
        **_SHARED_KEYS,
    },
    "dingtalk": {
        "client_id": _KeyRule("str"),
        "client_secret_ref": _KeyRule("secret_ref"),
        "login_url": _KeyRule("client_url"),
        "api_base_url": _KeyRule("outbound_url"),
        "scope": _KeyRule("str"),
        "prompt": _KeyRule("str"),
        "redirect_uri": _KeyRule("client_url"),
        **_SHARED_KEYS,
    },
}
"""协议 → 键规格（键白名单；未知键拒绝）。"""

_REQUIRED_KEYS: dict[str, tuple[str, ...]] = {
    "oidc": ("issuer", "client_id", "client_secret_ref"),
    "cas": ("cas_server_url",),
    "wecom": ("corp_id", "agent_id", "secret_ref"),
    "dingtalk": ("client_id", "client_secret_ref"),
}
"""协议 → 必填键。"""


def validate_provider_config(
    protocol: str,
    config: Mapping[str, object],
    *,
    allow_private_hosts: bool,
) -> dict[str, object]:
    """校验并归一化 IdP 行配置（未知键拒绝）。

    Args:
        protocol: 协议类型（取 `IDP_PROTOCOLS`）。
        config: 行配置对象。
        allow_private_hosts: 出站 URL 是否允许私网主机。

    Returns:
        dict[str, object]: 归一化后的配置对象（新字典）。

    Raises:
        IdpConfigInvalidError: 协议不支持 / 配置非对象 / 未知键 / 必填缺失 / 值非法（`20064`）。
    """
    spec = _PROTOCOL_SPECS.get(protocol)
    if spec is None:
        raise IdpConfigInvalidError(f"不支持的 IdP 协议类型：{protocol}")
    raw = cast("Mapping[object, object]", config)
    for key in raw:
        name = str(key)
        if name not in spec:
            raise IdpConfigInvalidError(f"IdP 配置含未知键：{name}")
    normalized: dict[str, object] = {}
    for key, value in raw.items():
        name = str(key)
        normalized[name] = _normalize_value(name, spec[name], value, allow_private_hosts=allow_private_hosts)
    for key in _REQUIRED_KEYS[protocol]:
        if key not in normalized:
            raise IdpConfigInvalidError(f"IdP 配置缺必填字段：{key}")
    return normalized


def mask_provider_config(protocol: str, config: Mapping[str, object]) -> dict[str, object]:
    """响应层脱敏：敏感键值替换为「引用前缀 + `***`」，其余键原样返回。

    Args:
        protocol: 协议类型。
        config: 行配置对象（可能含历史未知键）。

    Returns:
        dict[str, object]: 脱敏后的新字典。
    """
    spec = _PROTOCOL_SPECS.get(protocol)
    if spec is None:
        return {}
    masked: dict[str, object] = {}
    for key, value in config.items():
        name = str(key)
        rule = spec.get(name)
        if (rule is not None and rule.kind == "secret_ref") or (rule is None and _looks_secret(name)):
            masked[name] = _mask_secret_ref(value)
        else:
            masked[name] = value
    return masked


def has_secret(protocol: str, config: Mapping[str, object]) -> bool:
    """配置是否含已填写的密钥引用（前端展示「凭据已配置」）。

    Args:
        protocol: 协议类型。
        config: 行配置对象。

    Returns:
        bool: 含任一非空密钥引用为 True。
    """
    spec = _PROTOCOL_SPECS.get(protocol, {})
    for key, value in config.items():
        rule = spec.get(str(key))
        if rule is not None and rule.kind == "secret_ref" and isinstance(value, str) and value.strip():
            return True
    return False


def _normalize_value(name: str, rule: _KeyRule, value: object, *, allow_private_hosts: bool) -> object:
    """按键规格归一化单个配置值。

    Args:
        name: 配置键。
        rule: 键规格。
        value: 原始值。
        allow_private_hosts: 出站 URL 是否允许私网主机。

    Returns:
        object: 归一化后的值。

    Raises:
        IdpConfigInvalidError: 值非法（`20064`）。
    """
    if rule.kind == "str":
        return _require_str(name, value)
    if rule.kind == "bool":
        if not isinstance(value, bool):
            raise IdpConfigInvalidError(f"配置项 {name} 必须是布尔值")
        return value
    if rule.kind == "number":
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise IdpConfigInvalidError(f"配置项 {name} 必须是数值")
        return value
    if rule.kind == "enum":
        text = _require_str(name, value)
        if text not in rule.values:
            raise IdpConfigInvalidError(f"配置项 {name} 取值非法（应为 {' / '.join(rule.values)}）")
        return text
    if rule.kind == "str_list":
        return _require_str_list(name, value)
    if rule.kind == "str_map":
        return _require_str_map(name, value)
    if rule.kind == "secret_ref":
        return _require_secret_ref(name, value)
    if rule.kind == "outbound_url":
        return validate_outbound_url(_require_str(name, value), allow_private_hosts=allow_private_hosts)
    if rule.kind == "client_url":
        return validate_browser_url(_require_str(name, value))
    raise IdpConfigInvalidError(f"配置项 {name} 规格未实现：{rule.kind}")  # pragma: no cover - 规格穷尽，防御性兜底


def _require_str(name: str, value: object) -> str:
    """取必填字符串（去空白）。

    Args:
        name: 配置键。
        value: 原始值。

    Returns:
        str: 去空白字符串。

    Raises:
        IdpConfigInvalidError: 非字符串或空（`20064`）。
    """
    if not isinstance(value, str) or not value.strip():
        raise IdpConfigInvalidError(f"配置项 {name} 必须是非空字符串")
    return value.strip()


def _require_str_list(name: str, value: object) -> list[str]:
    """取字符串数组（去重去空白）。

    Args:
        name: 配置键。
        value: 原始值。

    Returns:
        list[str]: 字符串列表。

    Raises:
        IdpConfigInvalidError: 非数组或含非字符串 / 空元素（`20064`）。
    """
    if not isinstance(value, (list, tuple)):
        raise IdpConfigInvalidError(f"配置项 {name} 必须是字符串数组")
    items: list[str] = []
    for item in cast("list[object] | tuple[object, ...]", value):
        if not isinstance(item, str) or not item.strip():
            raise IdpConfigInvalidError(f"配置项 {name} 含非法元素（须为非空字符串）")
        text = item.strip()
        if text not in items:
            items.append(text)
    return items


def _require_str_map(name: str, value: object) -> dict[str, list[str]]:
    """取「字符串 → 字符串数组」对象。

    Args:
        name: 配置键。
        value: 原始值。

    Returns:
        dict[str, list[str]]: 归一化映射。

    Raises:
        IdpConfigInvalidError: 非对象或值非法（`20064`）。
    """
    if not isinstance(value, Mapping):
        raise IdpConfigInvalidError(f"配置项 {name} 必须是对象")
    result: dict[str, list[str]] = {}
    for key, item in cast("Mapping[object, object]", value).items():
        result[str(key)] = _require_str_list(f"{name}.{key}", item)
    return result


def _require_secret_ref(name: str, value: object) -> str:
    """取密钥引用（仅接受 `env:变量名`；`secret:` 预留、明文拒绝）。

    Args:
        name: 配置键。
        value: 原始值。

    Returns:
        str: 密钥引用（`env:变量名`）。

    Raises:
        IdpConfigInvalidError: 引用非法 / `secret:` 未实现 / 疑似明文（`20064`）。
    """
    if not isinstance(value, str) or not value.strip():
        raise IdpConfigInvalidError(f"配置项 {name} 必须是非空字符串")
    text = value.strip()
    if not _SECRET_REF_RE.fullmatch(text):
        if text.startswith("secret:"):
            raise IdpConfigInvalidError(f"配置项 {name} 的 secret: 引用未实现（请使用 env:变量名）")
        raise IdpConfigInvalidError(f"配置项 {name} 只接受 env:变量名 引用（禁止明文密钥）")
    return text


def _looks_secret(name: str) -> bool:
    """按字段名判断疑似密钥键（历史脏配置兜底，防脱敏遗漏）。

    Args:
        name: 配置键名。

    Returns:
        bool: 疑似密钥键为 True。
    """
    lowered = name.lower()
    return lowered.endswith("_ref") or "secret" in lowered


def _mask_secret_ref(value: object) -> str:
    """掩码密钥引用：保留前缀（`env` / `secret`），其余以 `***` 替代。

    Args:
        value: 原始引用值。

    Returns:
        str: 掩码后的引用（非法形态返回 `***`）。
    """
    if not isinstance(value, str) or ":" not in value:
        return "***"
    prefix = value.split(":", 1)[0].strip().lower()
    return f"{prefix}:***" if prefix in ("env", "secret") else "***"
