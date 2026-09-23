"""租户注册仓储（`sys_tenant` 写路径唯一入口；06_03 归租户与配置服务）。

- 只读：`by_code` / `by_domain`（软删除过滤）——供本服务本地租户源与只读契约接口复用；
- 写路径：`create` / `update_status`（开通 / 停用）**由租户管理阶段补全**，本期只落状态变更入口，
  保证「版本键失效」有调用点（写路径与缓存失效同址）。
"""

from datetime import datetime

from sqlalchemy import select

from bms_core.core.base import BaseObject
from bms_core.db.session import DbSession
from bms_tenant.models.tenant import SysTenant

__all__ = ["TenantRegistryRepository"]


class TenantRegistryRepository(BaseObject):
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

    async def create(
        self,
        *,
        code: str,
        name: str,
        domain: str | None,
        db_key: str,
        expire_at: datetime | None = None,
    ) -> SysTenant:
        """登记新租户（幂等由调用方按编码判存；本方法只插入）。

        Args:
            code: 租户编码（全小写）。
            name: 租户名称。
            domain: 子域名。
            db_key: 数据源键。
            expire_at: 到期时间（UTC）。

        Returns:
            SysTenant: 新建注册行。
        """
        row = SysTenant(code=code, name=name, domain=domain, db_key=db_key, status="active", expire_at=expire_at)
        self._session.add(row)
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
