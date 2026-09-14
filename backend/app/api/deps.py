"""公共依赖汇总：数据访问、租户解析与各能力域基座提供者。

掩码 / 权限 / 锁 / 认证 / 故障应对 / 可观测 / 探针 / 开放接口 / 存储 / LLM / 检索 / 通知 / 推送 / 出站 / 工作流等
各能力域基座提供者统一从本模块导出，业务路由按需导入，避免分散引用。
"""

from app.captcha.base import get_captcha
from app.circuit.base import get_circuit_breaker
from app.db.session import build_session_factory, get_db, get_uow
from app.db.tenant import get_tenant
from app.fallback.base import get_fallback_policy
from app.health.base import get_health_check_registry
from app.idempotency.base import get_idempotency_store
from app.llm.base import get_llm_provider
from app.lock.base import get_distributed_lock
from app.masking.base import get_masker
from app.metrics.base import get_metrics
from app.notify.base import get_notifier
from app.oauth.base import get_oauth_server, get_scope_checker
from app.outbound.http import get_http_client
from app.outbound.webhook import get_webhook_sender
from app.password.base import get_password_policy
from app.permission.base import get_permission_checker
from app.ratelimit.base import get_rate_limiter
from app.replay.base import get_replay_guard
from app.search.base import get_search_index
from app.storage.base import get_object_storage
from app.tracing.base import get_tracer
from app.workflow.base import get_workflow_engine
from app.ws.base import get_realtime_publisher

__all__ = [
    "build_session_factory",
    "get_captcha",
    "get_circuit_breaker",
    "get_db",
    "get_distributed_lock",
    "get_fallback_policy",
    "get_health_check_registry",
    "get_http_client",
    "get_idempotency_store",
    "get_llm_provider",
    "get_masker",
    "get_metrics",
    "get_notifier",
    "get_oauth_server",
    "get_object_storage",
    "get_password_policy",
    "get_permission_checker",
    "get_rate_limiter",
    "get_realtime_publisher",
    "get_replay_guard",
    "get_scope_checker",
    "get_search_index",
    "get_tenant",
    "get_tracer",
    "get_uow",
    "get_webhook_sender",
    "get_workflow_engine",
]
