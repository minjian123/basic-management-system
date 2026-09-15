"""core 层应用插件装配：能力装配清单、平台实现登记与 lifespan 装配。

- `PluginWiring` / `PLUGIN_WIRINGS`：能力清单（plugin_key → 端口类 / 配置分区 / `app.state` 属性）。
- `register_platform_plugins`：平台内建实现登记（显式工厂，延迟导入 / 依赖注入落点；按注册表身份幂等）。
- `assemble_plugins`：读取各能力 provider → 解析实例化缓存（存在性 / 契约版本校验）→ `setup()` →
  登记 `ResourceManager` → 落 `app.state` → 启动日志（不含 options）；失败 `PluginError` 拒启。
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from importlib import import_module
from typing import cast

from fastapi import FastAPI

from app.archive.base import BaseArchivePolicy, BaseArchiveQueryRouter
from app.audit.hashchain import BaseHashChain
from app.captcha.base import BaseCaptcha
from app.circuit.base import BaseCircuitBreaker
from app.core.base import BaseObject
from app.core.capability import BaseAsyncResource
from app.core.config import PluginSelection, Settings
from app.core.exceptions import PluginError
from app.core.logging import get_logger
from app.core.plugin import (
    NULL_PLUGIN_NAME,
    BasePluggable,
    PluginRegistry,
    default_plugin_registry,
    register_plugin,
    resolve_plugin,
)
from app.core.resources import ResourceManager
from app.dashboard.base import BaseDashboardCardRegistry
from app.fallback.base import BaseFallbackPolicy
from app.fieldtype.base import BaseFieldTypeRegistry
from app.i18n.base import BaseTranslator
from app.idempotency.base import IdempotencyStore
from app.idp.base import BaseIdentityProvider
from app.llm.base import BaseLlmProvider
from app.lock.base import BaseDistributedLock
from app.masking.base import BaseMasker
from app.masking.null import NullMasker
from app.metrics.base import BaseMetrics
from app.notify.base import BaseNotifier
from app.oauth.base import BaseOAuthServer, BaseScopeChecker
from app.outbound.http import BaseHttpClient
from app.outbound.webhook import BaseWebhookSender
from app.password.base import BasePasswordPolicy
from app.permission.base import BasePermissionChecker
from app.query.base import BaseQueryProviderRegistry
from app.ratelimit.base import BaseRateLimiter
from app.replay.base import BaseReplayGuard
from app.scope.base import DataScope
from app.search.base import BaseSearchIndex
from app.session.base import BaseSessionStore
from app.sharding.base import ShardingRouter
from app.storage.base import BaseObjectStorage
from app.tracing.base import BaseTracer
from app.transfer.exporter import BaseExporter
from app.transfer.importer import BaseImporter
from app.workflow.base import BaseWorkflowEngine
from app.ws.base import BaseRealtimePublisher

__all__ = [
    "PLUGIN_WIRINGS",
    "PluginWiring",
    "assemble_plugins",
    "register_platform_plugins",
]

_LOGGER = get_logger("bms")

_PREPARED_REGISTRIES: list[PluginRegistry] = []
"""已登记平台实现的注册表引用（持引用防 `id` 复用；同一注册表只登记一次）。"""

_NULL_MODULES: tuple[str, ...] = (
    "app.archive.null",
    "app.audit.null",
    "app.captcha.null",
    "app.circuit.null",
    "app.dashboard.null",
    "app.db.null",
    "app.fallback.null",
    "app.fieldtype.null",
    "app.health.null",
    "app.i18n.null",
    "app.idempotency.null",
    "app.idp.null",
    "app.llm.null",
    "app.lock.null",
    "app.masking.null",
    "app.metrics.null",
    "app.notify.null",
    "app.oauth.null",
    "app.outbound.null",
    "app.password.null",
    "app.permission.null",
    "app.query.null",
    "app.ratelimit.null",
    "app.replay.null",
    "app.scope.null",
    "app.search.null",
    "app.session.null",
    "app.sharding.null",
    "app.storage.null",
    "app.tracing.null",
    "app.transfer.null",
    "app.workflow.null",
    "app.ws.null",
)
"""平台缺省实现模块（同域 `null.py`）：导入即经继承自动登记（轻量、无重依赖）。"""


@dataclass(frozen=True)
class PluginWiring(BaseObject):
    """单个能力的装配接线。"""

    plugin_key: str
    """能力域键（注册表键）。"""

    port: type[BasePluggable]
    """能力端口类（契约版本基准）。"""

    settings_section: str
    """配置分区名（`Settings` 字段 / `config.toml` 分区）。"""

    state_attr: str | None
    """`app.state` 属性名；`None` 表示仅预热（无应用状态落点）。"""


PLUGIN_WIRINGS: tuple[PluginWiring, ...] = (
    PluginWiring("permission", BasePermissionChecker, "permission", "permission_checker"),
    PluginWiring("masking", BaseMasker, "masking", "masker"),
    PluginWiring("distributed_lock", BaseDistributedLock, "distributed_lock", "distributed_lock"),
    PluginWiring("captcha", BaseCaptcha, "captcha", "captcha"),
    PluginWiring("password_policy", BasePasswordPolicy, "password_policy", "password_policy"),
    PluginWiring("fallback", BaseFallbackPolicy, "fallback", "fallback_policy"),
    PluginWiring("circuit_breaker", BaseCircuitBreaker, "circuit_breaker", "circuit_breaker"),
    PluginWiring("rate_limiter", BaseRateLimiter, "rate_limiter", "rate_limiter"),
    PluginWiring("idempotency", IdempotencyStore, "idempotency", "idempotency_store"),
    PluginWiring("replay_guard", BaseReplayGuard, "replay_guard", "replay_guard"),
    PluginWiring("metrics", BaseMetrics, "metrics", "metrics"),
    PluginWiring("tracer", BaseTracer, "tracer", "tracer"),
    PluginWiring("oauth_server", BaseOAuthServer, "oauth_server", "oauth_server"),
    PluginWiring("scope_checker", BaseScopeChecker, "scope_checker", "scope_checker"),
    PluginWiring("object_storage", BaseObjectStorage, "storage", "object_storage"),
    PluginWiring("llm_provider", BaseLlmProvider, "llm_provider", "llm_provider"),
    PluginWiring("search_index", BaseSearchIndex, "search_index", "search_index"),
    PluginWiring("notifier", BaseNotifier, "notifier", "notifier"),
    PluginWiring("realtime_publisher", BaseRealtimePublisher, "realtime_publisher", "realtime_publisher"),
    PluginWiring("http_client", BaseHttpClient, "http_client", "http_client"),
    PluginWiring("webhook_sender", BaseWebhookSender, "webhook_sender", "webhook_sender"),
    PluginWiring("workflow_engine", BaseWorkflowEngine, "workflow_engine", "workflow_engine"),
    PluginWiring("identity_provider", BaseIdentityProvider, "identity_provider", "identity_provider"),
    PluginWiring("session_store", BaseSessionStore, "session_store", "session_store"),
    PluginWiring(
        "query_provider_registry", BaseQueryProviderRegistry, "query_provider_registry", "query_provider_registry"
    ),
    PluginWiring("importer", BaseImporter, "importer", "importer"),
    PluginWiring("exporter", BaseExporter, "exporter", "exporter"),
    PluginWiring("hash_chain", BaseHashChain, "hash_chain", "hash_chain"),
    PluginWiring("archive_policy", BaseArchivePolicy, "archive_policy", "archive_policy"),
    PluginWiring("archive_query_router", BaseArchiveQueryRouter, "archive_query_router", "archive_query_router"),
    PluginWiring("field_type_registry", BaseFieldTypeRegistry, "field_type_registry", "field_type_registry"),
    PluginWiring("translator", BaseTranslator, "translator", "translator"),
    PluginWiring(
        "dashboard_card_registry", BaseDashboardCardRegistry, "dashboard_card_registry", "dashboard_card_registry"
    ),
    PluginWiring("data_scope", DataScope, "data_scope", None),
    PluginWiring("sharding", ShardingRouter, "sharding", None),
)


def register_platform_plugins(settings: Settings) -> None:
    """登记平台内建实现（显式工厂：延迟导入 / 依赖注入）；同一注册表仅登记一次。

    Args:
        settings: 应用配置（工厂登记可读取能力选择）。
    """
    registry = default_plugin_registry()
    if any(item is registry for item in _PREPARED_REGISTRIES):
        return
    for module in _NULL_MODULES:
        import_module(module)
    register_plugin("masking", NULL_PLUGIN_NAME, _null_masker_factory(settings))
    _PREPARED_REGISTRIES.append(registry)


def _null_masker_factory(settings: Settings) -> Callable[[], BaseMasker]:
    """构造缺省掩码器工厂（注入权限检查器；`NullMasker` 构造需参数，不自动登记）。

    Args:
        settings: 应用配置。

    Returns:
        Callable[[], BaseMasker]: 零参工厂。
    """

    def build() -> BaseMasker:
        """构造缺省掩码器（解析权限检查器实例）。

        Returns:
            BaseMasker: 掩码器实例。
        """
        checker = cast(
            "BasePermissionChecker",
            resolve_plugin(
                "permission",
                settings.permission.provider,
                expected_version=BasePermissionChecker.contract_version,
            ),
        )
        return NullMasker(checker=checker)

    return build


async def assemble_plugins(app: FastAPI, settings: Settings, resources: ResourceManager) -> dict[str, str]:
    """按清单装配各能力（lifespan 调用）：解析实例化缓存 → `setup()` → 资源登记 → `app.state` → 日志。

    Args:
        app: 应用实例（装配结果落 `app.state`）。
        settings: 应用配置（各能力 provider 选择）。
        resources: 异步资源登记表（`aclose` 逆序统一回收）。

    Returns:
        dict[str, str]: 各能力当前 provider（`plugin_key → 实现名`，供启动日志 / 测试核对）。

    Raises:
        PluginError: 存在性 / 契约版本校验失败，或实例化 / `setup()` 失败（拒启）。
    """
    providers: dict[str, str] = {}
    for wiring in PLUGIN_WIRINGS:
        selection = getattr(settings, wiring.settings_section, None)
        provider = selection.provider if isinstance(selection, PluginSelection) else ""
        instance = _resolve_or_reject(wiring, provider)
        await _setup_or_reject(wiring, provider, instance)
        if isinstance(instance, BaseAsyncResource):
            resources.register(instance)
        if wiring.state_attr:
            setattr(app.state, wiring.state_attr, instance)
        providers[wiring.plugin_key] = provider or NULL_PLUGIN_NAME
    _LOGGER.info("插件装配完成", providers=providers)
    return providers


def _resolve_or_reject(wiring: PluginWiring, provider: str) -> object:
    """解析实现实例（未注册 / 版本不兼容 / 工厂异常统一拒启）。

    Args:
        wiring: 装配接线。
        provider: 配置选定的实现名（空串 → `null`）。

    Returns:
        object: 实现实例。

    Raises:
        PluginError: 解析失败。
    """
    name = provider or NULL_PLUGIN_NAME
    try:
        return resolve_plugin(wiring.plugin_key, provider, expected_version=wiring.port.contract_version)
    except PluginError:
        raise
    except Exception as exc:  # 工厂导入 / 实例化失败（含实现依赖缺失）
        _LOGGER.critical("插件实例化失败", plugin_key=wiring.plugin_key, provider=name, error=repr(exc))
        raise PluginError(f"插件实例化失败：{wiring.plugin_key} → {name}（{exc!r}）") from exc


async def _setup_or_reject(wiring: PluginWiring, provider: str, instance: object) -> None:
    """调用实现 `setup()`（存在时；失败拒启）。

    Args:
        wiring: 装配接线。
        provider: 配置选定的实现名（空串 → `null`）。
        instance: 实现实例。

    Raises:
        PluginError: `setup()` 抛错。
    """
    setup = getattr(instance, "setup", None)
    if not callable(setup):
        return
    try:
        await cast("Awaitable[None]", setup())
    except Exception as exc:
        name = provider or NULL_PLUGIN_NAME
        _LOGGER.critical("插件 setup 失败", plugin_key=wiring.plugin_key, provider=name, error=repr(exc))
        raise PluginError(f"插件 setup 失败：{wiring.plugin_key} → {name}（{exc!r}）") from exc
