"""公共依赖汇总：数据访问（会话 / 工作单元）、租户解析与能力域基座（掩码 / 权限校验）。

统一从本模块导出，业务路由按需导入，避免分散引用。
"""

from app.db.session import build_session_factory, get_db, get_uow
from app.db.tenant import get_tenant
from app.masking.base import get_masker
from app.permission.base import get_permission_checker

__all__ = [
    "build_session_factory",
    "get_db",
    "get_masker",
    "get_permission_checker",
    "get_tenant",
    "get_uow",
]
