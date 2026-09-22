"""公共依赖汇总：数据访问、租户解析与各能力域基座提供者。

掩码 / 权限 / 锁 / 认证 / 故障应对 / 可观测 / 探针 / 开放接口 / 存储 / 分片上传 / LLM / 检索 / 通知 /
推送 / 出站 / 工作流 / 归档 / 身份源 / 会话 / 查询 / 导入导出 / 打印导出 / 审计链 / 字段类型 / 国际化 /
工作台等各能力域基座提供者统一从本模块导出，业务路由按需导入，避免分散引用。
"""

from typing import cast

from fastapi import Request

from app.archive.base import get_archive_policy, get_archive_query_router
from app.audit.base import get_audit_capturer
from app.audit.hashchain import get_hash_chain
from app.cache.base import get_cache_region
from app.captcha.base import get_captcha
from app.chat.base import get_chat_action_gate, get_chat_session_store, get_chat_stream
from app.circuit.base import get_circuit_breaker
from app.codecheck.base import get_code_validator
from app.dashboard.base import get_dashboard_card_registry
from app.db.health import PrimaryHealth
from app.db.registry import EngineRegistry
from app.db.session import SessionFactory, get_db, get_read_db, get_uow, get_write_db
from app.db.tenant import get_tenant
from app.db.tenant_source import TenantSource
from app.dict.base import get_dict_cache_region, get_dict_source, get_dict_translator
from app.dict.query import DictQueryService
from app.dict.service import DictService
from app.events.base import get_event_publisher
from app.fallback.base import get_fallback_policy
from app.fieldtype.base import get_field_type_registry
from app.globalsearch.base import get_audit_search, get_file_content_search, get_global_search
from app.health.base import get_health_check_registry
from app.i18n.base import get_translator
from app.icon.base import get_icon_registry
from app.idempotency.base import get_idempotency_store
from app.idp.base import get_identity_provider
from app.listing.base import get_query_scheme_store
from app.llm.base import get_llm_provider
from app.lock.base import get_distributed_lock
from app.masking.base import get_masker
from app.metrics.base import get_metrics
from app.notification.base import get_notification_center
from app.notify.base import get_notifier
from app.oauth.base import get_oauth_server, get_scope_checker
from app.org.base import get_org_data_source, get_org_name_resolver
from app.outbound.http import get_http_client
from app.outbound.webhook import get_webhook_sender
from app.password.base import get_password_policy
from app.permission.base import get_permission_checker
from app.preference.base import get_preference_store
from app.print.base import get_print_exporter, get_print_template_provider
from app.query.base import get_query_provider_registry
from app.ratelimit.base import get_rate_limiter
from app.replay.base import get_replay_guard
from app.search.base import get_search_index
from app.session.base import get_session_store
from app.storage.base import get_multipart_upload, get_object_storage
from app.tasks.base import get_task
from app.tenant.base import get_tenant_self_service
from app.tracing.base import get_tracer
from app.transfer.exporter import get_exporter
from app.transfer.importer import get_importer
from app.workflow.base import get_workflow_engine
from app.ws.base import get_realtime_publisher

__all__ = [
    "SessionFactory",
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
