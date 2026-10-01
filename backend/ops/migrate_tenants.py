"""批量迁移：按「服务 × 数据源 × 租户」遍历（分链执行 Alembic 迁移，幂等）（06_02）。

用法：

```bash
cd backend
uv run python -m ops.migrate_tenants --dry-run                 # 清单预演（不建连）
uv run python -m ops.migrate_tenants                           # 全部启用服务 × 各租户 + 归档
uv run python -m ops.migrate_tenants --service platform        # 仅指定服务（可重复）
uv run python -m ops.migrate_tenants --target platform         # 仅各服务的平台服务库
uv run python -m ops.migrate_tenants --target tenants --code demo --code acme
uv run python -m ops.migrate_tenants --target tenant \
    --url "dm+dmPython://SYSDBA:pass@host:5236" --schema BMS_MIGRCHECK   # 单库（演练 / 迁移演练）
```

- **服务维度**：`--service`（可重复）显式指定，缺省取服务目录**已启用服务**（`enabled_service_keys()`）；
- **租户维度**：`--code`（可重复）显式指定，或 `--all-tenants` 从**租户注册库**（键 `platform_tenant`）
  读未软删租户编码；`--target tenants|all` 需要二者之一；
- **库名基 `db_basis`（10_04）**：库键取「租户库名对照」`sys_tenant_database.db_basis`（缺对照行回落
  当前 `code`）——注册库不可读的显式 `--code` 模式回落 `code`（离线 / 演练可用）；库名与当前编码
  可不一致，由对照表解释；
- **链映射（06_02 分链）**：平台服务库 `bms_{service}` → 链 `{service}:platform`；服务租户库
  `bms_{service}_{db_basis}` → 链 `{service}:tenant`；归档库 `bms_archive` → 链 `platform:archive`
  （归档库不服务化，表集为空 → 无脚本跳过）；
- **执行**：逐库经 Alembic 程序化接口 `command.upgrade(cfg, "head")`（配置段 = 链名，版本目录 /
  元数据子集取自 `db/migration.py` 链注册）；
- **幂等**：目标 `alembic_version` 已为链 head → 输出「已是最新（跳过）」；链无脚本 → 「无脚本（跳过）」；
- **失败不中断**：单库失败记 ERROR 并继续下一库，末尾汇总；存在失败时退出码 1；
- **`--dry-run`**：仅打印清单（连接串脱敏）与库数量统计，不建连、不迁移；
- 达梦目标经 `--schema` 指定模式（库级隔离）。
"""

import argparse
import asyncio
from collections import Counter
from dataclasses import dataclass

from sqlalchemy import create_engine, select
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.config import Settings, get_settings
from bms_core.core.exceptions import ConfigError
from bms_core.core.objects import BaseValueObject
from bms_core.db.engine import EngineFactory
from bms_core.db.keys import build_platform_db_key, build_tenant_db_key
from bms_core.db.migration import (
    DATASOURCE_ARCHIVE,
    DATASOURCE_PLATFORM,
    DATASOURCE_TENANT,
    MigrationChain,
    archive_chain,
    build_chain_name,
    current_revision,
    head_revision,
    resolve_chain,
    upgrade_chain,
)
from bms_core.db.tenant_source import TENANT_SERVICE_KEY
from bms_core.services.module_registry import enabled_service_keys

_DM = "dm"
_TARGETS = ("all", "platform", "tenants", "tenant", "archive")


@dataclass(frozen=True)
class MigrationTask(BaseValueObject):
    """单个迁移任务（链 / 展示名 / 连接串 / 模式）。"""

    chain: MigrationChain
    label: str
    url: str
    schema: str = ""


@dataclass(frozen=True)
class TenantRef(BaseValueObject):
    """租户引用（编码 + 库名基）：库键按 `db_basis` 派生（10_04）。"""

    code: str
    """租户编码（当前值）。"""

    db_basis: str
    """库名基（对照表 `sys_tenant_database`；缺行回落编码）。"""


@dataclass(frozen=True)
class MigrationSummary(BaseValueObject):
    """批量迁移结果汇总（成功 / 跳过 / 失败 + 库数量统计）。"""

    succeeded: tuple[str, ...]
    skipped: tuple[str, ...]
    failed: tuple[str, ...]

    @property
    def exit_code(self) -> int:
        """退出码（存在失败为 1）。

        Returns:
            int: 0 全成功 / 1 存在失败。
        """
        return 1 if self.failed else 0


def build_parser() -> argparse.ArgumentParser:
    """构建命令行解析器。

    Returns:
        argparse.ArgumentParser: 解析器。
    """
    parser = argparse.ArgumentParser(description="批量迁移（服务 × 数据源 × 租户；幂等）")
    parser.add_argument("--target", default="all", choices=_TARGETS, help="迁移目标（缺省 all）")
    parser.add_argument("--service", action="append", default=[], help="服务标识（可重复；缺省全部启用服务）")
    parser.add_argument("--code", action="append", default=[], help="租户编码（可重复；库键 tenant_{service}_{code}）")
    parser.add_argument("--all-tenants", action="store_true", help="租户取注册库（platform_tenant）未软删全集")
    parser.add_argument(
        "--db-key", default="", help="指定单个库键（单库模式：platform_{service} / tenant_{service}_{code}）"
    )
    parser.add_argument("--url", default="", help="显式连接串（单库模式；含密码，禁止写入日志）")
    parser.add_argument("--schema", default="", help="达梦目标模式（仅达梦生效）")
    parser.add_argument("--dry-run", action="store_true", help="仅打印清单（不建连）")
    return parser


def _masked(url: str) -> str:
    """连接串脱敏（隐藏密码）。

    Args:
        url: 连接串。

    Returns:
        str: 脱敏连接串。
    """
    return make_url(url).render_as_string(hide_password=True)


def _tenant_refs_sync(url: str) -> ConcurrentStableList[TenantRef]:
    """同步枚举租户引用（达梦等无异步方言驱动的租户注册库）。

    Args:
        url: 租户注册库连接串。

    Returns:
        ConcurrentStableList[TenantRef]: 租户引用列表（库名基缺对照行回落当前编码）。
    """
    from bms_tenant.models.tenant import SysTenant  # 惰性：仅读租户注册库时需要，避免单一服务镜像强依赖
    from bms_tenant.models.tenant_database import SysTenantDatabase

    engine: Engine = create_engine(url, poolclass=NullPool)
    try:
        with engine.connect() as connection:
            statement = (
                select(SysTenant.code, SysTenantDatabase.db_basis)
                .outerjoin(
                    SysTenantDatabase,
                    (SysTenantDatabase.tenant_id == SysTenant.id) & (SysTenantDatabase.deleted_at.is_(None)),
                )
                .where(SysTenant.deleted_at.is_(None))
            )
            return ConcurrentStableList(_ref(code, basis) for code, basis in connection.execute(statement).all())
    finally:
        engine.dispose()


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


async def tenant_refs(registry_url: str) -> ConcurrentStableList[TenantRef]:
    """枚举租户引用（租户注册库查询；库名基经对照表；达梦走同步驱动线程）。

    Args:
        registry_url: 租户注册库连接串。

    Returns:
        ConcurrentStableList[TenantRef]: 租户引用列表（按主键序）。
    """
    if make_url(registry_url).get_backend_name() == _DM:
        return await asyncio.to_thread(_tenant_refs_sync, registry_url)
    from bms_tenant.models.tenant import SysTenant  # 惰性：仅读租户注册库时需要
    from bms_tenant.models.tenant_database import SysTenantDatabase

    engine = create_async_engine(registry_url, poolclass=NullPool)
    try:
        async with engine.connect() as connection:
            statement = (
                select(SysTenant.code, SysTenantDatabase.db_basis)
                .outerjoin(
                    SysTenantDatabase,
                    (SysTenantDatabase.tenant_id == SysTenant.id) & (SysTenantDatabase.deleted_at.is_(None)),
                )
                .where(SysTenant.deleted_at.is_(None))
            )
            result = await connection.execute(statement)
            return ConcurrentStableList(_ref(code, basis) for code, basis in result.all())
    finally:
        await engine.dispose()


def resolve_services(requested: ConcurrentStableList[str], *, use_default: bool = True) -> ConcurrentStableList[str]:
    """解析服务维度（显式指定须为已登记服务标识；缺省取全部启用服务）。

    Args:
        requested: 命令行指定的服务标识列表。
        use_default: 未指定时是否回落全部启用服务（False 时返回空列表）。

    Returns:
        ConcurrentStableList[str]: 服务标识列表（保序去重）。

    Raises:
        ConfigError: 指定服务未登记 / 目录无启用服务。
    """
    if requested:
        return ConcurrentStableList(dict.fromkeys(requested))
    if not use_default:
        return ConcurrentStableList()
    services = enabled_service_keys()
    if not services:
        raise ConfigError("服务目录无已启用服务（service_key 非空且 status=enabled），请显式 --service")
    return ConcurrentStableList(services)


def service_tasks(
    services: ConcurrentStableList[str],
    tenants: ConcurrentStableList[TenantRef],
    *,
    settings: Settings | None = None,
    include_platform: bool = True,
    include_tenants: bool = True,
    include_archive: bool = False,
) -> ConcurrentStableList[MigrationTask]:
    """构建「服务 × 数据源 × 租户」迁移任务清单（建库入口与批量迁移共用）。

    Args:
        services: 服务标识列表。
        tenants: 租户引用列表（`include_tenants` 为真时使用；库键按 `db_basis` 派生）。
        settings: 应用配置；None 取全局配置单例。
        include_platform: 是否包含各服务的平台服务库。
        include_tenants: 是否包含各服务的租户库。
        include_archive: 是否包含归档库。

    Returns:
        ConcurrentStableList[MigrationTask]: 任务清单（保序：平台 → 各服务租户 → 归档）。

    Raises:
        ConfigError: 服务标识未登记。
    """
    resolved = settings or get_settings()
    factory = EngineFactory(resolved, allow_cross_service=True)  # 运维通道：批量迁移按各服务库执行
    tasks: ConcurrentStableList[MigrationTask] = ConcurrentStableList()
    for service in services:
        if include_platform:
            chain = resolve_chain(build_chain_name(service, DATASOURCE_PLATFORM))
            key = build_platform_db_key(service)
            tasks.add(MigrationTask(chain=chain, label=key, url=factory.resolved_url(key)))
        if not include_tenants:
            continue
        for tenant in tenants:
            chain = resolve_chain(build_chain_name(service, DATASOURCE_TENANT))
            key = build_tenant_db_key(tenant.db_basis, service=service)
            tasks.add(MigrationTask(chain=chain, label=key, url=factory.resolved_url(key)))
    if include_archive:
        chain = archive_chain()
        tasks.add(MigrationTask(chain=chain, label="archive", url=factory.resolved_url("archive")))
    return tasks


async def build_tasks(args: argparse.Namespace) -> ConcurrentStableList[MigrationTask]:
    """按命令行参数构建迁移任务清单。

    Args:
        args: 命令行参数。

    Returns:
        ConcurrentStableList[MigrationTask]: 任务清单。

    Raises:
        ConfigError: 目标与参数组合非法 / 租户维度缺失 / 租户注册库不可读。
    """
    settings = get_settings()
    factory = EngineFactory(settings, allow_cross_service=True)
    use_default_services = args.target in ("all", "platform", "tenants")
    services = resolve_services(ConcurrentStableList(args.service), use_default=use_default_services)

    if args.target == "tenant":
        if not args.url:
            raise ConfigError("`--target tenant` 需显式 `--url`（单库模式：演练 / 指定库）")
        service = services[0] if services else settings.app.service
        chain = resolve_chain(build_chain_name(service, DATASOURCE_TENANT))
        return ConcurrentStableList(
            [MigrationTask(chain=chain, label=args.db_key or "tenant", url=args.url, schema=args.schema)]
        )

    if args.target == "archive":
        chain = archive_chain()
        url = args.url or factory.resolved_url("archive")
        return ConcurrentStableList([MigrationTask(chain=chain, label="archive", url=url, schema=args.schema)])

    if args.target == "platform":
        if args.url:  # 单库模式（演练）：指定服务（缺省取 [app].service）的平台服务库
            service = services[0] if services else settings.app.service
            if not service:
                raise ConfigError("`--target platform --url` 需 `--service` 或 [app].service 指定服务")
            chain = resolve_chain(build_chain_name(service, DATASOURCE_PLATFORM))
            return ConcurrentStableList(
                [
                    MigrationTask(
                        chain=chain,
                        label=args.db_key or build_platform_db_key(service),
                        url=args.url,
                        schema=args.schema,
                    )
                ]
            )
        return service_tasks(services, ConcurrentStableList(), settings=settings, include_tenants=False)

    codes = ConcurrentStableList(dict.fromkeys(args.code))
    registry_url = factory.resolved_url(build_platform_db_key(TENANT_SERVICE_KEY))
    refs: ConcurrentStableList[TenantRef] = ConcurrentStableList()
    if codes:
        refs = ConcurrentStableList(TenantRef(code=code, db_basis=code) for code in codes)
        refs = await enrich_refs(refs, registry_url)
    if args.all_tenants:
        refs = await _load_refs(registry_url)
        if not refs:
            print("[migrate_tenants] 租户注册库未注册租户（sys_tenant 为空）")
    if not refs and args.target in ("all", "tenants"):
        raise ConfigError("需 --code（可重复）或 --all-tenants 指定租户；仅迁移平台服务库请用 --target platform")
    return service_tasks(
        services,
        refs,
        settings=settings,
        include_platform=args.target == "all",
        include_tenants=bool(refs),
        include_archive=args.target == "all",
    )


async def _load_refs(registry_url: str) -> ConcurrentStableList[TenantRef]:
    """读租户注册库全部未软删租户引用（不可读即明确报错）。

    Args:
        registry_url: 租户注册库连接串。

    Returns:
        ConcurrentStableList[TenantRef]: 租户引用列表。

    Raises:
        ConfigError: 租户注册库不可读。
    """
    try:
        return await tenant_refs(registry_url)
    except Exception as exc:
        raise ConfigError(f"租户注册库不可读（请先建库并迁移 + 种子 ops.seed_tenant，或改用 --code）：{exc}") from exc


async def enrich_refs(refs: ConcurrentStableList[TenantRef], registry_url: str) -> ConcurrentStableList[TenantRef]:
    """显式 `--code` 模式补库名基（读对照表；注册库不可读回落编码，离线 / 演练可用）。

    Args:
        refs: 待补租户引用（`db_basis` 暂为编码）。
        registry_url: 租户注册库连接串。

    Returns:
        ConcurrentStableList[TenantRef]: 补库名基后的租户引用。
    """
    try:
        records = await tenant_refs(registry_url)
    except Exception as exc:
        print(f"[migrate_tenants] 租户注册库不可读，显式 --code 按编码作库名基：{type(exc).__name__}: {exc}")
        return ConcurrentStableList(refs)
    mapping = {record.code: record.db_basis for record in records}
    return ConcurrentStableList(TenantRef(code=ref.code, db_basis=mapping.get(ref.code, ref.db_basis)) for ref in refs)


def _counts(tasks: ConcurrentStableList[MigrationTask]) -> str:
    """库数量统计（按库类别与链名）。

    Args:
        tasks: 任务清单。

    Returns:
        str: 统计文案（如「平台服务库 9 / 服务租户库 18」）。
    """
    by_datasource = Counter(task.chain.datasource for task in tasks)
    labels = {
        DATASOURCE_PLATFORM: "平台服务库",
        DATASOURCE_TENANT: "服务租户库",
        DATASOURCE_ARCHIVE: "归档库",
    }
    detail = "、".join(f"{labels.get(name, name)} {count}" for name, count in sorted(by_datasource.items()))
    return f"共 {len(tasks)} 个目标（{detail}）"


async def run_tasks(tasks: ConcurrentStableList[MigrationTask]) -> MigrationSummary:
    """逐库执行迁移（幂等；单库失败不中断）。

    Args:
        tasks: 任务清单。

    Returns:
        MigrationSummary: 结果汇总。
    """
    succeeded: ConcurrentStableList[str] = ConcurrentStableList()
    skipped: ConcurrentStableList[str] = ConcurrentStableList()
    failed: ConcurrentStableList[str] = ConcurrentStableList()
    for task in tasks:
        chain = task.chain
        if head_revision(chain) is None:
            skipped.add(task.label)
            print(f"[migrate_tenants] {chain.name} {task.label} → 无脚本（跳过）")
            continue
        try:
            head = head_revision(chain)
            current = await current_revision(task.url, schema=task.schema)
            if head is not None and current == head:
                skipped.add(task.label)
                print(f"[migrate_tenants] {chain.name} {task.label} → 已是最新（跳过）")
                continue
            await asyncio.to_thread(upgrade_chain, chain, task.url, schema=task.schema)
        except Exception as exc:  # 单库失败不中断整批
            failed.add(task.label)
            print(f"[migrate_tenants] {chain.name} {task.label} → 失败：{type(exc).__name__}: {exc}")
            continue
        succeeded.add(task.label)
        print(f"[migrate_tenants] {chain.name} {task.label} → 迁移完成（{current or '未迁移'} → {head or '无脚本'}）")
    return MigrationSummary(succeeded=tuple(succeeded), skipped=tuple(skipped), failed=tuple(failed))


def report(summary: MigrationSummary, tasks: ConcurrentStableList[MigrationTask]) -> int:
    """输出汇总与库数量统计，返回退出码。

    Args:
        summary: 结果汇总。
        tasks: 任务清单（统计库数量）。

    Returns:
        int: 退出码（存在失败为 1）。
    """
    print(
        f"[migrate_tenants] 汇总：成功 {len(summary.succeeded)}、跳过 {len(summary.skipped)}、"
        f"失败 {len(summary.failed)}" + (f"（失败：{', '.join(summary.failed)}）" if summary.failed else "")
    )
    print(f"[migrate_tenants] 库数量：{_counts(tasks)}")
    return summary.exit_code


async def run(args: argparse.Namespace) -> int:
    """执行批量迁移。

    Args:
        args: 命令行参数。

    Returns:
        int: 退出码（存在失败为 1）。
    """
    tasks = await build_tasks(args)
    print(f"[migrate_tenants] 待迁移 {len(tasks)} 个目标（target={args.target}）")
    for task in tasks:
        suffix = f" schema={task.schema}" if task.schema else ""
        print(f"[migrate_tenants] {task.chain.name:<22} {task.label:<28} {_masked(task.url)}{suffix}")
    if args.dry_run:
        print(f"[migrate_tenants] 库数量：{_counts(tasks)}")
        print("[migrate_tenants] dry-run：不建连、不迁移")
        return 0
    return report(await run_tasks(tasks), tasks)


def main(argv: ConcurrentStableList[str] | None = None) -> int:
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
        print(f"[migrate_tenants] 失败：{exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
