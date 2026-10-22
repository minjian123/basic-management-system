"""租户开通编排内核（建库 → 逐链幂等建表 → 批量种子 → 失败清理；14_04 自 `ops.tenant_provisioning` 下沉）。

用法（经 `ops` 同名薄壳，命令与参数不变）：

```bash
cd backend
uv run python -m ops.tenant_provisioning --code acme --dry-run
uv run python -m ops.tenant_provisioning --code acme --password "<初始口令>"
```

- **建库**：复用 `bms_core.db.admin`（MySQL / PostgreSQL 建库、SQLite 建文件、达梦建模式；幂等）；
- **建表**：逐启用服务租户链 `apply_chain_schema`（与 `ops.init_schema` 同一表集派生点；迁移脚本目录当前为空，
  迁移机制保留）；
- **种子**（仅 platform / identity 租户库）：系统参数（含四类审计日志 90 天归档）、三类内置管理员角色与互斥预授
  （`BUILTIN_ADMIN_ROLES`）、初始系统管理员账号（随机口令一次性打印）、默认 IdP 占位（`disabled`）；
- **失败清理**：任一步失败逆序 `drop_database` 已建库并抛出（调用方删除注册行 + 告警）；
- **不做**：写 `sys_tenant` 注册行与模块清单（归 tenant 服务；本模块只负责库侧与种子）。

归属：本模块是**基座机制**（开通编排），供任何服务 / 产品复用；只依赖 `bms_core`，不导入 `ops` 与服务包。
"""

import argparse
import asyncio
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from bms_core.config.seed import seed_configs
from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.config import get_settings
from bms_core.core.exceptions import ConfigError
from bms_core.core.objects import BaseValueObject
from bms_core.db.admin import DatabaseTarget, create_database, drop_database, resolve_target
from bms_core.db.bootstrap import apply_chain_schema
from bms_core.db.engine import EngineFactory
from bms_core.db.keys import build_platform_db_key, build_tenant_db_key
from bms_core.db.migration import DATASOURCE_TENANT, build_chain_name, resolve_chain
from bms_core.services.module_registry import SERVICE_CATALOG, ModuleRecord, ModuleStatus, enabled_service_keys
from bms_core.tenant.seed.platform import seed_platform_rbac
from bms_core.tenant.seed.rbac import seed_rbac
from bms_core.tenant.seed.sso import seed_identity_provider
from bms_core.tenant.seed.user import seed_user

__all__ = [
    "ProvisionOutcome",
    "build_parser",
    "enabled_tenant_services",
    "main",
    "provision_infrastructure",
]

_DEFAULT_ADMIN_USERNAME = "admin"
"""初始系统管理员账号（租户库 `sys_user.username`）。"""

_DEFAULT_ADMIN_NAME = "系统管理员"
"""初始系统管理员显示名。"""


@dataclass(frozen=True)
class ProvisionOutcome(BaseValueObject):
    """开通编排结果（库侧 + 种子）。"""

    db_basis: str
    """库名基。"""

    services: ConcurrentStableList[str] = field(default_factory=lambda: ConcurrentStableList[str]())
    """已建库 / 建表的服务标识（保序）。"""

    created_databases: ConcurrentStableList[str] = field(default_factory=lambda: ConcurrentStableList[str]())
    """本次新建的库键（已存在的不计入）。"""

    seeded: int = 0
    """系统参数种子新增行数。"""

    roles_created: int = 0
    """内置管理员角色新增数。"""

    admin_username: str = _DEFAULT_ADMIN_USERNAME
    """初始管理员账号。"""

    initial_password: str = ""
    """初始口令明文（仅本次返回 / 打印一次；首登强制改密）。"""


def enabled_tenant_services() -> ConcurrentStableList[str]:
    """取需为租户建库的启用服务（平台服务 + 已启用产品模块所属服务）。

    Returns:
        ConcurrentStableList[str]: 服务标识（保序；`platform` 恒在首位）。
    """
    services = ConcurrentStableList(enabled_service_keys())
    for record in _catalog_records():
        if record.service_key and record.status == ModuleStatus.ENABLED and record.service_key not in services:
            services.add(record.service_key)
    return services


def _catalog_records() -> ConcurrentStableList[ModuleRecord]:
    """取服务目录记录（单一来源）。

    Returns:
        ConcurrentStableList[ModuleRecord]: 目录记录。
    """
    return ConcurrentStableList(SERVICE_CATALOG)


def _resolve_urls(db_basis: str, services: ConcurrentStableList[str]) -> ConcurrentStableList[tuple[str, str]]:
    """按库键解析各服务租户库连接串。

    Args:
        db_basis: 库名基。
        services: 服务标识清单。

    Returns:
        ConcurrentStableList[tuple[str, str]]: (服务标识, 连接串)。
    """
    factory = EngineFactory(get_settings(), allow_cross_service=True)
    return ConcurrentStableList(
        (service, factory.resolved_url(build_tenant_db_key(db_basis, service=service))) for service in services
    )


async def _seed_configs(url: str) -> int:
    """向租户库幂等写入系统参数（含归档策略）。

    Args:
        url: 租户库连接串。

    Returns:
        int: 新增行数。
    """
    engine = create_async_engine(url)
    factory: async_sessionmaker[AsyncSession] = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            return await seed_configs(session)
    finally:
        await engine.dispose()


async def provision_infrastructure(
    *,
    db_basis: str,
    initial_password: str = "",
    admin_username: str = _DEFAULT_ADMIN_USERNAME,
    admin_name: str = _DEFAULT_ADMIN_NAME,
    platform: bool = False,
) -> ProvisionOutcome:
    """建库 + 逐链建表 + 批量种子（失败逆序清理已建库）。

    Args:
        db_basis: 库名基（租户编码）。
        initial_password: 初始管理员口令（空串表示随机生成）。
        admin_username: 初始管理员账号。
        admin_name: 初始管理员显示名。
        platform: 是否平台租户（`True` 时播平台 RBAC 而非租户三权管理员）。

    Returns:
        ProvisionOutcome: 编排结果。

    Raises:
        ConfigError: 无启用服务或建库 / 建表 / 种子失败（已清理）。
    """
    services = enabled_tenant_services()
    if not services:
        raise ConfigError("无已启用服务，无法为租户建库")
    urls = _resolve_urls(db_basis, services)
    created: ConcurrentStableList[tuple[str, DatabaseTarget]] = ConcurrentStableList()
    try:
        for service, url in urls:
            target = resolve_target(url)
            if await create_database(target):
                created.add((service, target))
        for service, url in urls:
            chain = resolve_chain(build_chain_name(service, DATASOURCE_TENANT))
            await apply_chain_schema(chain, url, target=f"tenant_{db_basis}")
        seeded = await _seed_configs(dict(urls)["platform"])
        user = await seed_user(
            url=dict(urls)["platform"],
            username=admin_username,
            name=admin_name,
            password=initial_password,
        )
        roles_created = 0
        if platform:
            platform_seed = await seed_platform_rbac(platform_code=db_basis, assign_user=admin_username)
            roles_created = platform_seed.roles_created
        else:
            rbac = await seed_rbac(
                tenant_url=dict(urls)["platform"],
                platform_url=EngineFactory(get_settings(), allow_cross_service=True).resolved_url(
                    build_platform_db_key("platform")
                ),
                assign_user="",
            )
            roles_created = rbac.roles_created
        await seed_identity_provider(dict(urls)["identity"], status="disabled")
        return ProvisionOutcome(
            db_basis=db_basis,
            services=services,
            created_databases=ConcurrentStableList(service for service, _ in created),
            seeded=seeded,
            roles_created=roles_created,
            admin_username=admin_username,
            initial_password=user.password,
        )
    except Exception:
        for _service, target in reversed(list(created)):
            await drop_database(target)
        raise


def build_parser() -> argparse.ArgumentParser:
    """构建命令行解析器。

    Returns:
        argparse.ArgumentParser: 解析器。
    """
    parser = argparse.ArgumentParser(description="租户开通编排（建库 + 建表 + 种子；失败清理）")
    parser.add_argument("--code", required=True, help="租户编码（库名基）")
    parser.add_argument("--password", default="", help="初始管理员口令（缺省随机生成并一次性打印）")
    parser.add_argument("--dry-run", action="store_true", help="仅打印计划（不建连、不建库）")
    return parser


def main(argv: ConcurrentStableList[str] | None = None) -> int:
    """入口。

    Args:
        argv: 命令行参数。

    Returns:
        int: 退出码。
    """
    args = build_parser().parse_args(argv)
    if args.dry_run:
        services = enabled_tenant_services()
        print(f"[tenant_provisioning] 租户 {args.code}：待建库 {len(services)} 个（{'、'.join(services)}）")
        print("[tenant_provisioning] dry-run：不建连、不建库")
        return 0
    try:
        outcome = asyncio.run(provision_infrastructure(db_basis=args.code, initial_password=args.password))
    except Exception as exc:
        print(f"[tenant_provisioning] 失败（已清理已建库）：{type(exc).__name__}: {exc}")
        return 1
    print(
        f"[tenant_provisioning] 完成：服务 {len(outcome.services)} 个、新建库 {len(outcome.created_databases)} 个、"
        f"系统参数 {outcome.seeded} 行、内置角色 {outcome.roles_created} 个"
    )
    if outcome.initial_password:
        print(
            f"[tenant_provisioning] 初始管理员 {outcome.admin_username} 口令"
            f"（仅本次打印，请立即保存并在首登后修改）：{outcome.initial_password}"
        )
    return 0
