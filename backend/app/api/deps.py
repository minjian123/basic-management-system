"""公共依赖汇总：数据访问、租户解析与各能力域基座提供者。

掩码 / 权限 / 锁 / 认证 / 故障应对 / 可观测 / 健康检查 / 开放接口 / 对象存储等提供者统一从本模块导出，
业务路由按需导入，避免分散引用。
"""

from app.captcha.base import get_captcha
from app.circuit.base import get_circuit_breaker
from app.db.session import build_session_factory, get_db, get_uow
from app.db.tenant import get_tenant
from app.fallback.base import get_fallback_policy
from app.health.base import get_health_check_registry
from app.idempotency.base import get_idempotency_store
from app.lock.base import get_distributed_lock
from app.masking.base import get_masker
from app.metrics.base import get_metrics
from app.oauth.base import get_oauth_server, get_scope_checker
from app.password.base import get_password_policy
from app.permission.base import get_permission_checker
from app.ratelimit.base import get_rate_limiter
from app.replay.base import get_replay_guard
from app.storage.base import get_object_storage
from app.tracing.base import get_tracer

__all__ = [
    "build_session_factory",
    "get_captcha",
    "get_circuit_breaker",
    "get_db",
    "get_distributed_lock",
    "get_fallback_policy",
    "get_health_check_registry",
    "get_idempotency_store",
    "get_masker",
    "get_metrics",
    "get_oauth_server",
    "get_object_storage",
    "get_password_policy",
    "get_permission_checker",
    "get_rate_limiter",
    "get_replay_guard",
    "get_scope_checker",
    "get_tenant",
    "get_tracer",
    "get_uow",
]
