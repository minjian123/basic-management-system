"""租户注册仓储（`sys_tenant` 写路径唯一入口；06_03 归租户与配置服务）。

- 只读：`by_code` / `by_domain` / `by_id`（软删除过滤）——供本服务本地租户源与只读契约接口复用；
  库名基 `db_basis` 经对照表 `sys_tenant_database` 取数（`db_basis()`）；
- 写路径：`create` / `update_status`（开通 / 停用）——`create` 同事务写 `sys_tenant` + `sys_tenant_database`
  （开通流程「先写注册 + 对照，再建库 / 迁移」）；本期只落状态变更入口，保证「版本键失效」有调用点。
"""

from datetime import datetime

from sqlalchemy import delete, func, select

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.objects import BaseFrameworkObject
from bms_core.db.session import DbSession
from bms_tenant.models.tenant import (
    TENANT_KIND_BUSINESS,
    TENANT_KIND_PLATFORM,
    TENANT_STATUS_ACTIVE,
    SysTenant,
)
from bms_tenant.models.tenant_database import SysTenantDatabase

__all__ = ["TenantRegistryRepository"]

_ACTIVE_STATUS = TENANT_STATUS_ACTIVE
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
        """取启用业务租户注册行（`kind = business`、`status == active` 且未软删；主键升序、上限 `limit` 条）。

        供免登录链路「唯一启用租户」判个数（上限 2 即可判定唯一 / 不唯一），不取全量；**平台租户不参与**
        （否则无来源登录会被错误兜底到平台租户）。

        Args:
            limit: 返回上限（缺省 2）。

        Returns:
            ConcurrentStableList[SysTenant]: 启用业务租户注册行（至多 `limit` 条，保持主键升序）。
        """
        statement = (
            select(SysTenant)
            .where(
                SysTenant.kind == TENANT_KIND_BUSINESS,
                SysTenant.status == _ACTIVE_STATUS,
                SysTenant.deleted_at.is_(None),
            )
            .order_by(SysTenant.id)
            .limit(limit)
        )
        return ConcurrentStableList((await self._session.execute(statement)).scalars().all())

    async def page_business(
        self,
        *,
        page: int,
        size: int,
        code: str | None = None,
        name: str | None = None,
        status: str | None = None,
    ) -> tuple[ConcurrentStableList[SysTenant], int]:
        """分页取业务租户（平台租户一律排除）。

        Args:
            page: 页码（从 1 起）。
            size: 每页条数。
            code: 编码模糊筛选（可选）。
            name: 名称模糊筛选（可选）。
            status: 状态精确筛选（可选）。

        Returns:
            tuple[ConcurrentStableList[SysTenant], int]: 当页行与总数。
        """
        conditions = [SysTenant.kind == TENANT_KIND_BUSINESS, SysTenant.deleted_at.is_(None)]
        if code:
            conditions.append(SysTenant.code.contains(code))
        if name:
            conditions.append(SysTenant.name.contains(name))
        if status:
            conditions.append(SysTenant.status == status)
        total = (
            await self._session.execute(select(func.count()).select_from(SysTenant).where(*conditions))
        ).scalar_one()
        statement = (
            select(SysTenant)
            .where(*conditions)
            .order_by(SysTenant.created_at.desc(), SysTenant.id.desc())
            .offset((page - 1) * size)
            .limit(size)
        )
        rows = ConcurrentStableList((await self._session.execute(statement)).scalars().all())
        return rows, int(total)

    async def platform_row(self) -> SysTenant | None:
        """取平台租户注册行（`kind = platform` 且未软删）。

        Returns:
            SysTenant | None: 平台租户行；未创建返回 None。
        """
        return await self._one(SysTenant.kind == TENANT_KIND_PLATFORM)

    async def domain_taken(self, domain: str, *, exclude_id: int | None = None) -> bool:
        """判定域名是否已被其他未删租户占用。

        Args:
            domain: 子域名。
            exclude_id: 排除的租户主键（更新场景）。

        Returns:
            bool: 已占用为 True。
        """
        conditions = [SysTenant.domain == domain, SysTenant.deleted_at.is_(None)]
        if exclude_id is not None:
            conditions.append(SysTenant.id != exclude_id)
        statement = select(func.count()).select_from(SysTenant).where(*conditions)
        return int((await self._session.execute(statement)).scalar_one()) > 0

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
        kind: str = TENANT_KIND_BUSINESS,
        status: str = TENANT_STATUS_ACTIVE,
    ) -> SysTenant:
        """登记新租户（同事务写 `sys_tenant` + `sys_tenant_database`；幂等由调用方按编码判存）。

        Args:
            code: 租户编码（全小写）。
            name: 租户名称。
            domain: 子域名。
            db_basis: 库名基（缺省取当前 `code`；创建时冻结、后续不随编码变更）。
            expire_at: 到期时间（UTC）。
            kind: 租户类型（`business` 缺省 / `platform` 平台租户）。
            status: 初始状态（开通流程先落 `provisioning`，成功后置 `active`）。

        Returns:
            SysTenant: 新建注册行。
        """
        row = SysTenant(code=code, name=name, domain=domain, kind=kind, status=status, expire_at=expire_at)
        self._session.add(row)
        await self._session.flush()
        self._session.add(SysTenantDatabase(tenant_id=row.id, db_basis=db_basis or code))
        await self._session.flush()
        return row

    async def update_fields(
        self,
        row: SysTenant,
        *,
        name: str | None = None,
        domain: str | None = None,
        expire_at: datetime | None = None,
    ) -> SysTenant:
        """更新租户可改字段（名称 / 域名 / 到期时间；`code` 不可改）。

        Args:
            row: 注册行。
            name: 新名称（None 不改）。
            domain: 新子域名（None 不改）。
            expire_at: 新到期时间（None 不改）。

        Returns:
            SysTenant: 更新后的注册行。
        """
        if name is not None:
            row.name = name
        if domain is not None:
            row.domain = domain
        if expire_at is not None:
            row.expire_at = expire_at
        await self._session.flush()
        return row

    async def delete_provisioning(self, tenant_id: int) -> None:
        """物理删除开通失败的注册行与库名对照（失败清理用；不留半开通租户）。

        Args:
            tenant_id: 租户主键。
        """
        await self._session.execute(delete(SysTenantDatabase).where(SysTenantDatabase.tenant_id == tenant_id))
        await self._session.execute(delete(SysTenant).where(SysTenant.id == tenant_id))

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
