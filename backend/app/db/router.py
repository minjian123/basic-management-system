"""数据源路由：按请求租户上下文选择平台库或租户库引擎。"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncEngine

from ..core.context import get_tenant_code
from .engine import get_platform_engine, get_tenant_engine


async def resolve_engine() -> AsyncEngine:
    """按当前请求租户上下文返回对应引擎。

    有租户上下文（租户级请求）→ 租户库引擎；无租户上下文（平台级请求，如租户开通）→ 平台库引擎。
    """
    tenant_code = get_tenant_code()
    if tenant_code:
        return await get_tenant_engine(tenant_code)
    return await get_platform_engine()
