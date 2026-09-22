"""公共依赖汇总：数据访问、租户解析与各能力域基座提供者。

掩码 / 权限 / 锁 / 认证 / 故障应对 / 可观测 / 探针 / 开放接口 / 存储 / 分片上传 / LLM / 检索 / 通知 /
推送 / 出站 / 工作流 / 归档 / 身份源 / 会话 / 查询 / 导入导出 / 打印导出 / 审计链 / 字段类型 / 国际化 /
工作台等各能力域基座提供者统一从本模块导出，业务路由按需导入，避免分散引用。
"""

from typing import cast

from fastapi import Request

from bms_core.archive.base import get_archive_policy, get_archive_query_router
from bms_core.audit.base import get_audit_capturer
from bms_core.audit.hashchain import get_hash_chain
from bms_core.cache.base import get_cache_region
from bms_core.captcha.base import get_captcha
from bms_core.chat.base import get_chat_action_gate, get_chat_session_store, get_chat_stream
from bms_core.circuit.base import get_circuit_breaker
from bms_core.codecheck.base import get_code_validator
from bms_core.dashboard.base import get_dashboard_card_registry
from bms_core.db.health import PrimaryHealth
from bms_core.db.registry import EngineRegistry
from bms_core.db.session import SessionFactory, get_db, get_read_db, get_uow, get_write_db
from bms_core.db.tenant import TenantContext, get_tenant
from bms_core.db.tenant_source import TenantSource
from bms_core.dict.base import get_dict_cache_region, get_dict_source, get_dict_translator
from bms_core.dict.query import DictQueryService
from bms_core.dict.service import DictService
from bms_core.events.base import get_event_publisher
from bms_core.fallback.base import get_fallback_policy
from bms_core.fieldtype.base import get_field_type_registry
from bms_core.globalsearch.base import get_audit_search, get_file_content_search, get_global_search
from bms_core.health.base import get_health_check_registry
from bms_core.i18n.base import get_translator
from bms_core.icon.base import get_icon_registry
from bms_core.idempotency.base import get_idempotency_store
from bms_core.idp.base import get_identity_provider
from bms_core.listing.base import get_query_scheme_store
from bms_core.llm.base import get_llm_provider
from bms_core.lock.base import get_distributed_lock
from bms_core.masking.base import get_masker
from bms_core.metrics.base import get_metrics
from bms_core.notification.base import get_notification_center
from bms_core.notify.base import get_notifier
from bms_core.oauth.base import get_oauth_server, get_scope_checker
from bms_core.org.base import get_org_data_source, get_org_name_resolver
from bms_core.outbound.http import get_http_client
from bms_core.outbound.webhook import get_webhook_sender
from bms_core.password.base import get_password_policy
from bms_core.permission.base import get_permission_checker
from bms_core.preference.base import get_preference_store
from bms_core.print.base import get_print_exporter, get_print_template_provider
from bms_core.query.base import get_query_provider_registry
from bms_core.ratelimit.base import get_rate_limiter
from bms_core.replay.base import get_replay_guard
from bms_core.search.base import get_search_index
from bms_core.session.base import get_session_store
from bms_core.storage.base import get_multipart_upload, get_object_storage
from bms_core.tasks.base import get_task
from bms_core.tenant.base import get_tenant_self_service
from bms_core.tracing.base import get_tracer
from bms_core.transfer.exporter import get_exporter
from bms_core.transfer.importer import get_importer
from bms_core.workflow.base import get_workflow_engine
from bms_core.ws.base import get_realtime_publisher

__all__ = [
    "SessionFactory",
    "current_code_of",
    "get_archive_policy",
    "get_archive_query_router",
    "get_audit_capturer",
    "get_audit_search",
    "get_cache_region",
    "get_captcha",
    "get_chat_action_gate",
    "get_chat_session_store",
    "get_chat_stream",
    "get_circuit_breaker",
    "get_code_validator",
    "get_dashboard_card_registry",
    "get_db",
    "get_dict_cache_region",
    "get_dict_query_service",
    "get_dict_service",
    "get_dict_source",
    "get_dict_translator",
    "get_distributed_lock",
    "get_event_publisher",
    "get_exporter",
    "get_fallback_policy",
    "get_field_type_registry",
    "get_file_content_search",
    "get_global_search",
    "get_hash_chain",
    "get_health_check_registry",
    "get_http_client",
    "get_icon_registry",
    "get_idempotency_store",
    "get_identity_provider",
    "get_importer",
    "get_llm_provider",
    "get_masker",
    "get_metrics",
    "get_multipart_upload",
    "get_notification_center",
    "get_notifier",
    "get_oauth_server",
    "get_object_storage",
    "get_org_data_source",
    "get_org_name_resolver",
    "get_password_policy",
    "get_permission_checker",
    "get_preference_store",
    "get_primary_health",
    "get_print_exporter",
    "get_print_template_provider",
    "get_query_provider_registry",
    "get_query_scheme_store",
    "get_rate_limiter",
    "get_read_db",
    "get_realtime_publisher",
    "get_replay_guard",
    "get_scope_checker",
    "get_search_index",
    "get_session_store",
    "get_task",
    "get_tenant",
    "get_tenant_self_service",
    "get_tenant_source",
    "get_tracer",
    "get_translator",
    "get_uow",
    "get_webhook_sender",
    "get_workflow_engine",
    "get_write_db",
]


def get_dict_service(request: Request) -> DictService:
    """取字典写路径服务（请求级组装：引擎注册表 + 字典缓存域）。

    Args:
        request: 请求对象。

    Returns:
        DictService: 字典写路径服务实例。
    """
    engines = cast("EngineRegistry", request.app.state.engine_registry)
    return DictService(engines=engines, cache=get_dict_cache_region(request))


def get_dict_query_service(request: Request) -> DictQueryService:
    """取字典高级查询服务（请求级组装：引擎注册表）。

    Args:
        request: 请求对象。

    Returns:
        DictQueryService: 字典高级查询服务实例。
    """
    engines = cast("EngineRegistry", request.app.state.engine_registry)
    return DictQueryService(engines=engines)


def get_primary_health(request: Request) -> PrimaryHealth:
    """取主库可用性状态（只读降级标记与探测）。

    Args:
        request: 请求对象。

    Returns:
        PrimaryHealth: 主库可用性实例。
    """
    return cast("PrimaryHealth", request.app.state.primary_health)


def get_tenant_source(request: Request) -> TenantSource:
    """取租户源（平台库注册记录取数 / 缓存失效；租户管理阶段写路径取用）。

    Args:
        request: 请求对象。

    Returns:
        TenantSource: 应用装配的租户源实例。
    """
    return cast("TenantSource", request.app.state.tenant_source)


def current_code_of(tenant: TenantContext | None) -> str | None:
    """取解析链当前租户编码（供幂等 / 限流键的租户作用域位与租户自助接口复用）。

    Args:
        tenant: 请求级租户上下文（豁免路径为 None）。

    Returns:
        str | None: 当前租户编码；无上下文为空。
    """
    return tenant.tenant_code if tenant is not None else None
