"""共享测试库准备集（通用实现）：`platform` / `tenant` 两个逻辑数据源的建库与播种。

**为什么在基座**（2026-11-04 拍板）：准备集只依赖 `bms_core` 自身（建表派生点 + 种子 + 租户主键对齐），
不含任何服务层的业务种子；下沉后平台仓与各产品仓（mdm / msg）共用同一份实现，仓内只留薄壳声明
「本产品还要导入哪些模型模块 / 用哪些种子主键」，不再各复制一套。

口径（《测试规范》「测试数据」节，需求 04-6）：

- 每个逻辑数据源**只有一套库**，全 worker 共用，用例叠加；
- 准备集只在抢到初始化锁的 worker 上执行一次，其余 worker 等 `.ready`（锁与版本戳在
  `bms_core.testing.fixtures::ensure_shared_db`，本模块只提供「建什么、播什么」）；
- 种子固定主键（`demo` → 1001 / `acme` → 2002）是平台全局基础数据，用例只读引用、不得改主键；
- 幂等：重复执行行数增量为 0。

调用方式：各仓 `backend/tests_support/shared_db.py` 转发到本模块并在 `prepare` 夹具里传入参数，
版本戳由薄壳源码摘要派生（准备内容一改即重建）。
"""

from __future__ import annotations

import asyncio
import importlib
from collections.abc import Iterable

from sqlalchemy import MetaData, select, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from bms_core.config.seed import seed_configs
from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.exceptions import ConfigError
from bms_core.db.bootstrap import domains_metadata
from bms_core.db.migration import BASE_MODEL_MODULES, COMMON_MODEL_MODULES, DATASOURCE_TENANT, known_domains
from bms_core.models.base import Base
from bms_core.tenant.seed.tenant import seed_tenants

__all__ = [
    "SEED_TENANT_IDS",
    "align_seed_tenant_ids",
    "default_model_modules",
    "prepare_platform",
    "prepare_platform_async",
    "prepare_tenant",
    "prepare_tenant_async",
]

SEED_TENANT_IDS: ConcurrentStableList[tuple[str, int]] = ConcurrentStableList((("demo", 1001), ("acme", 2002)))
"""种子租户编码 → 固定主键（平台全局基础数据；测试租户源与令牌租户位同口径）。"""


def default_model_modules() -> ConcurrentStableList[str]:
    """平台库建表所需的基座共享模型模块（全量共享模型 + 基座基础设施模型）。

    与启动期自动建表的模型面同源：`COMMON_MODEL_MODULES`（归属 / 发件箱 / 系统参数 / 查询方案 +
    平台 / 身份 / 租户三条子包）+ `BASE_MODEL_MODULES`（作业记录）。产品仓在此基础上追加自有模型。

    Returns:
        ConcurrentStableList[str]: 模型模块清单（插入序）。
    """
    modules: ConcurrentStableList[str] = ConcurrentStableList(COMMON_MODEL_MODULES)
    modules.update(BASE_MODEL_MODULES)
    return modules


def prepare_platform(
    url: str,
    *,
    model_modules: Iterable[str] = (),
    seed_tenant_ids: Iterable[tuple[str, int]] = SEED_TENANT_IDS,
    seed_catalog: bool = False,
) -> None:
    """准备平台库：导入模型 → 建表 → 种子租户 → 主键对齐 →（可选）服务目录种子。

    幂等：重复执行行数增量为 0。

    Args:
        url: 共享平台库连接串。
        model_modules: 本仓额外模型模块（产品仓传自有 `models` 包清单；平台仓不传）。
        seed_tenant_ids: 需要固定主键的种子租户（编码 / 主键）；传空即不做租户种子与对齐。
        seed_catalog: 是否种服务目录与产品档案（平台仓 True；产品仓平台库无此要求，False）。
    """
    asyncio.run(
        prepare_platform_async(
            url,
            model_modules=model_modules,
            seed_tenant_ids=seed_tenant_ids,
            seed_catalog=seed_catalog,
        )
    )


async def prepare_platform_async(
    url: str,
    *,
    model_modules: Iterable[str] = (),
    seed_tenant_ids: Iterable[tuple[str, int]] = SEED_TENANT_IDS,
    seed_catalog: bool = False,
) -> None:
    """平台库准备集的异步实现（见 `prepare_platform`）。

    **建表集为已导入模型并集**（`Base.metadata.create_all`，幂等）：单库化后全 worker 共用一份库，
    建表若留给用例各自 `create_all`，多 worker 并发执行会撞「table already exists」。
    这里一次性建全，用例侧的 `create_all(checkfirst=True)` 只做存在性确认。

    Args:
        url: 共享平台库连接串。
        model_modules: 本仓额外模型模块。
        seed_tenant_ids: 需要固定主键的种子租户。
        seed_catalog: 是否种服务目录与产品档案。
    """
    modules: ConcurrentStableList[str] = default_model_modules()
    modules.update(model_modules)
    for module in modules:
        importlib.import_module(module)
    await create_tables(url, Base.metadata)
    targets = tuple(seed_tenant_ids)
    if targets:
        await seed_tenants(url)
        await align_seed_tenant_ids(url, targets)
    if seed_catalog:
        await _seed_catalog(url)


def prepare_tenant(
    url: str,
    *,
    domains: Iterable[str] | None = None,
    model_modules: Iterable[str] = (),
) -> None:
    """准备租户库：租户侧建表集（各业务域并集 + 基础设施表）→ 系统参数种子。

    建表集经 `domains_metadata` 按「域 × 数据源」派生（与启动期自动建表同一派生点），
    不把平台库表建进租户库，避免「写错数据源」的用例失去判别能力。

    Args:
        url: 共享租户库连接串。
        domains: 建表集的业务域集合（产品仓传自有域；None 取本仓已知域）。
        model_modules: 本仓额外模型模块（域派生取不到时兜底建表用）。
    """
    asyncio.run(prepare_tenant_async(url, domains=domains, model_modules=model_modules))


async def prepare_tenant_async(
    url: str,
    *,
    domains: Iterable[str] | None = None,
    model_modules: Iterable[str] = (),
) -> None:
    """租户库准备集的异步实现（见 `prepare_tenant`）。

    Args:
        url: 共享租户库连接串。
        domains: 建表集的业务域集合（None 取本仓已知域）。
        model_modules: 本仓额外模型模块。
    """
    for module in model_modules:
        importlib.import_module(module)
    await create_tables(url, tenant_metadata(domains))
    await _seed_configs(url)


async def create_tables(url: str, metadata: MetaData) -> None:
    """幂等建表并设置写锁等待上限（`busy_timeout`）。

    Args:
        url: 目标库连接串。
        metadata: 建表集元数据。
    """
    engine = create_async_engine(url, poolclass=NullPool)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(metadata.create_all)
        await enable_concurrency(engine)
    finally:
        await engine.dispose()


async def enable_concurrency(engine: AsyncEngine) -> None:
    """设置写锁等待上限（`busy_timeout`）。

    单库叠加下多 worker 并发写同一份 SQLite 库，「写-写」必然短暂互斥：默认等待 5s、且只会
    在获取锁时等待，调用方不重试就直接报 `database is locked`。这里把等待上限抬到 30s
    （与共享引擎夹具的驱动侧 `timeout` 同值），把偶发冲突退化为短等待
    （《测试规范》13「并行与隔离」）。

    为什么不用 WAL：WAL 下「先读后写」的事务取快照后升级写会立即 `SQLITE_BUSY_SNAPSHOT`
    （**不等待**），对「回滚会话里读-改-写」的用例反而更容易失败。

    Args:
        engine: 共享库引擎。
    """
    autocommit = engine.execution_options(isolation_level="AUTOCOMMIT")
    try:
        async with autocommit.connect() as connection:
            await connection.exec_driver_sql("PRAGMA busy_timeout=30000")
    finally:
        await autocommit.dispose()


def tenant_metadata(domains: Iterable[str] | None = None) -> MetaData:
    """租户库建表集元数据（域并集 + 基础设施表）。

    域布局缺失时（脚手架 / 未登记单元）回落到全模型并集并打印提示——宁可多建表，
    也不让准备集静默少建表后由用例在运行期报「no such table」。

    Args:
        domains: 业务域集合（None 取本仓已知域）。

    Returns:
        MetaData: 建表集元数据。
    """
    resolved = ConcurrentStableList(domains) if domains is not None else known_domains()
    try:
        return domains_metadata(resolved, DATASOURCE_TENANT)
    except ConfigError as exc:
        print(f"[shared_db] 域布局不可用，租户库回落到全模型建表：{type(exc).__name__}: {exc}")
        return Base.metadata


async def align_seed_tenant_ids(url: str, seed_tenant_ids: Iterable[tuple[str, int]] = SEED_TENANT_IDS) -> None:
    """把种子租户主键对齐到测试租户源口径（含库名对照行）。

    用户↔租户可达关系表 `sys_user_tenant` 按雪花租户主键与 `sys_tenant` 同库 join，
    主键须与令牌租户位一致才能命中。幂等：已对齐时写回原值。

    **走 ORM 而非原生 SQL**：`update()` 经 `SnowflakeId` 统一处理 SQLite 的 38 位补零，
    且不越过服务边界直接拼表名（跨库写硬禁，无例外）；只更新测试库的种子行，不产生业务写。

    Args:
        url: 共享平台库连接串。
        seed_tenant_ids: 需要对齐的种子租户（编码 / 主键）。
    """
    targets = tuple(seed_tenant_ids)
    if not targets:
        return
    from bms_core.models.tenant.tenant import SysTenant
    from bms_core.models.tenant.tenant_database import SysTenantDatabase

    engine = create_async_engine(url, poolclass=NullPool)
    factory: async_sessionmaker[AsyncSession] = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            for code, tenant_id in targets:
                current = await session.scalar(select(SysTenant.id).where(SysTenant.code == code))
                if current is None:
                    continue
                await session.execute(
                    update(SysTenantDatabase).where(SysTenantDatabase.tenant_id == current).values(tenant_id=tenant_id)
                )
                await session.execute(update(SysTenant).where(SysTenant.code == code).values(id=tenant_id))
            await session.commit()
    finally:
        await engine.dispose()


async def _seed_catalog(url: str) -> None:
    """种服务目录与产品档案（平台仓专用；幂等）。

    Args:
        url: 共享平台库连接串。
    """
    from bms_core.tenant.seed.module import seed_modules

    await seed_modules(url)


async def _seed_configs(url: str) -> None:
    """写入平台默认参数（幂等）。

    Args:
        url: 共享租户库连接串。
    """
    engine = create_async_engine(url, poolclass=NullPool)
    factory: async_sessionmaker[AsyncSession] = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            await seed_configs(session)
            await session.commit()
    finally:
        await engine.dispose()
