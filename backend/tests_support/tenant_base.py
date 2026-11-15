"""租户服务用例的**共享基础数据集**（2026-11-15 单库叠加收口）。

背景：`test_tenant_source`（租户源）与 `test_tenant_admin`（租户管理面）原本各建一份
「每用例一份临时平台库 + 固定租户集合」的独占库。单库叠加口径下改为：

- 库用**共享平台库**：基础租户集合**提交入库**，即「业务里已有的数据」，两个文件共用同一份；
- 新用例按需自造的行仍走命名空间 / 自我清理，断言只看自造行或相对增量；
- 不再使用未提交事务——`single_active()` 的 0 / 1 态属全局口径，共享库上人造这种态等于篡改
  业务数据，改为在用例里用替身验证分支（见 `test_tenant_source`）。

口径出处：《测试规范》「测试库与数据隔离」。
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.models.tenant.tenant import SysTenant
from bms_core.models.tenant.tenant_database import SysTenantDatabase
from bms_core.models.tenant.tenant_module import SysTenantModule

__all__ = ("BASE_TENANTS", "TenantBase", "tenant_base")


@dataclass(frozen=True)
class _TenantSpec:
    """基础租户集合的一条（提交入库的「业务已有数据」）。"""

    code: str
    name: str
    domain: str | None = None
    db_key: str | None = None
    db_basis: str | None = None
    status: str = "active"
    soft_deleted: bool = False


BASE_TENANTS: tuple[_TenantSpec, ...] = (
    _TenantSpec(code="demo", name="演示租户", domain="demo.bms.example.com", db_key="tenant_demo", db_basis="demo"),
    _TenantSpec(code="acme", name="示例租户", domain="acme.bms.example.com", db_key="tenant_acme"),
    _TenantSpec(
        code="sosp",
        name="停用租户",
        domain="sosp.bms.example.com",
        db_key="tenant_sosp",
        status="suspended",
    ),
    _TenantSpec(code="renamed", name="改名租户", domain="renamed.bms.example.com", db_basis="orig"),
    _TenantSpec(code="gone", name="已删除租户", db_key="tenant_gone", soft_deleted=True),
)
"""基础租户集合：两个文件共用的「业务已有数据」（幂等写入，会话内只造一次）。"""


class TenantBase:
    """共享平台库上的基础租户数据集（已提交，等同业务既有数据）。

    用法：用例通过 `tenant_base` 夹具拿到本对象；共用基础集合由 `ensure_base()` 幂等保证，
    用例自造的行用 `seed()` / `soft_delete()` / `delete_row()` 并自行收尾。
    """

    def __init__(self, url: str, session: AsyncSession) -> None:
        """初始化。

        Args:
            url: 共享平台库连接串。
            session: 共享平台库会话（用例自造行写它，需要时自行提交）。
        """
        self.url = url
        self.session = session

    async def ensure_base(self) -> None:
        """幂等写入基础租户集合（已存在的编码跳过；并发撞唯一约束时以后落库者为准）。"""
        for spec in BASE_TENANTS:
            existing = (
                (await self.session.execute(select(SysTenant).where(SysTenant.code == spec.code))).scalars().first()
            )
            if existing is not None:
                continue
            try:
                async with self.session.begin_nested():
                    row = SysTenant(
                        code=spec.code,
                        name=spec.name,
                        domain=spec.domain,
                        status=spec.status,
                        **({"db_key": spec.db_key} if spec.db_key is not None else {}),
                    )
                    self.session.add(row)
                    await self.session.flush()
                    if spec.db_basis is not None:
                        self.session.add(SysTenantDatabase(tenant_id=int(row.id), db_basis=spec.db_basis))
                    if spec.soft_deleted:
                        row.soft_delete()
                    await self.session.flush()
            except IntegrityError:
                continue
        await self.session.commit()

    async def seed(
        self,
        *,
        code: str,
        name: str = "租户",
        domain: str | None = None,
        db_key: str | None = None,
        db_basis: str | None = None,
        kind: str = "business",
        status: str = "active",
        modules: ConcurrentStableList[tuple[str, str]] | None = None,
    ) -> int:
        """写入一条**本用例自造**的租户（含库名对照 / 模块），返回主键。

        Args:
            code: 租户编码。
            name: 租户名称。
            domain: 子域名。
            db_key: 显式库键（None 表示按 code 派生）。
            db_basis: 库名基（None 表示不写对照行）。
            kind: 租户类型（business / platform）。
            status: 状态（active / suspended）。
            modules: 模块（标识 / 状态）。

        Returns:
            int: 租户主键。
        """
        row = SysTenant(
            code=code,
            name=name,
            domain=domain,
            kind=kind,
            status=status,
            **({"db_key": db_key} if db_key is not None else {}),
        )
        self.session.add(row)
        await self.session.flush()
        tenant_id = int(row.id)
        if db_basis is not None:
            self.session.add(SysTenantDatabase(tenant_id=tenant_id, db_basis=db_basis))
        for module_key, module_status in modules or ConcurrentStableList[tuple[str, str]]():
            self.session.add(SysTenantModule(tenant_id=tenant_id, module_key=module_key, status=module_status))
        await self.session.flush()
        return tenant_id

    async def soft_delete(self, *codes: str) -> None:
        """软删除指定编码的租户行（本用例自造行的收尾 / 构造态）。

        Args:
            *codes: 租户编码。
        """
        for code in codes:
            row = (await self.session.execute(select(SysTenant).where(SysTenant.code == code))).scalars().first()
            if row is not None:
                row.soft_delete()
        await self.session.flush()

    async def delete_row(self, code: str) -> None:
        """物理删除指定编码的租户行（模拟「行被外部删除」）。

        Args:
            code: 租户编码。
        """
        row = (await self.session.execute(select(SysTenant).where(SysTenant.code == code))).scalars().first()
        if row is not None:
            await self.session.delete(row)
            await self.session.flush()

    async def cleanup(self) -> None:
        """清掉本会话自造的行（**仅供调试**：不作为用例收尾，会误删并行用例的行）。"""
        base_codes = {spec.code for spec in BASE_TENANTS}
        rows = (await self.session.execute(select(SysTenant))).scalars().all()
        for row in rows:
            if row.code in base_codes:
                continue
            await self.session.delete(row)
        await self.session.commit()


@pytest.fixture(scope="session")
async def tenant_base(shared_platform_db_url: str) -> AsyncIterator[TenantBase]:
    """共享平台库上的基础租户数据集（会话级；已提交，等同业务既有数据）。

    会话级（而非每用例）原因：基础集合是「业务已有数据」，只该造一次；用例自造的行按命名空间
    编码写入、断言按前缀收敛，互不干扰——收尾也**不能**按「非基础行」清理，那会误删并行用例
    正在使用的行。

    Args:
        shared_platform_db_url: 共享平台库连接串。

    Yields:
        TenantBase: 基础数据集句柄。
    """
    engine = create_async_engine(shared_platform_db_url)
    factory: async_sessionmaker[AsyncSession] = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            base = TenantBase(shared_platform_db_url, session)
            await base.ensure_base()
            yield base
    finally:
        await engine.dispose()
