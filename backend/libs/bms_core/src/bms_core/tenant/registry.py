"""租户注册库解析：租户引用（编码 + 库名基）的唯一读取入口（14_04 自 `ops.migrate_tenants` 下沉）。

- `TenantRef`：租户引用值对象（`code` 当前编码 / `db_basis` 库名基，缺对照行回落编码）。
- `tenant_refs`：读租户注册库（`sys_tenant` 左联 `sys_tenant_database`），返回未软删租户引用；
  **达梦**无异步驱动方言，走 `asyncio.to_thread` 复用同步实现 `tenant_refs_sync`。
- `tenant_refs_sync`：同步实现（达梦等同步驱动场景直接调用）。

口径：库名基 `db_basis` 是**租户库键 / 库名的派生依据**（创建时冻结；编码变更不随之变），
一律经对照表 `sys_tenant_database` 取数，缺对照行回落当前编码（离线 / 演练可用）。

归属：本模块属租户能力域的**注册库读取机制**，被开通编排内核与 `ops` 运维脚本（批量迁移 / 建库 /
种子）共同复用；只依赖 `bms_core`，不导入 `ops` 与任何服务包。
"""

import asyncio
from dataclasses import dataclass

from sqlalchemy import create_engine, select
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.objects import BaseValueObject

__all__ = ["TenantRef", "tenant_refs", "tenant_refs_sync"]

_DM = "dm"
"""达梦方言名（同步驱动，无异步方言）。"""


@dataclass(frozen=True)
class TenantRef(BaseValueObject):
    """租户引用（编码 + 库名基）：库键按 `db_basis` 派生（10_04）。"""

    code: str
    """租户编码（当前值）。"""

    db_basis: str
    """库名基（对照表 `sys_tenant_database`；缺行回落编码）。"""


def _ref(code: object, db_basis: object) -> TenantRef:
    """行值 → 租户引用（库名基为空回落编码）。

    Args:
        code: 租户编码。
        db_basis: 库名基（可空）。

    Returns:
        TenantRef: 租户引用。
    """
    basis = str(db_basis) if isinstance(db_basis, str) and db_basis else str(code)
    return TenantRef(code=str(code), db_basis=basis)


def _statement():
    """构造租户引用查询语句（`sys_tenant` 左联对照表，均限未软删）。

    Returns:
        Select: 查询语句（列：编码、库名基）。
    """
    from bms_core.models.tenant.tenant import SysTenant  # 惰性：仅读租户注册库时需要
    from bms_core.models.tenant.tenant_database import SysTenantDatabase

    return (
        select(SysTenant.code, SysTenantDatabase.db_basis)
        .outerjoin(
            SysTenantDatabase,
            (SysTenantDatabase.tenant_id == SysTenant.id) & (SysTenantDatabase.deleted_at.is_(None)),
        )
        .where(SysTenant.deleted_at.is_(None))
    )


def tenant_refs_sync(url: str) -> ConcurrentStableList[TenantRef]:
    """同步枚举租户引用（达梦等无异步方言驱动的租户注册库）。

    Args:
        url: 租户注册库连接串。

    Returns:
        ConcurrentStableList[TenantRef]: 租户引用列表（库名基缺对照行回落当前编码）。
    """
    engine: Engine = create_engine(url, poolclass=NullPool)
    try:
        with engine.connect() as connection:
            return ConcurrentStableList(_ref(code, basis) for code, basis in connection.execute(_statement()).all())
    finally:
        engine.dispose()


async def tenant_refs(registry_url: str) -> ConcurrentStableList[TenantRef]:
    """枚举租户引用（租户注册库查询；库名基经对照表；达梦走同步驱动线程）。

    Args:
        registry_url: 租户注册库连接串。

    Returns:
        ConcurrentStableList[TenantRef]: 租户引用列表（按主键序）。
    """
    if make_url(registry_url).get_backend_name() == _DM:
        return await asyncio.to_thread(tenant_refs_sync, registry_url)
    engine = create_async_engine(registry_url, poolclass=NullPool)
    try:
        async with engine.connect() as connection:
            result = await connection.execute(_statement())
            return ConcurrentStableList(_ref(code, basis) for code, basis in result.all())
    finally:
        await engine.dispose()
