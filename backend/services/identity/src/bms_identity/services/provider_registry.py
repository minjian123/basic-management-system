"""认证与身份服务 services 层：ORM 行配置 → 基座注册表实例（桥接）。

- `spec_for`：`SysIdentityProvider` 行 → `IdentityProviderSpec`（`config` TEXT 解析为 JSON 对象，
  非法即 `ConfigError`；`updated_at` 规范化为 ISO 字符串供实例缓存失效）。
- `instance_for` / `instance_for_spec`：经基座 `IdentityProviderRegistry` 按 `(id, updated_at, type)` 取实例。
- `spec_for_config`：草稿配置 → 实例规格（连通性测试；不落库、不缓存）。
- `redirect_uri_for` / `spec_for`：`config.redirect_uri` 优先；缺省按 `[sso].callback_base_url`
  派生 `{base}/api/v1/auth/sso/{idp_key}/callback`（网关形态经行配置覆盖）。
- `transport` 供测试注入 `httpx.MockTransport`（走真实网络的部署不传）。
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import cast

import httpx

from bms_core.core.concurrent import ConcurrentStableDict
from bms_core.core.exceptions import ConfigError
from bms_core.core.objects import BaseFrameworkObject
from bms_core.idp.base import BaseIdentityProvider
from bms_core.idp.registry import IdentityProviderRegistry, IdentityProviderSpec
from bms_identity.models.identity_provider import SysIdentityProvider


class ProviderRegistry(BaseFrameworkObject):
    """租户内 IdP 行实例化桥接（authorize / callback 逐请求取实例）。"""

    def __init__(
        self,
        registry: IdentityProviderRegistry | None = None,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        callback_base_url: str = "",
    ) -> None:
        """初始化。

        Args:
            registry: 基座实例注册表（缺省新建；测试可注入自定义密钥解析）。
            transport: 出站传输（测试注入 MockTransport；缺省走真实网络）。
            callback_base_url: 回调地址基址（行配置缺 `redirect_uri` 时派生）。
        """
        self._registry = registry if registry is not None else IdentityProviderRegistry(transport=transport)
        self._callback_base_url = callback_base_url.rstrip("/")

    def redirect_uri_for(self, row: SysIdentityProvider) -> str:
        """取行生效回调地址（行配置优先，缺省按基址派生）。

        Args:
            row: IdP 行。

        Returns:
            str: 回调地址；无行配置且无基址时返回空串。

        Raises:
            ConfigError: `config` 非法 JSON / 非对象（40001）。
        """
        return _resolve_redirect_uri(_parse_config(row.config, row.idp_key), row.idp_key, self._callback_base_url)

    def spec_for(self, row: SysIdentityProvider) -> IdentityProviderSpec:
        """行 → 基座实例规格（配置 JSON 解析 + 更新时间规范化）。

        Args:
            row: IdP 行。

        Returns:
            IdentityProviderSpec: 实例化规格。

        Raises:
            ConfigError: `config` 非法 JSON / 非对象（40001）。
        """
        config = _parse_config(row.config, row.idp_key)
        redirect_uri = _resolve_redirect_uri(config, row.idp_key, self._callback_base_url)
        if redirect_uri and not config.get("redirect_uri"):
            config = ConcurrentStableDict({**config, "redirect_uri": redirect_uri})
        return IdentityProviderSpec(
            id=row.id,
            idp_key=row.idp_key,
            type=row.type,
            config=config,
            updated_at=_normalize_updated_at(row.updated_at),
        )

    def spec_for_config(
        self,
        *,
        idp_key: str,
        type: str,
        config: ConcurrentStableDict[str, object],
    ) -> IdentityProviderSpec:
        """草稿配置 → 实例规格（连通性测试用；不落库、不缓存）。

        与 `spec_for` 同口径补齐 `redirect_uri`（行配置优先，缺省按回调基址派生）。

        Args:
            idp_key: 租户内标识（派生回调路径用；草稿可传占位值）。
            type: 协议类型。
            config: 行配置对象。

        Returns:
            IdentityProviderSpec: 实例规格（`id=0` / `updated_at=""`）。
        """
        redirect_uri = _resolve_redirect_uri(config, idp_key, self._callback_base_url)
        merged = ConcurrentStableDict(config)
        if redirect_uri and not merged.get("redirect_uri"):
            merged.set("redirect_uri", redirect_uri)
        return IdentityProviderSpec(id=0, idp_key=idp_key, type=type, config=merged, updated_at="")

    def instance_for_spec(self, spec: IdentityProviderSpec) -> BaseIdentityProvider:
        """按实例规格取 IdP 实例（按规格缓存；行配置变更自动失效）。

        Args:
            spec: 实例规格。

        Returns:
            BaseIdentityProvider: IdP 实例。
        """
        return self._registry.get(spec)

    def instance_for(self, row: SysIdentityProvider) -> BaseIdentityProvider:
        """取 IdP 实例（按规格缓存；行配置变更自动失效）。

        Args:
            row: IdP 行。

        Returns:
            BaseIdentityProvider: IdP 实例。
        """
        return self.instance_for_spec(self.spec_for(row))

    def clear(self) -> None:
        """清空实例缓存（测试 / 调试用）。"""
        self._registry.clear()


def _parse_config(raw: str | None, idp_key: str) -> ConcurrentStableDict[str, object]:
    """解析 IdP 行配置 JSON（必须是对象）。

    Args:
        raw: `config` 列原文。
        idp_key: 租户内标识（错误提示用）。

    Returns:
        ConcurrentStableDict[str, object]: 配置对象。

    Raises:
        ConfigError: 非法 JSON / 非对象（40001）。
    """
    try:
        parsed = json.loads(raw or "{}")
    except ValueError as exc:
        raise ConfigError(f"身份源行配置非法 JSON：{idp_key}") from exc
    if not isinstance(parsed, dict):
        raise ConfigError(f"身份源行配置必须是 JSON 对象：{idp_key}")
    return ConcurrentStableDict(cast("dict[str, object]", parsed))


def _resolve_redirect_uri(config: ConcurrentStableDict[str, object], idp_key: str, callback_base_url: str) -> str:
    """行配置 `redirect_uri` 优先；缺省按回调基址派生。

    Args:
        config: 行配置对象。
        idp_key: 租户内标识（派生路径用）。
        callback_base_url: 回调地址基址（已去尾斜杠）。

    Returns:
        str: 回调地址；均缺省时返回空串。
    """
    given = config.get("redirect_uri")
    if isinstance(given, str) and given.strip():
        return given.strip()
    if callback_base_url:
        return f"{callback_base_url}/api/v1/auth/sso/{idp_key}/callback"
    return ""


def _normalize_updated_at(value: datetime | str | None) -> str:
    """规范化行更新时间为 ISO 字符串（缓存键组成）。

    Args:
        value: ORM 更新时间 / 字符串 / 空。

    Returns:
        str: ISO 字符串（空返回空串）。
    """
    if value is None:
        return ""
    return value.isoformat() if isinstance(value, datetime) else str(value)
