"""共享测试库准备集（04-6-2）：`platform` / `tenant` 两个逻辑数据源的建库与播种单源实现。

为什么落 `tests_support` 而不落 `bms_core`：准备集要拼「已导入模型的建表集 + 业务种子」，
种子与建表口径属后端工程层（`backend/`）而非基座库；放进 `bms_core` 会让下层库反向依赖
上层，且产品仓（mdm）无 `ops` 无法复用。产品仓以同名薄壳转发到 `bms_core` 侧能力。

口径（《测试规范》「测试数据」节，需求 04-6）：

- 每个逻辑数据源**只有一套库**，全 worker 共用，用例叠加；
- 准备集只在抢到初始化锁的 worker 上执行一次，其余 worker 等 `.ready`；
- 种子固定主键（`demo` → 1001 / `acme` → 2002）是平台全局基础数据，用例只读引用、不得改主键；
- `.ready` 版本戳由本模块源码摘要派生——准备内容一改即自动重建，避免「改了种子但旧库沿用」。
"""

from __future__ import annotations

import asyncio

from sqlalchemy import MetaData, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from bms_core.config.seed import seed_configs
from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.exceptions import ConfigError
from bms_core.db.bootstrap import domains_metadata
from bms_core.db.migration import DATASOURCE_TENANT, known_domains
from bms_core.models.base import SQLITE_PADDED_WIDTH, Base
from bms_core.registry.products import load_product_manifests
from bms_core.tenant.seed.module import seed_modules
from bms_core.tenant.seed.tenant import seed_tenants

SEED_TENANT_IDS: tuple[tuple[str, int], ...] = (("demo", 1001), ("acme", 2002))
"""种子租户编码 → 固定主键（平台全局基础数据；测试租户源与令牌租户位同口径）。"""


def prepare_platform(url: str) -> None:
    """准备平台库：种子租户 → 主键对齐 → 服务目录与产品档案。

    **产品清单先固定为本仓清单**：服务目录种子取「平台常量 + 已装载产品清单」合并视图，
    若沿用当前进程里因前序用例注册/复位产生的状态，准备内容会随执行顺序漂移
    （同一会话换一个 worker 先跑到就换一套种子），违背「并行与串行结果一致」。

    幂等：重复执行行数增量为 0。

    Args:
        url: 共享平台库连接串。
    """
    asyncio.run(_prepare_platform(url))


async def _prepare_platform(url: str) -> None:
    """平台库准备集的异步实现（见 `prepare_platform`）。

    **建表集为已导入模型并集**（`Base.metadata.create_all`，幂等）：单库化后全 worker 共用一份库，
    建表若留给用例各自 `create_all`，多 worker 并发执行会撞「table already exists」。
    这里一次性建全，用例侧的 `create_all(checkfirst=True)` 只做存在性确认。

    Args:
        url: 共享平台库连接串。
    """
    engine = create_async_engine(url, poolclass=NullPool)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        await _enable_concurrency(engine)
    finally:
        await engine.dispose()
    load_product_manifests(ConcurrentStableList())
    await seed_tenants(url)
    await _align_seed_tenant_ids(url)
    await seed_modules(url)


async def _align_seed_tenant_ids(url: str) -> None:
    """把种子租户主键对齐到测试租户源口径（`demo` / `acme`；含库名对照行）。

    用户↔租户可达关系表 `sys_user_tenant` 按雪花租户主键与 `sys_tenant` 同库 join，
    主键须与令牌租户位一致才能命中。幂等：已对齐时两次 UPDATE 均写回原值。

    Args:
        url: 共享平台库连接串。
    """
    engine = create_async_engine(url, poolclass=NullPool)
    try:
        async with engine.begin() as connection:
            for code, tenant_id in SEED_TENANT_IDS:
                padded = str(tenant_id).zfill(SQLITE_PADDED_WIDTH)
                await connection.execute(
                    text(
                        "UPDATE sys_tenant_database SET tenant_id = :new WHERE tenant_id = "
                        "(SELECT id FROM sys_tenant WHERE code = :code AND deleted_at IS NULL)"
                    ),
                    {"new": padded, "code": code},
                )
                await connection.execute(
                    text("UPDATE sys_tenant SET id = :new WHERE code = :code AND deleted_at IS NULL"),
                    {"new": padded, "code": code},
                )
    finally:
        await engine.dispose()


async def prepare_platform_async(url: str) -> None:
    """平台库准备集的异步入口（供异步夹具调用，避免在事件循环里 `asyncio.run`）。

    Args:
        url: 共享平台库连接串。
    """
    await _prepare_platform(url)


async def prepare_tenant_async(url: str) -> None:
    """租户库准备集的异步入口（供异步夹具调用）。

    Args:
        url: 共享租户库连接串。
    """
    await _prepare_tenant(url)


def prepare_tenant(url: str) -> None:
    """准备租户库：租户侧建表集（各业务域并集 + 基础设施表）→ 系统参数种子。

    建表集经 `domains_metadata` 按「域 × 数据源」派生（与启动期自动建表同一派生点），
    不把平台库表建进租户库，避免「写错数据源」的用例失去判别能力。

    Args:
        url: 共享租户库连接串。
    """
    asyncio.run(_prepare_tenant(url))


async def _prepare_tenant(url: str) -> None:
    """租户库准备集的异步实现（见 `prepare_tenant`）。

    Args:
        url: 共享租户库连接串。
    """
    metadata = _tenant_metadata()
    engine = create_async_engine(url, poolclass=NullPool)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(metadata.create_all)
        await _enable_concurrency(engine)
    finally:
        await engine.dispose()
    await _seed_configs(url)


async def _enable_concurrency(engine: AsyncEngine) -> None:
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


def _tenant_metadata() -> MetaData:
    """租户库建表集元数据（域并集 + 基础设施表）。

    域布局缺失时（脚手架 / 未登记单元）回落到全模型并集并打印提示——宁可多建表，
    也不让准备集静默少建表后由用例在运行期报「no such table」。

    Returns:
        MetaData: 建表集元数据。
    """
    try:
        return domains_metadata(known_domains(), DATASOURCE_TENANT)
    except ConfigError as exc:
        print(f"[shared_db] 域布局不可用，租户库回落到全模型建表：{type(exc).__name__}: {exc}")
        return Base.metadata


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
