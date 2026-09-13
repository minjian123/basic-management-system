"""公共依赖汇总：数据访问（会话 / 工作单元）、租户解析与能力域基座（掩码 / 权限 / 锁 / 认证 / 故障应对）。

统一从本模块导出，业务路由按需导入，避免分散引用。
"""

from app.captcha.base import get_captcha
from app.circuit.base import get_circuit_breaker
from app.db.session import build_session_factory, get_db, get_uow
from app.db.tenant import get_tenant
from app.fallback.base import get_fallback_policy
from app.lock.base import get_distributed_lock
from app.masking.base import get_masker
from app.password.base import get_password_policy
from app.permission.base import get_permission_checker

__all__ = [
    "build_session_factory",
    "get_captcha",
    "get_circuit_breaker",
    "get_db",
    "get_distributed_lock",
    "get_fallback_policy",
    "get_masker",
    "get_password_policy",
    "get_permission_checker",
    "get_tenant",
    "get_uow",
]
