"""租户注册仓储（`sys_tenant` 写路径唯一入口；06_03 归租户与配置服务）。

- 只读：`by_code` / `by_domain` / `by_id`（软删除过滤）——供本服务本地租户源与只读契约接口复用；
  库名基 `db_basis` 经对照表 `sys_tenant_database` 取数（`db_basis()`）；
- 写路径：`create` / `update_status`（开通 / 停用）——`create` 同事务写 `sys_tenant` + `sys_tenant_database`
  （开通流程「先写注册 + 对照，再建库 / 迁移」）；本期只落状态变更入口，保证「版本键失效」有调用点。
"""

from datetime import datetime

from sqlalchemy import select

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.objects import BaseFrameworkObject
from bms_core.db.session import DbSession
from bms_tenant.models.tenant import SysTenant
from bms_tenant.models.tenant_database import SysTenantDatabase

__all__ = ["TenantRegistryRepository"]

_ACTIVE_STATUS = "active"
"""启用租户状态取值（与 `sys_tenant.status` 口径一致）。"""


class TenantRegistryRepository(BaseFrameworkObject):
    """租户注册仓储（会话绑定；调用方负责事务边界）。"""

    def __init__(self, session: DbSession) -> None:
        """初始化。

        Args:
            session: 数据库会话（异步会话或达梦同步门面）。
        """
        self._session = session

    async def by_code(self, code: str) -> SysTenant | None:
        """按编码取未软删注册行。

        Args:
            code: 租户编码。

        Returns:
            SysTenant | None: 注册行；未命中返回 None。
        """
        return await self._one(SysTenant.code == code)

    async def by_domain(self, domain: str) -> SysTenant | None:
        """按子域名取未软删注册行。

        Args:
            domain: 子域名。

        Returns:
            SysTenant | None: 注册行；未命中返回 None。
        """
        return await self._one(SysTenant.domain == domain)

    async def by_id(self, tenant_id: int) -> SysTenant | None:
        """按租户主键取未软删注册行。

        Args:
            tenant_id: 租户主键（雪花 id）。

        Returns:
            SysTenant | None: 注册行；未命中返回 None。
        """
        return await self._one(SysTenant.id == tenant_id)

    async def active_rows(self, limit: int = 2) -> ConcurrentStableList[SysTenant]:
        """取启用租户注册行（`status == active` 且未软删；按主键升序、上限 `limit` 条）。

        供免登录链路「唯一启用租户」判个数（上限 2 即可判定唯一 / 不唯一），不取全量。

        Args:
            limit: 返回上限（缺省 2）。

        Returns:
            ConcurrentStableList[SysTenant]: 启用租户注册行（至多 `limit` 条，保持主键升序）。
        """
        statement = (
            select(SysTenant)
            .where(SysTenant.status == _ACTIVE_STATUS, SysTenant.deleted_at.is_(None))
            .order_by(SysTenant.id)
            .limit(limit)
        )
        return ConcurrentStableList((await self._session.execute(statement)).scalars().all())

    async def db_basis(self, tenant_id: int) -> str | None:
        """取租户库名基（对照表 `sys_tenant_database`；未软删）。

        Args:
            tenant_id: 租户主键（雪花 id）。

        Returns:
            str | None: 库名基；缺对照行返回 None（调用方回落当前 code）。
        """
        statement = (
            select(SysTenantDatabase.db_basis)
            .where(SysTenantDatabase.tenant_id == tenant_id, SysTenantDatabase.deleted_at.is_(None))
            .limit(1)
        )
        return (await self._session.execute(statement)).scalar_one_or_none()

    async def create(
        self,
        *,
        code: str,
        name: str,
        domain: str | None,
        db_basis: str | None = None,
        expire_at: datetime | None = None,
    ) -> SysTenant:
        """登记新租户（同事务写 `sys_tenant` + `sys_tenant_database`；幂等由调用方按编码判存）。

        Args:
            code: 租户编码（全小写）。
            name: 租户名称。
            domain: 子域名。
            db_basis: 库名基（缺省取当前 `code`；创建时冻结、后续不随编码变更）。
            expire_at: 到期时间（UTC）。

        Returns:
            SysTenant: 新建注册行。
        """
        row = SysTenant(code=code, name=name, domain=domain, status="active", expire_at=expire_at)
        self._session.add(row)
        await self._session.flush()
        self._session.add(SysTenantDatabase(tenant_id=row.id, db_basis=db_basis or code))
        await self._session.flush()
        return row

    async def update_status(self, row: SysTenant, status: str) -> SysTenant:
        """变更租户状态（停用 / 启用）。

        Args:
            row: 注册行。
            status: 目标状态（`active` / `suspended`）。

        Returns:
            SysTenant: 更新后的注册行。
        """
        row.status = status
        await self._session.flush()
        return row

    async def _one(self, condition: object) -> SysTenant | None:
        """按条件取单行（软删除过滤）。

        Args:
            condition: 查询条件。

        Returns:
            SysTenant | None: 注册行；未命中返回 None。
        """
        statement = select(SysTenant).where(condition, SysTenant.deleted_at.is_(None)).limit(1)  # type: ignore[arg-type]
        return (await self._session.execute(statement)).scalar_one_or_none()
