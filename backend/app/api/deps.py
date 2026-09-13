"""公共依赖汇总：数据访问（会话 / 工作单元）与租户解析。

统一从本模块导出，业务路由按需导入，避免分散引用。
"""

from app.db.session import build_session_factory, get_db, get_uow
from app.db.tenant import get_tenant

__all__ = ["build_session_factory", "get_db", "get_tenant", "get_uow"]
