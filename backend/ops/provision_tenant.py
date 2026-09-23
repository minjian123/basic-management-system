"""按「服务 × 租户」建库（平台服务库 + 服务租户库；幂等，**不做迁移**）（06_01）。

用法：

```bash
cd backend
uv run python -m ops.provision_tenant --code demo --dry-run            # 计划预演（不建连）
uv run python -m ops.provision_tenant --code demo --code acme          # 全部启用服务 × 两租户
uv run python -m ops.provision_tenant --all-tenants                    # 租户取注册库 active 全集
uv run python -m ops.provision_tenant --service platform --code demo   # 仅指定服务
uv run python -m ops.provision_tenant --code demo --skip-platform      # 只建服务租户库
uv run python -m ops.provision_tenant --code demo \
    --admin-url "mysql+aiomysql://root:pass@host:3306"                 # 建库用管理连接串
uv run python -m ops.provision_tenant --code demo \
    --schema BMS_PROVISION                                             # 达梦：以模式为库级单位
```

- **服务维度**：`SERVICE_CATALOG` 中 `service_key` 非空且 `status = enabled` 的服务
  （当前 9 个：platform / identity / tenant / org / file / notification / search / ai / report）；
  `--service` 可显式指定（须为已登记服务标识）；
- **库命名（单一来源 `bms_core/db/keys.py`）**：平台服务库 `bms_{service}`（键 `platform_{service}`）、
  服务租户库 `bms_{service}_{tenant}`（键 `tenant_{service}_{code}`）；连接串经各自
  `url_template` 解析（空模板回落 `[database.{platform,tenants}].url`）；
- **租户维度**：`--code`（可重复）显式指定，或 `--all-tenants` 从**租户注册库**
  （键 `platform_tenant`）读未软删租户编码（要求该库已建库 + 迁移 + 种子）；
- **幂等**：`create_database` 命中已存在即跳过（不重建、不清空）；重复执行全为「已存在（跳过）」；
- **不做迁移**：库结构由 Alembic 迁移或（SQLite 开发库）启动期自动建表负责；
  遍历「服务 × 租户」的批量迁移编排归 06_02；
- 达梦无 `CREATE DATABASE`：以**模式**为库级隔离单位（`--schema` 指定模式名）。
"""

import argparse
import asyncio
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import create_engine, select
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from bms_core.core.base import BaseObject
from bms_core.core.config import get_settings
from bms_core.core.exceptions import ConfigError
from bms_core.db.admin import create_database, resolve_target
from bms_core.db.engine import EngineFactory
from bms_core.db.keys import (
    DB_KIND_PLATFORM,
    DB_KIND_TENANT,
    build_platform_db_key,
    build_tenant_db_key,
    database_name,
    parse_db_key,
)
from bms_core.db.tenant_source import TENANT_SERVICE_KEY
from bms_core.services.module_registry import enabled_service_keys
from bms_core.services.table_registry import known_service_keys
from bms_tenant.models.tenant import SysTenant

_DM = "dm"


@dataclass(frozen=True)
class ProvisionTask(BaseObject):
    """单个建库任务（库类别 / 服务 / 租户 / 库键 / 连接串）。"""

    kind: str
    """库类别（`platform` 平台服务库 / `tenant` 服务租户库）。"""

    service: str
    """归属服务标识。"""

    db_key: str
    """数据源键（`platform_{service}` / `tenant_{service}_{code}`）。"""

    url: str
    """目标连接串（含密码；禁止写入日志）。"""

    tenant_code: str | None = None
    """租户编码（平台服务库为 None）。"""


def build_parser() -> argparse.ArgumentParser:
    """构建命令行解析器。

    Returns:
        argparse.ArgumentParser: 解析器。
    """
    parser = argparse.ArgumentParser(description="按「服务 × 租户」建库（平台服务库 + 服务租户库；幂等）")
    parser.add_argument("--code", action="append", default=[], help="租户编码（可重复；库键 tenant_{service}_{code}）")
    parser.add_argument("--all-tenants", action="store_true", help="租户取注册库（platform_tenant）未软删全集")
    parser.add_argument("--service", action="append", default=[], help="服务标识（可重复；缺省全部启用服务）")
    parser.add_argument("--admin-url", default="", help="建库管理连接串（缺省按方言推导）")
    parser.add_argument("--schema", default="", help="达梦目标模式（仅达梦生效；缺省取库名）")
    parser.add_argument("--skip-platform", action="store_true", help="跳过平台服务库（只建服务租户库）")
    parser.add_argument("--skip-tenants", action="store_true", help="跳过服务租户库（只建平台服务库）")
    parser.add_argument("--dry-run", action="store_true", help="仅打印计划（不建连、不建库）")
    return parser


def _masked(url: str) -> str:
    """连接串脱敏（隐藏密码）。

    Args:
        url: 连接串。

    Returns:
        str: 脱敏连接串。
    """
    return make_url(url).render_as_string(hide_password=True)


def _query_tenant_codes_sync(url: str) -> list[str]:
    """同步枚举租户编码（达梦等无异步方言驱动）。

    Args:
        url: 租户注册库连接串。

    Returns:
        list[str]: 租户编码列表。
    """
    engine: Engine = create_engine(url, poolclass=NullPool)
    try:
        with engine.connect() as connection:
            rows = connection.execute(select(SysTenant.code).where(SysTenant.deleted_at.is_(None))).all()
            return [str(code) for (code,) in rows]
    finally:
        engine.dispose()


async def _tenant_codes(registry_url: str) -> list[str]:
    """枚举租户注册库未软删租户编码（达梦走同步驱动线程）。

    Args:
        registry_url: 租户注册库连接串。

    Returns:
        list[str]: 租户编码列表（按主键序）。
    """
    if make_url(registry_url).get_backend_name() == _DM:
        return await asyncio.to_thread(_query_tenant_codes_sync, registry_url)
    engine = create_async_engine(registry_url, poolclass=NullPool)
    try:
        async with engine.connect() as connection:
            result = await connection.execute(select(SysTenant.code).where(SysTenant.deleted_at.is_(None)))
            return [str(code) for (code,) in result.all()]
    finally:
        await engine.dispose()


def _resolve_services(requested: Sequence[str]) -> tuple[str, ...]:
    """解析服务维度（显式指定须为已登记服务标识；缺省取全部启用服务）。

    Args:
        requested: 命令行指定的服务标识列表。

    Returns:
        tuple[str, ...]: 服务标识元组（保序去重）。

    Raises:
        ConfigError: 指定服务未登记 / 目录无启用服务。
    """
    if requested:
        registered = known_service_keys()
        unknown = [service for service in requested if service not in registered]
        if unknown:
            raise ConfigError(f"服务标识未登记：{', '.join(unknown)}")
        return tuple(dict.fromkeys(requested))
    services = enabled_service_keys()
    if not services:
        raise ConfigError("服务目录无已启用服务（service_key 非空且 status=enabled），请显式 --service")
    return services


async def build_tasks(args: argparse.Namespace) -> list[ProvisionTask]:
    """构建建库任务清单（平台服务库 → 各服务租户库）。

    Args:
        args: 命令行参数。

    Returns:
        list[ProvisionTask]: 任务清单（保序）。

    Raises:
        ConfigError: 服务 / 租户维度缺失或租户注册库不可用。
    """
    settings = get_settings()
    # 运维通道：允许跨服务库键（按各服务建库，不以运行服务为限）
    factory = EngineFactory(settings, allow_cross_service=True)
    services = _resolve_services(args.service)

    tasks: list[ProvisionTask] = []
    if not args.skip_platform:
        for service in services:
            key = build_platform_db_key(service)
            tasks.append(
                ProvisionTask(kind=DB_KIND_PLATFORM, service=service, db_key=key, url=factory.resolved_url(key))
            )

    if args.skip_tenants:
        return tasks

    codes = list(dict.fromkeys(args.code))
    if not codes and args.all_tenants:
        registry_key = build_platform_db_key(TENANT_SERVICE_KEY)
        registry_url = factory.resolved_url(registry_key)
        try:
            codes = await _tenant_codes(registry_url)
        except Exception as exc:
            raise ConfigError(
                f"租户注册库不可读（{registry_key}）：请先建库并迁移 + 种子（ops.seed_tenant），或改用 --code"
            ) from exc
        if not codes:
            print("[provision_tenant] 租户注册库未注册租户（sys_tenant 为空）")
    if not codes:
        raise ConfigError("需 --code（可重复）或 --all-tenants 指定租户；仅建平台服务库请用 --skip-tenants")

    for service in services:
        for code in codes:
            key = build_tenant_db_key(code, service=service)
            tasks.append(
                ProvisionTask(
                    kind=DB_KIND_TENANT,
                    service=service,
                    db_key=key,
                    url=factory.resolved_url(key),
                    tenant_code=code,
                )
            )
    return tasks


async def run(args: argparse.Namespace) -> int:
    """执行建库（幂等）。

    Args:
        args: 命令行参数。

    Returns:
        int: 退出码（成功 0）。
    """
    tasks = await build_tasks(args)
    print(f"[provision_tenant] 待建库 {len(tasks)} 个目标（服务 {len(_resolve_services(args.service))} 个）")
    for task in tasks:
        key = parse_db_key(task.db_key)
        name = database_name(key, service=task.service)
        print(f"[provision_tenant] {task.kind:<8} {task.service:<12} {task.db_key:<28} {name:<28} {_masked(task.url)}")
    if args.dry_run:
        print("[provision_tenant] dry-run：不建连、不建库")
        return 0

    created = 0
    existed = 0
    failed: list[str] = []
    for task in tasks:
        target = resolve_target(task.url, name=args.schema or None, admin_url=args.admin_url)
        try:
            if await create_database(target):
                created += 1
                print(f"[provision_tenant] {task.db_key} → 新建（{target.describe()}）")
            else:
                existed += 1
                print(f"[provision_tenant] {task.db_key} → 已存在（跳过）")
        except Exception as exc:  # 单库失败不中断整批
            failed.append(task.db_key)
            print(f"[provision_tenant] {task.db_key} → 失败：{type(exc).__name__}: {exc}")
    print(
        f"[provision_tenant] 汇总：新建 {created}、已存在 {existed}、失败 {len(failed)}"
        + (f"（失败：{', '.join(failed)}）" if failed else "")
    )
    return 1 if failed else 0


def main(argv: Sequence[str] | None = None) -> int:
    """入口。

    Args:
        argv: 命令行参数。

    Returns:
        int: 退出码。
    """
    args = build_parser().parse_args(argv)
    try:
        return asyncio.run(run(args))
    except ConfigError as exc:
        print(f"[provision_tenant] 失败：{exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
