"""身份源能力域：行配置实例化（`sys_identity_provider` → 租户内 IdP 实例）。

- `IdentityProviderSpec`：行配置视图（id / idp_key / type / config / updated_at），与 ORM 解耦。
- `resolve_secret_ref`：密钥引用解析——`env:变量名` 取环境变量（缺失抛 `ConfigError`）；`secret:标识`
  预留（后续安全强化；当前抛 `ConfigError`）；未知前缀抛 `ConfigError`（零明文入代码 / 入仓）。
- `IdentityProviderRegistry`：按 `type` 分派构造（`oidc` / `cas`；企微 / 钉钉随对应任务注册），按
  `(id, updated_at, type)` 进程内缓存（行配置变更自动失效，同时保留实例内 Discovery / JWKS 缓存）。

口径：registry 为服务内构件（不做 IO、不进插件注册表）；`transport` 供测试注入（MockTransport）。
"""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import cast

import httpx

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.exceptions import ConfigError, DingtalkConfigError, WecomConfigError
from bms_core.core.objects import BaseFrameworkObject, BaseValueObject
from bms_core.idp.base import BaseIdentityProvider
from bms_core.idp.cas import CasIdentityProvider, normalize_attribute_map
from bms_core.idp.dingtalk import DingtalkIdentityProvider
from bms_core.idp.oidc import OidcIdentityProvider
from bms_core.idp.wecom import WecomIdentityProvider

__all__ = [
    "IdentityProviderRegistry",
    "IdentityProviderSpec",
    "resolve_secret_ref",
]


@dataclass(frozen=True)
class IdentityProviderSpec(BaseValueObject):
    """IdP 行配置视图（authorize / callback 按行构造实例）。"""

    id: int = 0
    """行主键（实例缓存键之一）。"""

    idp_key: str = ""
    """租户内 IdP 稳定标识（路由与映射键来源）。"""

    type: str = ""
    """协议类型（`oidc` / `cas` / `wecom` / `dingtalk`）。"""

    config: ConcurrentStableDict[str, object] = field(default_factory=ConcurrentStableDict[str, object])
    """行配置 JSON（密钥仅存引用 `client_secret_ref`）。"""

    updated_at: str = ""
    """行更新时间（ISO 字符串；变更即失效实例缓存）。"""


def resolve_secret_ref(ref: str) -> str:
    """解析密钥引用为明文（仅运行期内存持有，零明文入代码 / 入仓）。

    Args:
        ref: 密钥引用（`env:变量名`；`secret:标识` 预留）。

    Returns:
        str: 密钥明文。

    Raises:
        ConfigError: 引用为空 / 环境变量缺失 / `secret:` 未实现 / 未知前缀（40001）。
    """
    if not ref:
        raise ConfigError("身份源密钥引用为空")
    if ref.startswith("env:"):
        name = ref[4:]
        value = os.environ.get(name, "")
        if not value:
            raise ConfigError(f"身份源密钥环境变量缺失：{name}")
        return value
    if ref.startswith("secret:"):
        raise ConfigError("身份源密钥引用 secret: 未实现（后续安全强化）")
    raise ConfigError(f"未知身份源密钥引用前缀：{ref.split(':', 1)[0]}")


class IdentityProviderRegistry(BaseFrameworkObject):
    """行配置 → IdP 实例（按 type 分派；`(id, updated_at, type)` 进程内缓存）。"""

    def __init__(
        self,
        secret_resolver: Callable[[str], str] = resolve_secret_ref,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        """初始化。

        Args:
            secret_resolver: 密钥引用解析器（缺省 `resolve_secret_ref`；测试可注入）。
            transport: 出站传输（测试注入 MockTransport；缺省走真实网络）。
        """
        self._secret_resolver = secret_resolver
        self._transport = transport
        self._cache: ConcurrentStableDict[tuple[int, str, str], BaseIdentityProvider] = ConcurrentStableDict()

    def build(self, spec: IdentityProviderSpec) -> BaseIdentityProvider:
        """按 `type` 构造 IdP 实例（不缓存）。

        Args:
            spec: 行配置视图。

        Returns:
            BaseIdentityProvider: IdP 实例。

        Raises:
            ConfigError: 协议类型未支持 / 必填配置缺失 / 密钥引用解析失败（40001）。
        """
        if spec.type == "oidc":
            return self._build_oidc(spec)
        if spec.type == "cas":
            return self._build_cas(spec)
        if spec.type == "wecom":
            return self._build_wecom(spec)
        if spec.type == "dingtalk":
            return self._build_dingtalk(spec)
        raise ConfigError(f"未支持的 IdP 协议类型：{spec.type}（{spec.idp_key}）")

    def get(self, spec: IdentityProviderSpec) -> BaseIdentityProvider:
        """取 IdP 实例（命中缓存直接返回；行配置更新自动失效）。

        Args:
            spec: 行配置视图。

        Returns:
            BaseIdentityProvider: IdP 实例。
        """
        cache_key = (spec.id, spec.updated_at, spec.type)
        cached = self._cache.get(cache_key)
        if cached is None:
            cached = self.build(spec)
            self._cache.set(cache_key, cached)
        return cached

    def clear(self) -> None:
        """清空实例缓存（测试 / 调试用）。"""
        for key in self._cache:
            self._cache.get_and_remove(key)

    def _build_oidc(self, spec: IdentityProviderSpec) -> OidcIdentityProvider:
        """构造 OIDC 实例（读取行配置，密钥引用经解析器转明文）。

        Args:
            spec: 行配置视图。

        Returns:
            OidcIdentityProvider: OIDC 客户端实例。

        Raises:
            ConfigError: 必填配置缺失 / 密钥引用解析失败（40001）。
        """
        config = spec.config
        issuer = _require_config_str(config, "issuer", spec)
        client_id = _require_config_str(config, "client_id", spec)
        redirect_uri = _require_config_str(config, "redirect_uri", spec)
        secret_ref = _optional_config_str(config, "client_secret_ref")
        if not secret_ref:
            raise ConfigError(f"身份源行缺密钥引用 client_secret_ref：{spec.idp_key}")
        scopes = _optional_scopes(config)
        discovery_ttl = _as_float(config.get("discovery_cache_ttl"), 3600.0)
        jwks_ttl = _as_float(config.get("jwks_cache_ttl"), 300.0)
        return OidcIdentityProvider(
            issuer=issuer,
            client_id=client_id,
            client_secret=self._secret_resolver(secret_ref),
            redirect_uri=redirect_uri,
            scopes=scopes or ConcurrentStableList(("openid", "profile", "email")),
            discovery_cache_ttl=discovery_ttl,
            jwks_cache_ttl=jwks_ttl,
            transport=self._transport,
        )

    def _build_cas(self, spec: IdentityProviderSpec) -> CasIdentityProvider:
        """构造 CAS 实例（读取行配置；CAS 不要求客户端密钥）。

        Args:
            spec: 行配置视图。

        Returns:
            CasIdentityProvider: CAS 客户端实例。

        Raises:
            ConfigError: 必填配置缺失（`cas_server_url` / `redirect_uri`）/ `attribute_map` 非法（40001）。
        """
        config = spec.config
        server_url = _require_config_str(config, "cas_server_url", spec)
        redirect_uri = _require_config_str(config, "redirect_uri", spec)
        login_path = _optional_config_str(config, "cas_login_path") or "/login"
        service_validate_path = _optional_config_str(config, "cas_service_validate_path") or "/p3/serviceValidate"
        attribute_map = normalize_attribute_map(config.get("attribute_map"))
        return CasIdentityProvider(
            server_url=server_url,
            redirect_uri=redirect_uri,
            login_path=login_path,
            service_validate_path=service_validate_path,
            attribute_map=attribute_map or None,
            transport=self._transport,
        )

    def _build_wecom(self, spec: IdentityProviderSpec) -> WecomIdentityProvider:
        """构造企业微信实例（读取行配置，密钥引用经解析器转明文）。

        Args:
            spec: 行配置视图。

        Returns:
            WecomIdentityProvider: 企业微信客户端实例。

        Raises:
            WecomConfigError: 必填配置缺失（`corp_id` / `agent_id` / `redirect_uri` / `secret_ref`）、
                密钥引用解析失败、`mode` 非法（20057）。
        """
        config = spec.config
        try:
            corp_id = _require_config_str(config, "corp_id", spec)
            agent_id = _require_config_str(config, "agent_id", spec)
            redirect_uri = _require_config_str(config, "redirect_uri", spec)
            secret = self._secret_resolver(_require_config_str(config, "secret_ref", spec))
        except ConfigError as exc:
            raise WecomConfigError(str(exc)) from exc
        mode = _optional_config_str(config, "mode") or "qr"
        if mode not in ("qr", "oauth"):
            raise WecomConfigError(f"企业微信行配置 mode 非法：{spec.idp_key}（应为 qr / oauth）")
        return WecomIdentityProvider(
            corp_id=corp_id,
            agent_id=agent_id,
            secret=secret,
            redirect_uri=redirect_uri,
            mode=mode,
            login_url=_optional_config_str(config, "login_url"),
            oauth_url=_optional_config_str(config, "oauth_url"),
            api_base_url=_optional_config_str(config, "api_base_url"),
            scope=_optional_config_str(config, "scope"),
            login_type=_optional_config_str(config, "login_type"),
            transport=self._transport,
        )

    def _build_dingtalk(self, spec: IdentityProviderSpec) -> DingtalkIdentityProvider:
        """构造钉钉实例（读取行配置，密钥引用经解析器转明文）。

        Args:
            spec: 行配置视图。

        Returns:
            DingtalkIdentityProvider: 钉钉客户端实例。

        Raises:
            DingtalkConfigError: 必填配置缺失（`client_id` / `redirect_uri` / `client_secret_ref`）、
                密钥引用解析失败（20060）。
        """
        config = spec.config
        try:
            client_id = _require_config_str(config, "client_id", spec)
            redirect_uri = _require_config_str(config, "redirect_uri", spec)
            client_secret = self._secret_resolver(_require_config_str(config, "client_secret_ref", spec))
        except ConfigError as exc:
            raise DingtalkConfigError(str(exc)) from exc
        return DingtalkIdentityProvider(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
            login_url=_optional_config_str(config, "login_url"),
            api_base_url=_optional_config_str(config, "api_base_url"),
            scope=_optional_config_str(config, "scope"),
            prompt=_optional_config_str(config, "prompt"),
            transport=self._transport,
        )


def _require_config_str(config: ConcurrentStableDict[str, object], key: str, spec: IdentityProviderSpec) -> str:
    """取行配置必填字符串。

    Args:
        config: 行配置 JSON。
        key: 配置键。
        spec: 行配置视图（错误提示用）。

    Returns:
        str: 配置值。

    Raises:
        ConfigError: 缺失 / 非字符串（40001）。
    """
    value = config.get(key)
    if not isinstance(value, str) or not value:
        raise ConfigError(f"身份源行配置缺字段 {key}：{spec.idp_key}")
    return value


def _optional_config_str(config: ConcurrentStableDict[str, object], key: str) -> str:
    """取行配置可选字符串（缺失 / 非字符串返回空串）。

    Args:
        config: 行配置 JSON。
        key: 配置键。

    Returns:
        str: 配置值或空串。
    """
    value = config.get(key)
    return value if isinstance(value, str) else ""


def _optional_scopes(config: ConcurrentStableDict[str, object]) -> ConcurrentStableList[str] | None:
    """解析可选 `scopes` 配置（数组；缺省 / 空数组返回 None）。

    Args:
        config: 行配置视图。

    Returns:
        ConcurrentStableList[str] | None: 作用域序列；缺省返回 None（由实现取默认）。
    """
    raw = config.get("scopes")
    if not isinstance(raw, (list, tuple)) or not raw:
        return None
    values = cast("list[object] | tuple[object, ...]", raw)
    return ConcurrentStableList(str(item) for item in values)


def _as_float(value: object, default: float) -> float:
    """归一化数值配置项。

    Args:
        value: 原始值。
        default: 缺省值。

    Returns:
        float: 数值（非法取缺省）。
    """
    return float(value) if isinstance(value, (int, float)) else default
