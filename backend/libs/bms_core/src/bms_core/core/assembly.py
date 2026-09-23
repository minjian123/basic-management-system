"""core 层应用插件装配：能力装配清单、平台实现登记与 lifespan 装配。

- `PluginWiring` / `PLUGIN_WIRINGS`：能力清单（plugin_key → 端口类 / 配置分区 / `app.state` 属性）。
- `register_platform_plugins`：平台内建实现登记（显式工厂，延迟导入 / 依赖注入落点；按注册表身份幂等）。
- `assemble_plugins`：读取各能力 provider → 解析实例化缓存（存在性 / 契约版本校验）→ `setup()` →
  登记 `ResourceManager` → 落 `app.state` → 启动日志（不含 options）；失败 `PluginError` 拒启。
"""

from collections.abc import Awaitable
from dataclasses import dataclass
from importlib import import_module
from pathlib import Path
from typing import cast

from fastapi import FastAPI

from bms_core.archive.base import BaseArchivePolicy, BaseArchiveQueryRouter
from bms_core.audit.base import AuditCapturer
from bms_core.audit.hashchain import BaseHashChain
from bms_core.boundary.base import BaseDataOwnershipGuard
from bms_core.boundary.directory import known_prefixes, known_services, known_tables
from bms_core.boundary.exceptions import load_exceptions, validate_exceptions
from bms_core.boundary.table import TableOwnershipGuard
from bms_core.cache.base import CacheRegion
from bms_core.cache.memory import MemoryCacheRegion
from bms_core.cache.redis import RedisCacheRegion
from bms_core.captcha.base import BaseCaptcha
from bms_core.chat.base import BaseChatActionGate, BaseChatSessionStore, BaseChatStream
from bms_core.circuit.base import BaseCircuitBreaker
from bms_core.codecheck.base import BaseCodeValidator
from bms_core.core.base import BaseObject
from bms_core.core.capability import BaseAsyncResource
from bms_core.core.config import PluginSelection, Settings
from bms_core.core.exceptions import PluginError
from bms_core.core.factory import BasePluginFactory
from bms_core.core.logging import get_logger
from bms_core.core.plugin import (
    NULL_PLUGIN_NAME,
    BasePluggable,
    PluginRegistry,
    default_plugin_registry,
    register_plugin,
    resolve_plugin,
)
from bms_core.core.resources import ResourceManager
from bms_core.dashboard.base import BaseDashboardCardRegistry
from bms_core.db.migration import BACKEND_ROOT
from bms_core.db.registry import EngineRegistry
from bms_core.db.session import SessionFactory
from bms_core.dict.base import BaseDictSource, BaseDictTranslator, DictCacheRegion
from bms_core.dict.cache import MemoryDictCacheRegion, RedisDictCacheRegion
from bms_core.dict.http import HttpDictSource, HttpDictTranslator
from bms_core.dict.providers import BuiltinDictQueryProvider
from bms_core.dict.sql import SqlDictSource, SqlDictTranslator
from bms_core.edge.base import BaseEdgeTrust
from bms_core.edge.headers import GATEWAY_IDENTITY_VALUE
from bms_core.edge.marker import MarkerEdgeTrust
from bms_core.edge.service_jwt import ServiceJwtEdgeTrustFactory
from bms_core.events.base import BaseEventConsumer, EventPublisher
from bms_core.events.platform_events import register_platform_event_contracts
from bms_core.fallback.base import BaseFallbackPolicy
from bms_core.fieldtype.base import BaseFieldTypeRegistry
from bms_core.fieldtype.local import LocalFieldTypeRegistry
from bms_core.globalsearch.base import BaseAuditSearch, BaseFileContentSearch, BaseGlobalSearch
from bms_core.health.base import BaseHealthCheckRegistry
from bms_core.health.checks import CatalogHealthCheck, DatabaseHealthCheck, RedisHealthCheck
from bms_core.health.registry import HealthCheckRegistry
from bms_core.i18n.base import BaseTranslator
from bms_core.icon.base import BaseIconRegistry
from bms_core.idempotency.base import IdempotencyStore
from bms_core.idempotency.redis import RedisIdempotencyStore
from bms_core.idp.base import BaseIdentityProvider
from bms_core.idp.oidc import OidcIdentityProviderFactory
from bms_core.listing.base import BaseQuerySchemeStore
from bms_core.listing.store import SqlQuerySchemeStore
from bms_core.llm.base import BaseLlmProvider
from bms_core.lock.base import BaseDistributedLock
from bms_core.masking.base import BaseMasker
from bms_core.masking.null import NullMasker
from bms_core.metrics.base import BaseMetrics
from bms_core.metrics.prometheus import PrometheusMetrics
from bms_core.notification.base import BaseNotificationCenter
from bms_core.notify.base import BaseNotifier
from bms_core.oauth.base import BaseOAuthServer, BaseScopeChecker
from bms_core.oauth.jwt import JwtServiceTokenIssuerFactory
from bms_core.oauth.token import BaseServiceTokenIssuer
from bms_core.oauth.verify import BaseTokenVerifier, UnifiedTokenVerifierFactory
from bms_core.org.base import BaseOrgDataSource, BaseOrgNameResolver
from bms_core.outbound.http import BaseHttpClient
from bms_core.outbound.webhook import BaseWebhookSender
from bms_core.outbox.base import BaseOutboxDispatcher, BaseOutboxStore
from bms_core.outbox.dispatcher import PollOutboxDispatcher
from bms_core.outbox.store import SqlOutboxStore
from bms_core.password.base import BasePasswordPolicy
from bms_core.permission.base import BasePermissionChecker
from bms_core.preference.base import BasePreferenceStore
from bms_core.print.base import BasePrintExporter, BasePrintTemplateProvider
from bms_core.query.base import BaseQueryProviderRegistry
from bms_core.query.local import LocalQueryProviderRegistry
from bms_core.ratelimit.base import BaseRateLimiter
from bms_core.replay.base import BaseReplayGuard
from bms_core.saga.base import BaseSagaExecutor
from bms_core.saga.choreography import ChoreographySagaExecutor
from bms_core.scope.base import DataScope
from bms_core.search.base import BaseSearchIndex
from bms_core.servicecall.base import (
    DEFAULT_BASE_URL_TEMPLATE,
    SERVICE_CLIENT_OPTION_ATTACH_TOKEN,
    SERVICE_CLIENT_OPTION_BASE_URL,
    BaseServiceClient,
)
from bms_core.servicecall.http import HttpServiceClient
from bms_core.session.base import BaseSessionStore
from bms_core.sharding.base import ShardingRouter
from bms_core.storage.base import BaseMultipartUpload, BaseObjectStorage
from bms_core.tasks.base import BaseTask
from bms_core.tenant.base import BaseTenantSelfService
from bms_core.tracing.base import BaseTracer
from bms_core.transfer.exporter import BaseExporter
from bms_core.transfer.importer import BaseImporter
from bms_core.workflow.base import BaseWorkflowEngine
from bms_core.ws.base import BaseRealtimePublisher

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
    "bms_core.archive.null",
    "bms_core.audit.null",
    "bms_core.boundary.null",
    "bms_core.cache.null",
    "bms_core.captcha.null",
    "bms_core.chat.null",
    "bms_core.circuit.null",
    "bms_core.codecheck.null",
    "bms_core.dashboard.null",
    "bms_core.db.null",
    "bms_core.dict.null",
    "bms_core.edge.null",
    "bms_core.events.null",
    "bms_core.fallback.null",
    "bms_core.fieldtype.null",
    "bms_core.globalsearch.null",
    "bms_core.health.null",
    "bms_core.i18n.null",
    "bms_core.icon.null",
    "bms_core.idempotency.null",
    "bms_core.idp.null",
    "bms_core.listing.null",
    "bms_core.llm.null",
    "bms_core.lock.null",
    "bms_core.masking.null",
    "bms_core.metrics.null",
    "bms_core.notification.null",
    "bms_core.notify.null",
    "bms_core.oauth.null",
    "bms_core.org.null",
    "bms_core.outbound.null",
    "bms_core.outbox.null",
    "bms_core.saga.null",
    "bms_core.password.null",
    "bms_core.permission.null",
    "bms_core.preference.null",
    "bms_core.print.null",
    "bms_core.query.null",
    "bms_core.ratelimit.null",
    "bms_core.replay.null",
    "bms_core.scope.null",
    "bms_core.search.null",
    "bms_core.servicecall.null",
    "bms_core.session.null",
    "bms_core.sharding.null",
    "bms_core.storage.null",
    "bms_core.tasks.null",
    "bms_core.tenant.null",
    "bms_core.tracing.null",
    "bms_core.transfer.null",
    "bms_core.workflow.null",
    "bms_core.ws.null",
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
    PluginWiring("preference", BasePreferenceStore, "preference", "preference_store"),
    PluginWiring("masking", BaseMasker, "masking", "masker"),
    PluginWiring("distributed_lock", BaseDistributedLock, "distributed_lock", "distributed_lock"),
    PluginWiring("edge", BaseEdgeTrust, "edge", "edge"),
    PluginWiring("data_ownership_guard", BaseDataOwnershipGuard, "data_ownership", "data_ownership_guard"),
    PluginWiring("captcha", BaseCaptcha, "captcha", "captcha"),
    PluginWiring("chat_stream", BaseChatStream, "chat_stream", "chat_stream"),
    PluginWiring("chat_session_store", BaseChatSessionStore, "chat_session_store", "chat_session_store"),
    PluginWiring("chat_action_gate", BaseChatActionGate, "chat_action_gate", "chat_action_gate"),
    PluginWiring("password_policy", BasePasswordPolicy, "password_policy", "password_policy"),
    PluginWiring("fallback", BaseFallbackPolicy, "fallback", "fallback_policy"),
    PluginWiring("circuit_breaker", BaseCircuitBreaker, "circuit_breaker", "circuit_breaker"),
    PluginWiring("rate_limiter", BaseRateLimiter, "rate_limiter", "rate_limiter"),
    PluginWiring("idempotency", IdempotencyStore, "idempotency", "idempotency_store"),
    PluginWiring("replay_guard", BaseReplayGuard, "replay_guard", "replay_guard"),
    PluginWiring("metrics", BaseMetrics, "metrics", "metrics"),
    PluginWiring("tracer", BaseTracer, "tracer", "tracer"),
    PluginWiring("health_check_registry", BaseHealthCheckRegistry, "health_check_registry", "health_check_registry"),
    PluginWiring("oauth_server", BaseOAuthServer, "oauth_server", "oauth_server"),
    PluginWiring("scope_checker", BaseScopeChecker, "scope_checker", "scope_checker"),
    PluginWiring("service_token", BaseServiceTokenIssuer, "service_token", "service_token"),
    PluginWiring("token_verifier", BaseTokenVerifier, "token_verifier", "token_verifier"),
    PluginWiring("org_data_source", BaseOrgDataSource, "org_data_source", "org_data_source"),
    PluginWiring("org_name_resolver", BaseOrgNameResolver, "org_name_resolver", "org_name_resolver"),
    PluginWiring("dict_cache_region", DictCacheRegion, "dict_cache_region", "dict_cache_region"),
    PluginWiring("dict_source", BaseDictSource, "dict_source", "dict_source"),
    PluginWiring("dict_translator", BaseDictTranslator, "dict_translator", "dict_translator"),
    PluginWiring("object_storage", BaseObjectStorage, "storage", "object_storage"),
    PluginWiring("multipart_upload", BaseMultipartUpload, "multipart_upload", "multipart_upload"),
    PluginWiring("llm_provider", BaseLlmProvider, "llm_provider", "llm_provider"),
    PluginWiring("search_index", BaseSearchIndex, "search_index", "search_index"),
    PluginWiring("global_search", BaseGlobalSearch, "global_search", "global_search"),
    PluginWiring("audit_search", BaseAuditSearch, "audit_search", "audit_search"),
    PluginWiring("file_content_search", BaseFileContentSearch, "file_content_search", "file_content_search"),
    PluginWiring("notifier", BaseNotifier, "notifier", "notifier"),
    PluginWiring("notification_center", BaseNotificationCenter, "notification_center", "notification_center"),
    PluginWiring("realtime_publisher", BaseRealtimePublisher, "realtime_publisher", "realtime_publisher"),
    PluginWiring("http_client", BaseHttpClient, "http_client", "http_client"),
    PluginWiring("webhook_sender", BaseWebhookSender, "webhook_sender", "webhook_sender"),
    PluginWiring("outbox_store", BaseOutboxStore, "outbox_store", "outbox_store"),
    PluginWiring("outbox_dispatcher", BaseOutboxDispatcher, "outbox", "outbox_dispatcher"),
    PluginWiring("saga_executor", BaseSagaExecutor, "saga", "saga_executor"),
    PluginWiring("service_client", BaseServiceClient, "service_client", "service_client"),
    PluginWiring("workflow_engine", BaseWorkflowEngine, "workflow_engine", "workflow_engine"),
    PluginWiring("identity_provider", BaseIdentityProvider, "identity_provider", "identity_provider"),
    PluginWiring("session_store", BaseSessionStore, "session_store", "session_store"),
    PluginWiring(
        "query_provider_registry", BaseQueryProviderRegistry, "query_provider_registry", "query_provider_registry"
    ),
    PluginWiring("query_scheme_store", BaseQuerySchemeStore, "query_scheme_store", "query_scheme_store"),
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
    PluginWiring("cache", CacheRegion, "cache", "cache"),
    PluginWiring("audit", AuditCapturer, "audit", "audit"),
    PluginWiring("task", BaseTask, "task", "task"),
    PluginWiring("tenant_self_service", BaseTenantSelfService, "tenant_self_service", "tenant_self_service"),
    PluginWiring("print_template", BasePrintTemplateProvider, "print_template", "print_template"),
    PluginWiring("print_exporter", BasePrintExporter, "print_exporter", "print_exporter"),
    PluginWiring("icon_registry", BaseIconRegistry, "icon_registry", "icon_registry"),
    PluginWiring("code_validator", BaseCodeValidator, "code_validator", "code_validator"),
    PluginWiring("event", EventPublisher, "event", "event_publisher"),
    PluginWiring("event_consumer", BaseEventConsumer, "event_consumer", None),  # 消费轨：仅预热，无 app.state 落点
)


def register_platform_plugins(settings: Settings, app: FastAPI, resources: ResourceManager) -> None:
    """登记平台内建实现（显式工厂：延迟导入 / 依赖注入）；同一注册表仅登记一次。

    Args:
        settings: 应用配置（工厂登记可读取能力选择）。
        app: 应用实例（依赖注入型工厂读取运行期对象，如引擎注册表）。
        resources: 应用资源登记表（工厂内需要随生命周期释放的检查项）。
    """
    registry = default_plugin_registry()
    if any(item is registry for item in _PREPARED_REGISTRIES):
        return
    for module in _NULL_MODULES:
        import_module(module)
    # 链路真实实现（`otel`，零参可实例化）：导入即经继承自动登记
    import_module("bms_core.tracing.otel")
    register_platform_event_contracts()
    register_plugin("masking", NULL_PLUGIN_NAME, DefaultMaskerFactory(settings))
    register_plugin("health_check_registry", "local", HealthCheckRegistryFactory(settings, app, resources))
    register_plugin("object_storage", "local", LocalObjectStorageFactory(settings))
    register_plugin("object_storage", "minio", MinioObjectStorageFactory(settings))
    register_plugin("cache", "memory", MemoryCacheRegionFactory())
    register_plugin("cache", "redis", RedisCacheRegionFactory(settings))
    register_plugin("dict_cache_region", "memory", MemoryDictCacheRegionFactory())
    register_plugin("dict_cache_region", "redis", RedisDictCacheRegionFactory(settings))
    register_plugin("dict_source", "sql", SqlDictSourceFactory(app))
    register_plugin("dict_translator", "sql", SqlDictTranslatorFactory(app))
    # 跨服务读出口（06_02）：非 platform 服务经公开契约读平台服务字典接口（权威侧仍为 platform）
    register_plugin("dict_source", "http", HttpDictSourceFactory(app))
    register_plugin("dict_translator", "http", HttpDictTranslatorFactory(app))
    register_plugin("query_scheme_store", "sql", SqlQuerySchemeStoreFactory(app))
    register_plugin("field_type_registry", "local", LocalFieldTypeRegistryFactory())
    register_plugin("query_provider_registry", "local", LocalQueryProviderRegistryFactory(app))
    register_plugin("edge", "marker", MarkerEdgeTrustFactory(settings))
    register_plugin("edge", "service_jwt", ServiceJwtEdgeTrustFactory(settings))
    register_plugin("identity_provider", "oidc", OidcIdentityProviderFactory(settings))
    register_plugin("service_token", "jwt", JwtServiceTokenIssuerFactory(settings))
    register_plugin("token_verifier", "unified", UnifiedTokenVerifierFactory(settings))
    register_plugin("data_ownership_guard", "table", TableOwnershipGuardFactory(settings))
    register_plugin("service_client", "http", HttpServiceClientFactory(settings))
    register_plugin("outbox_store", "sql", SqlOutboxStoreFactory(settings))
    register_plugin("outbox_dispatcher", "poll", PollOutboxDispatcherFactory(settings, app))
    register_plugin("saga_executor", "choreography", ChoreographySagaExecutorFactory(settings))
    register_plugin("idempotency", "redis", RedisIdempotencyStoreFactory(settings))
    register_plugin("metrics", "prometheus", PrometheusMetricsFactory(settings))
    _PREPARED_REGISTRIES.append(registry)


class PrometheusMetricsFactory(BasePluginFactory[PrometheusMetrics]):
    """Prometheus 指标真实实现工厂（注入服务身份，指标统一按服务归因）。"""

    plugin_key: str = "metrics"
    plugin_name: str = "prometheus"

    def __init__(self, settings: Settings) -> None:
        """初始化。

        Args:
            settings: 应用配置（取 `[app].service` 作 `service` 标签）。
        """
        self._settings = settings

    def create(self, options: None = None) -> PrometheusMetrics:
        """构造 Prometheus 指标实现。

        Args:
            options: 未使用（零参口径）。

        Returns:
            PrometheusMetrics: 指标实现实例。
        """
        return PrometheusMetrics(self._settings.app.service)


class LocalObjectStorageFactory(BasePluginFactory[BaseObjectStorage]):
    """本地文件系统存储工厂（根目录取 `[storage].options.root`，缺省 `var/storage`）。"""

    plugin_key: str = "object_storage"
    plugin_name: str = "local"

    def __init__(self, settings: Settings) -> None:
        """初始化。

        Args:
            settings: 应用配置。
        """
        self._settings = settings

    def create(self, options: None = None) -> BaseObjectStorage:
        """构造本地存储实例（延迟导入实现模块）。

        Args:
            options: 未使用（零参口径）。

        Returns:
            BaseObjectStorage: 本地文件系统实现。
        """
        from bms_core.storage.local import DEFAULT_ROOT, LocalObjectStorage

        root = self._settings.storage.options.get("root") or DEFAULT_ROOT
        return LocalObjectStorage(root=cast("str", root))


class MinioObjectStorageFactory(BasePluginFactory[BaseObjectStorage]):
    """MinIO 存储工厂（校验 SDK 依赖与端点 / 凭据齐备；不建连）。"""

    plugin_key: str = "object_storage"
    plugin_name: str = "minio"

    def __init__(self, settings: Settings) -> None:
        """初始化。

        Args:
            settings: 应用配置。
        """
        self._settings = settings

    def create(self, options: None = None) -> BaseObjectStorage:
        """构造 MinIO 存储实例（依赖 / 配置校验在实例化前完成）。

        Args:
            options: 未使用（零参口径）。

        Returns:
            BaseObjectStorage: MinIO 实现。

        Raises:
            PluginError: 依赖缺失 / 配置不全。
        """
        try:
            import_module("minio")
        except ModuleNotFoundError as exc:
            raise PluginError("minio 实现依赖未安装：uv sync --extra storage-minio") from exc
        minio_settings = self._settings.minio
        if not (minio_settings.endpoint and minio_settings.access_key and minio_settings.secret_key):
            raise PluginError("minio 实现缺少端点 / 凭据配置（经 BMS_MINIO__* 环境变量注入）")
        from bms_core.storage.base import STORAGE_BUCKET
        from bms_core.storage.minio import MinioObjectStorage

        bucket = self._settings.storage.options.get("bucket") or STORAGE_BUCKET
        return MinioObjectStorage(
            endpoint=minio_settings.endpoint,
            access_key=minio_settings.access_key,
            secret_key=minio_settings.secret_key,
            bucket=cast("str", bucket),
            secure=minio_settings.secure,
        )


class HealthCheckRegistryFactory(BasePluginFactory[HealthCheckRegistry]):
    """真实健康检查注册表工厂（注入超时配置与 `redis` / `database` 检查项）。"""

    plugin_key: str = "health_check_registry"
    plugin_name: str = "local"

    def __init__(self, settings: Settings, app: FastAPI, resources: ResourceManager) -> None:
        """初始化。

        Args:
            settings: 应用配置。
            app: 应用实例。
            resources: 资源登记表（`redis` 检查项随生命周期释放）。
        """
        self._settings = settings
        self._app = app
        self._resources = resources

    def create(self, options: None = None) -> HealthCheckRegistry:
        """构造真实注册表并登记检查项。

        Args:
            options: 未使用（零参口径）。

        Returns:
            HealthCheckRegistry: 注册表实例。
        """
        registry = HealthCheckRegistry(
            check_timeout_ms=self._settings.health.check_timeout_ms,
            total_timeout_ms=self._settings.health.total_timeout_ms,
        )
        redis_check = RedisHealthCheck(self._settings.redis.url)
        registry.register(redis_check)
        registry.register(DatabaseHealthCheck(cast("EngineRegistry", self._app.state.engine_registry)))
        # 非必需项：服务目录快照可达性（06_01；失败只标记降级可见，不产生 503）
        registry.register(CatalogHealthCheck(self._app))
        self._resources.register(redis_check)
        return registry


class DefaultMaskerFactory(BasePluginFactory[BaseMasker]):
    """缺省掩码器工厂（注入权限检查器；`NullMasker` 构造需参数，不自动登记）。"""

    plugin_key: str = "masking"
    plugin_name: str = NULL_PLUGIN_NAME

    def __init__(self, settings: Settings) -> None:
        """初始化。

        Args:
            settings: 应用配置。
        """
        self._settings = settings

    def create(self, options: None = None) -> BaseMasker:
        """构造缺省掩码器（解析权限检查器实例）。

        Args:
            options: 未使用（零参口径）。

        Returns:
            BaseMasker: 掩码器实例。
        """
        checker = cast(
            "BasePermissionChecker",
            resolve_plugin(
                "permission",
                self._settings.permission.provider,
                expected_version=BasePermissionChecker.contract_version,
            ),
        )
        return NullMasker(checker=checker)


class HttpServiceClientFactory(BasePluginFactory[HttpServiceClient]):
    """服务间调用真实实现工厂（注入熔断 / 降级 / 限流实例与基址模板）。"""

    plugin_key: str = "service_client"
    plugin_name: str = "http"

    def __init__(self, settings: Settings) -> None:
        """初始化。

        Args:
            settings: 应用配置（含 `[service_client]` 与各韧性能力选择）。
        """
        self._settings = settings

    def create(self, options: None = None) -> HttpServiceClient:
        """构造服务间调用实现（解析韧性三件套与基址模板）。

        Args:
            options: 未使用（零参口径）。

        Returns:
            HttpServiceClient: 服务间调用实现。
        """
        template = (
            self._settings.service_client.options.get(SERVICE_CLIENT_OPTION_BASE_URL) or DEFAULT_BASE_URL_TEMPLATE
        )
        circuit = cast(
            "BaseCircuitBreaker",
            resolve_plugin(
                "circuit_breaker",
                self._settings.circuit_breaker.provider,
                expected_version=BaseCircuitBreaker.contract_version,
            ),
        )
        fallback = cast(
            "BaseFallbackPolicy",
            resolve_plugin(
                "fallback",
                self._settings.fallback.provider,
                expected_version=BaseFallbackPolicy.contract_version,
            ),
        )
        rate_limiter = cast(
            "BaseRateLimiter",
            resolve_plugin(
                "rate_limiter",
                self._settings.rate_limiter.provider,
                expected_version=BaseRateLimiter.contract_version,
            ),
        )
        service_token = cast(
            "BaseServiceTokenIssuer",
            resolve_plugin(
                "service_token",
                self._settings.service_token.provider,
                expected_version=BaseServiceTokenIssuer.contract_version,
            ),
        )
        attach_service_token = bool(
            self._settings.service_client.options.get(SERVICE_CLIENT_OPTION_ATTACH_TOKEN) or False
        )
        return HttpServiceClient(
            circuit_breaker=circuit,
            fallback_policy=fallback,
            rate_limiter=rate_limiter,
            base_url_template=cast("str", template),
            token_issuer=service_token,
            attach_service_token=attach_service_token,
        )


class MarkerEdgeTrustFactory(BasePluginFactory[MarkerEdgeTrust]):
    """边缘信任标记实现工厂（期望值取 `[edge].options.gateway_identity`，缺省基座常量）。"""

    plugin_key: str = "edge"
    plugin_name: str = "marker"

    def __init__(self, settings: Settings) -> None:
        """初始化。

        Args:
            settings: 应用配置。
        """
        self._settings = settings

    def create(self, options: None = None) -> MarkerEdgeTrust:
        """构造网关标记头信任实现。

        Args:
            options: 未使用（零参口径）。

        Returns:
            MarkerEdgeTrust: 标记头信任实现。
        """
        expected = self._settings.edge.options.get("gateway_identity") or GATEWAY_IDENTITY_VALUE
        return MarkerEdgeTrust(expected=cast("str", expected))


class TableOwnershipGuardFactory(BasePluginFactory[TableOwnershipGuard]):
    """数据所有权守卫工厂（`table` 真实实现）：载入例外白名单并注入服务身份 / 模式 / 指标器。"""

    plugin_key: str = "data_ownership_guard"
    plugin_name: str = "table"

    def __init__(self, settings: Settings) -> None:
        """初始化。

        Args:
            settings: 应用配置（服务身份、`[data_ownership]` 与各能力选择）。
        """
        self._settings = settings

    def create(self, options: None = None) -> TableOwnershipGuard:
        """构造表前缀归属守卫。

        Args:
            options: 未使用（零参口径）。

        Returns:
            TableOwnershipGuard: 数据所有权守卫实例。

        Raises:
            PluginError: 例外白名单结构非法。
        """
        settings = self._settings
        path = Path(settings.data_ownership.exceptions_file)
        if not path.is_absolute():
            path = BACKEND_ROOT.parent / path
        entries = load_exceptions(path)
        errors = validate_exceptions(
            entries,
            known_tables=known_tables(),
            known_prefixes=known_prefixes(),
            known_services=known_services(),
        )
        if errors:
            raise PluginError("数据所有权例外白名单非法：" + "；".join(errors))
        metrics = cast(
            "BaseMetrics",
            resolve_plugin("metrics", settings.metrics.provider, expected_version=BaseMetrics.contract_version),
        )
        return TableOwnershipGuard(
            settings.app.service,
            mode=settings.data_ownership.mode,
            exceptions=entries,
            metrics=metrics,
        )


class SqlOutboxStoreFactory(BasePluginFactory[SqlOutboxStore]):
    """发件箱存储真实实现工厂（`sql`：SQLAlchemy 会话绑定 + 签发契约校验模式）。

    零参工厂**不声明 `plugin_name`**（避免被插件注册表自动收集）；经 `register_plugin` 显式登记。
    """

    plugin_key: str = "outbox_store"

    def __init__(self, settings: Settings) -> None:
        """初始化。

        Args:
            settings: 应用配置（`[event].contract_mode` 签发契约校验模式）。
        """
        self._settings = settings

    def create(self, options: None = None) -> SqlOutboxStore:
        """构造发件箱存储。

        Args:
            options: 未使用（零参口径）。

        Returns:
            SqlOutboxStore: 发件箱存储实例。
        """
        return SqlOutboxStore(contract_mode=self._settings.event.contract_mode)


class PollOutboxDispatcherFactory(BasePluginFactory[PollOutboxDispatcher]):
    """投递器真实实现工厂（`poll`：注入存储 / 发布器 / 引擎注册表 / 指标 / 配置）。"""

    plugin_key: str = "outbox_dispatcher"
    plugin_name: str = "poll"

    def __init__(self, settings: Settings, app: FastAPI) -> None:
        """初始化。

        Args:
            settings: 应用配置（`[outbox]` 与各能力选择）。
            app: 应用实例（取引擎注册表与会话工厂）。
        """
        self._settings = settings
        self._app = app

    def create(self, options: None = None) -> PollOutboxDispatcher:
        """构造轮询投递器。

        Args:
            options: 未使用（零参口径）。

        Returns:
            PollOutboxDispatcher: 投递器实例。
        """
        store = cast(
            "BaseOutboxStore",
            resolve_plugin(
                "outbox_store",
                self._settings.outbox_store.provider,
                expected_version=BaseOutboxStore.contract_version,
            ),
        )
        publisher = cast(
            "EventPublisher",
            resolve_plugin(
                "event",
                self._settings.event.provider,
                expected_version=EventPublisher.contract_version,
            ),
        )
        metrics = cast(
            "BaseMetrics",
            resolve_plugin(
                "metrics",
                self._settings.metrics.provider,
                expected_version=BaseMetrics.contract_version,
            ),
        )
        registry = cast("EngineRegistry", self._app.state.engine_registry)
        session_factory = cast("SessionFactory | None", getattr(self._app.state, "session_factory", None))
        return PollOutboxDispatcher.from_settings(
            self._settings,
            store=store,
            publisher=publisher,
            engine_registry=registry,
            session_factory=session_factory,
            metrics=metrics,
        )


class ChoreographySagaExecutorFactory(BasePluginFactory[ChoreographySagaExecutor]):
    """Saga 协同式执行器工厂（`choreography`：注入事务性发件箱存储）。"""

    plugin_key: str = "saga_executor"
    plugin_name: str = "choreography"

    def __init__(self, settings: Settings) -> None:
        """初始化。

        Args:
            settings: 应用配置（`[outbox_store]` 能力选择）。
        """
        self._settings = settings

    def create(self, options: None = None) -> ChoreographySagaExecutor:
        """构造协同式 Saga 执行器。

        Args:
            options: 未使用（零参口径）。

        Returns:
            ChoreographySagaExecutor: 执行器实例。
        """
        store = cast(
            "BaseOutboxStore",
            resolve_plugin(
                "outbox_store",
                self._settings.outbox_store.provider,
                expected_version=BaseOutboxStore.contract_version,
            ),
        )
        return ChoreographySagaExecutor(store)


class RedisIdempotencyStoreFactory(BasePluginFactory[RedisIdempotencyStore]):
    """Redis 幂等存储工厂（`redis`：读取 Redis 连接串，惰性建连）。"""

    plugin_key: str = "idempotency"
    plugin_name: str = "redis"

    def __init__(self, settings: Settings) -> None:
        """初始化。

        Args:
            settings: 应用配置（Redis 连接串）。
        """
        self._settings = settings

    def create(self, options: None = None) -> RedisIdempotencyStore:
        """构造 Redis 幂等存储。

        Args:
            options: 未使用（零参口径）。

        Returns:
            RedisIdempotencyStore: 幂等存储实例。
        """
        return RedisIdempotencyStore(self._settings.redis.url)


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
    app.state.plugin_providers = providers
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


class MemoryCacheRegionFactory(BasePluginFactory[MemoryCacheRegion]):
    """通用内存缓存 Region 工厂（无 Redis 环境 / 测试用）。"""

    plugin_key: str = "cache"
    # 不声明 plugin_name：零参工厂避免被插件注册表自动收集（经 register_plugin 显式登记）

    def create(self, options: None = None) -> MemoryCacheRegion:
        """构造内存 Region。

        Args:
            options: 未使用（零参口径）。

        Returns:
            MemoryCacheRegion: 内存 Region 实例。
        """
        return MemoryCacheRegion(domain="generic")


class RedisCacheRegionFactory(BasePluginFactory[RedisCacheRegion]):
    """Redis 缓存 Region 工厂（连接串取 `settings.redis.url`，不建连）。"""

    plugin_key: str = "cache"
    plugin_name: str = "redis"

    def __init__(self, settings: Settings) -> None:
        """初始化。

        Args:
            settings: 应用配置。
        """
        self._settings = settings

    def create(self, options: None = None) -> RedisCacheRegion:
        """构造 Redis Region。

        Args:
            options: 未使用（零参口径）。

        Returns:
            RedisCacheRegion: Redis Region 实例。
        """
        return RedisCacheRegion(domain="generic", url=self._settings.redis.url)


class MemoryDictCacheRegionFactory(BasePluginFactory[MemoryDictCacheRegion]):
    """字典域内存缓存工厂（L1 双分区 + 进程内版本）。"""

    plugin_key: str = "dict_cache_region"
    # 不声明 plugin_name：零参工厂避免被插件注册表自动收集（经 register_plugin 显式登记）

    def create(self, options: None = None) -> MemoryDictCacheRegion:
        """构造字典域内存缓存。

        Args:
            options: 未使用（零参口径）。

        Returns:
            MemoryDictCacheRegion: 字典域内存缓存实例。
        """
        return MemoryDictCacheRegion()


class RedisDictCacheRegionFactory(BasePluginFactory[RedisDictCacheRegion]):
    """字典域 Redis 缓存工厂（Redis 共享层 + 进程内 L1）。"""

    plugin_key: str = "dict_cache_region"
    plugin_name: str = "redis"

    def __init__(self, settings: Settings) -> None:
        """初始化。

        Args:
            settings: 应用配置。
        """
        self._settings = settings

    def create(self, options: None = None) -> RedisDictCacheRegion:
        """构造字典域 Redis 缓存。

        Args:
            options: 未使用（零参口径）。

        Returns:
            RedisDictCacheRegion: 字典域 Redis 缓存实例。
        """
        return RedisDictCacheRegion(url=self._settings.redis.url)


class SqlDictSourceFactory(BasePluginFactory[SqlDictSource]):
    """字典真实取数工厂（注入引擎注册表与已装配的字典缓存域）。"""

    plugin_key: str = "dict_source"
    plugin_name: str = "sql"

    def __init__(self, app: FastAPI) -> None:
        """初始化。

        Args:
            app: 应用实例（取 `engine_registry` 与已装配 `dict_cache_region`）。
        """
        self._app = app

    def create(self, options: None = None) -> SqlDictSource:
        """构造真实取数实例。

        Args:
            options: 未使用（零参口径）。

        Returns:
            SqlDictSource: 取数实例。
        """
        engines = cast("EngineRegistry", self._app.state.engine_registry)
        cache = cast("DictCacheRegion | None", getattr(self._app.state, "dict_cache_region", None))
        return SqlDictSource(engines=engines, cache=cache)


class HttpDictSourceFactory(BasePluginFactory[HttpDictSource]):
    """字典跨服务取数工厂（06_02）：注入服务间调用客户端（读平台服务字典接口）。"""

    plugin_key: str = "dict_source"
    plugin_name: str = "http"

    def __init__(self, app: FastAPI) -> None:
        """初始化。

        Args:
            app: 应用实例（取配置以解析服务间调用客户端）。
        """
        self._app = app

    def create(self, options: None = None) -> HttpDictSource:
        """构造跨服务取数实例。

        Args:
            options: 未使用（零参口径）。

        Returns:
            HttpDictSource: 取数实例。
        """
        return HttpDictSource(client=_resolve_service_client(self._app))


class HttpDictTranslatorFactory(BasePluginFactory[HttpDictTranslator]):
    """字典跨服务翻译工厂（06_02）：注入服务间调用客户端与已装配字典缓存域。"""

    plugin_key: str = "dict_translator"
    plugin_name: str = "http"

    def __init__(self, app: FastAPI) -> None:
        """初始化。

        Args:
            app: 应用实例（取服务间调用客户端与 `dict_cache_region`）。
        """
        self._app = app

    def create(self, options: None = None) -> HttpDictTranslator:
        """构造跨服务翻译实例。

        Args:
            options: 未使用（零参口径）。

        Returns:
            HttpDictTranslator: 翻译实例。
        """
        cache = cast("DictCacheRegion | None", getattr(self._app.state, "dict_cache_region", None))
        return HttpDictTranslator(client=_resolve_service_client(self._app), cache=cache)


def _resolve_service_client(app: FastAPI) -> BaseServiceClient:
    """解析已装配的服务间调用客户端（跨服务读出口依赖）。

    Args:
        app: 应用实例（取装配配置）。

    Returns:
        BaseServiceClient: 服务间调用客户端。
    """
    settings = cast("Settings", app.state.settings)
    return cast(
        "BaseServiceClient",
        resolve_plugin(
            "service_client",
            settings.service_client.provider,
            expected_version=BaseServiceClient.contract_version,
        ),
    )


class SqlDictTranslatorFactory(BasePluginFactory[SqlDictTranslator]):
    """字典真实翻译工厂（与取数共用同一份字典缓存域）。"""

    plugin_key: str = "dict_translator"
    plugin_name: str = "sql"

    def __init__(self, app: FastAPI) -> None:
        """初始化。

        Args:
            app: 应用实例（取 `engine_registry` 与已装配 `dict_cache_region`）。
        """
        self._app = app

    def create(self, options: None = None) -> SqlDictTranslator:
        """构造真实翻译实例。

        Args:
            options: 未使用（零参口径）。

        Returns:
            SqlDictTranslator: 翻译实例。
        """
        engines = cast("EngineRegistry", self._app.state.engine_registry)
        cache = cast("DictCacheRegion | None", getattr(self._app.state, "dict_cache_region", None))
        return SqlDictTranslator(engines=engines, cache=cache)


class SqlQuerySchemeStoreFactory(BasePluginFactory[SqlQuerySchemeStore]):
    """查询方案真实存储工厂（租户库落库）。"""

    plugin_key: str = "query_scheme_store"
    plugin_name: str = "sql"

    def __init__(self, app: FastAPI) -> None:
        """初始化。

        Args:
            app: 应用实例（取 `engine_registry`）。
        """
        self._app = app

    def create(self, options: None = None) -> SqlQuerySchemeStore:
        """构造查询方案存储。

        Args:
            options: 未使用（零参口径）。

        Returns:
            SqlQuerySchemeStore: 存储实例。
        """
        engines = cast("EngineRegistry", self._app.state.engine_registry)
        return SqlQuerySchemeStore(engines=engines)


class LocalFieldTypeRegistryFactory(BasePluginFactory[LocalFieldTypeRegistry]):
    """字段类型真实注册表工厂（内建类型随构造注册）。"""

    plugin_key: str = "field_type_registry"
    # 不声明 plugin_name：零参工厂避免被插件注册表自动收集（经 register_plugin 显式登记）

    def create(self, options: None = None) -> LocalFieldTypeRegistry:
        """构造字段类型注册表。

        Args:
            options: 未使用（零参口径）。

        Returns:
            LocalFieldTypeRegistry: 注册表实例。
        """
        return LocalFieldTypeRegistry()


class LocalQueryProviderRegistryFactory(BasePluginFactory[LocalQueryProviderRegistry]):
    """查询提供者真实注册表工厂（注册字典域内建示例提供者）。"""

    plugin_key: str = "query_provider_registry"
    plugin_name: str = "local"

    def __init__(self, app: FastAPI) -> None:
        """初始化。

        Args:
            app: 应用实例（取 `engine_registry`）。
        """
        self._app = app

    def create(self, options: None = None) -> LocalQueryProviderRegistry:
        """构造查询提供者注册表并注册内建提供者。

        Args:
            options: 未使用（零参口径）。

        Returns:
            LocalQueryProviderRegistry: 注册表实例。
        """
        engines = cast("EngineRegistry", self._app.state.engine_registry)
        registry = LocalQueryProviderRegistry()
        registry.register(BuiltinDictQueryProvider(engines=engines))
        return registry
