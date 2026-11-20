"""租户管理面用例的共享助手：临时库接线与租户造数。

为什么放在 `tests_support` 而不是用例文件里：`base test-db-isolation` 只判 `test_*.py`
（`tests_support/` 是共享测试基座，建库职责由规则段显式声明）。这些助手**只服务
「建库即被测 / 自带独占库」的 `own_db` 文件**（如 `test_tenant_delete_lifecycle`），
单库叠加口径下的用例应改用共享平台库（见 `tests_support/tenant_base.py`）。
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import cast

from fastapi import FastAPI
from sqlalchemy import Table
from sqlalchemy.ext.asyncio import AsyncSession

from bms_core.api.deps import get_platform_read_db, get_platform_write_db, get_service_client
from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.models.base import Base
from bms_core.models.outbox import SysOutbox
from bms_core.models.tenant.tenant import SysTenant
from bms_core.models.tenant.tenant_database import SysTenantDatabase
from bms_core.models.tenant.tenant_module import SysTenantModule
from bms_core.models.tenant.tenant_quota import SysTenantQuota
from bms_core.testing.transaction import GatedSessionMaker, gated_sessionmaker
from tests_support.shared_access import shared_engine, shared_session, shared_window

__all__ = ("TENANT_CATALOG", "TENANT_TABLES", "Resp", "StubClient", "override_platform", "seed_tenant")

TENANT_TABLES: ConcurrentStableList[Table] = ConcurrentStableList(
    (
        cast("Table", SysTenant.__table__),
        cast("Table", SysTenantDatabase.__table__),
        cast("Table", SysTenantModule.__table__),
        cast("Table", SysTenantQuota.__table__),
        cast("Table", SysOutbox.__table__),
    )
)
"""租户管理面涉及的表（幂等建表集）。"""


TENANT_CATALOG: ConcurrentStableList[ConcurrentStableDict[str, object]] = ConcurrentStableList(
    (
        ConcurrentStableDict(
            {
                "module_key": "sys",
                "name": "平台地基",
                "table_prefix": "sys_",
                "errcode_segment": "01",
                "service_group": "foundation",
                "status": "enabled",
            }
        ),
        ConcurrentStableDict(
            {
                "module_key": "tenant",
                "name": "租户服务",
                "table_prefix": "tenant_",
                "errcode_segment": None,
                "service_group": "foundation",
                "status": "enabled",
            }
        ),
        ConcurrentStableDict(
            {
                "module_key": "pur",
                "name": "采购",
                "table_prefix": "pur_",
                "errcode_segment": "10",
                "service_group": "product",
                "status": "enabled",
            }
        ),
        ConcurrentStableDict(
            {
                "module_key": "pay",
                "name": "收付款",
                "table_prefix": "pay_",
                "errcode_segment": "11",
                "service_group": "product",
                "status": "planned",
            }
        ),
    )
)
"""租户模块目录替身数据（模块键 / 名称 / 表前缀 / 错误码段位 / 分组 / 状态）。"""


class Resp:
    """服务间响应替身。"""

    def __init__(self, payload: object, status_code: int = 200) -> None:
        """初始化。

        Args:
            payload: 响应载荷。
            status_code: HTTP 状态码。
        """
        self.status_code = status_code
        self._payload = payload

    def payload(self) -> object:
        """取载荷。

        Returns:
            object: 响应载荷。
        """
        return self._payload


class StubClient:
    """服务间客户端替身：目录快照 / 会话撤销 / 配额。"""

    def __init__(self) -> None:
        """初始化调用记录。"""
        self.paths: ConcurrentStableList[str] = ConcurrentStableList()
        self.revoked_calls = 0

    async def call(self, request: object) -> Resp:
        """按请求路径返回替身响应。

        Args:
            request: 服务间请求（读其 `path`）。

        Returns:
            Resp: 替身响应。
        """
        path = str(getattr(request, "path", ""))
        self.paths.append(path)
        if path.endswith("/modules/snapshot"):
            return Resp({"code": 0, "data": [dict(item) for item in TENANT_CATALOG]})
        if path.endswith("/sessions/revoke-tenant"):
            self.revoked_calls += 1
            return Resp({"code": 0, "data": {"revoked": 2}})
        return Resp({"code": 0, "data": {"allowed": True, "used_value": 0, "limit_value": None}})


async def override_platform(app: FastAPI, url: str) -> StubClient:
    """覆盖平台库读 / 写会话依赖并返回服务间客户端替身。

    Args:
        app: 应用实例。
        url: 平台库连接串（调用方自建库时使用）。

    Returns:
        StubClient: 服务间客户端替身。
    """
    engine = shared_engine(url)
    try:
        async with shared_window(engine), engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all, tables=list(TENANT_TABLES), checkfirst=True)
    finally:
        await engine.dispose()
    factory: GatedSessionMaker = gated_sessionmaker(shared_engine(url), read_only=False)

    async def _session() -> AsyncIterator[AsyncSession]:
        async with factory() as session:
            yield session

    client = StubClient()
    app.dependency_overrides[get_platform_read_db] = _session
    app.dependency_overrides[get_platform_write_db] = _session
    app.dependency_overrides[get_service_client] = lambda: client
    return client


async def seed_tenant(
    url: str,
    *,
    code: str,
    name: str = "租户",
    domain: str | None = None,
    kind: str = "business",
    status: str = "active",
    modules: ConcurrentStableList[tuple[str, str]] | None = None,
) -> int:
    """向指定连接串写入租户（含库名对照 / 模块），返回主键。

    Args:
        url: 平台库连接串。
        code: 租户编码。
        name: 租户名称。
        domain: 子域名。
        kind: 租户类型。
        status: 状态。
        modules: 模块（标识 / 状态）。

    Returns:
        int: 租户主键。
    """
    async with shared_session(url, read_only=False) as session:
        row = SysTenant(code=code, name=name, domain=domain, kind=kind, status=status)
        session.add(row)
        await session.flush()
        tenant_id = int(row.id)
        session.add(SysTenantDatabase(tenant_id=tenant_id, db_basis=code))
        for module_key, module_status in modules or ConcurrentStableList[tuple[str, str]]():
            session.add(SysTenantModule(tenant_id=tenant_id, module_key=module_key, status=module_status))
        await session.commit()
    return tenant_id
