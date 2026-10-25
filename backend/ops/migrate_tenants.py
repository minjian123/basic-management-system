"""批量迁移：按「部署单元 × 数据源 × 库」执行所含各业务域清单（幂等）（07C `03_02`）。

用法：

```bash
cd backend
uv run python -m ops.migrate_tenants --dry-run                 # 清单预演（不建连）
uv run python -m ops.migrate_tenants                           # 全部启用单元 × 各租户 + 归档
uv run python -m ops.migrate_tenants --unit platform           # 仅指定单元（可重复；--service 为同义别名）
uv run python -m ops.migrate_tenants --target platform         # 仅各单元的平台服务库
uv run python -m ops.migrate_tenants --target tenants --code demo --code acme
uv run python -m ops.migrate_tenants --target tenant \
    --url "dm+dmPython://SYSDBA:pass@host:5236" --schema BMS_MIGRCHECK   # 单库（演练）
```

- **单元维度**：`--unit`（可重复）显式指定，缺省取服务目录**已启用服务**（缺省形态下单元标识即服务标识）；
- **清单维度**：一个单元在一个库里承载多个业务域 → 按域名**稳定顺序**逐条执行业务域清单；
  每条清单独立一张版本记录表 `alembic_version_{domain}`，已到 head 直接跳过；
- **租户维度**：`--code`（可重复）显式指定，或 `--all-tenants` 从租户注册库（键 `platform_tenant`）
  读未软删租户编码；`--target tenants|all` 需要二者之一；
- **库名基 `db_basis`（10_04）**：库键取「租户库名对照」`sys_tenant_database.db_basis`（缺对照行回落
  当前 `code`）——库名与当前编码可不一致，由对照表解释；
- **执行期校验（§3.8）**：执行前先全量预检（脚本目标表归属 / 清单表集不相交 / 破坏性操作放行），
  执行中同库加库级锁（PostgreSQL / MySQL；其余方言按部署串行）、逐清单核对版本记录表与单调性；
  **任一清单失败 → 该库整体失败并指出域与脚本，不回滚已成功清单**；
- **失败不中断**：单库失败记 ERROR 并继续下一库，末尾汇总；存在失败时退出码 1；
- **`--dry-run`**：仅打印清单（连接串脱敏）与库数量统计，不建连、不迁移；
- 达梦目标经 `--schema` 指定模式（库级隔离）。
"""

import argparse
import asyncio
from collections import Counter
from dataclasses import dataclass

from sqlalchemy.engine import make_url

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
    MigrationSeries,
    archive_series,
    current_revision,
    head_revision,
    unit_series,
    upgrade_series,
)
from bms_core.db.migration_guard import (
    MigrationGuard,
    check_monotonic,
    check_version_known,
    library_lock,
)
from bms_core.db.tenant_source import TENANT_SERVICE_KEY
from bms_core.services.module_registry import enabled_service_keys
from bms_core.tenant.registry import TenantRef
from bms_core.tenant.registry import tenant_refs as tenant_refs_base

RUN_IMAGE = "*"
"""本脚本只依赖 `bms_core` 与 `ops`（不导入任何服务包），任意服务镜像均可运行。"""
_TARGETS = ("all", "platform", "tenants", "tenant", "archive")


@dataclass(frozen=True)
class MigrationTask(BaseValueObject):
    """单个迁移任务（库维度：单元 + 数据源 + 目标库 + 该库要跑的清单序列）。"""

    unit: str
    datasource: str
    series: ConcurrentStableList[MigrationSeries]
    label: str
    url: str
    schema: str = ""
    allow_destructive: bool = False

    @property
    def domains(self) -> str:
        """清单域列表（展示用，如 `platform_registry, user`）。

        Returns:
            str: 逗号分隔的域标识。
        """
        return ", ".join(series.domain for series in self.series) or "—"


@dataclass(frozen=True)
class MigrationSummary(BaseValueObject):
    """批量迁移结果汇总（成功 / 跳过 / 失败 + 库数量统计）。"""

    succeeded: ConcurrentStableList[str]
    skipped: ConcurrentStableList[str]
    failed: ConcurrentStableList[str]

    @property
    def exit_code(self) -> int:
        """退出码（存在失败为 1）。

        Returns:
            int: 0 全成功 / 1 存在失败。
        """
        return 1 if self.failed else 0


def build_task_parser(description: str) -> argparse.ArgumentParser:
    """构建「单元 × 数据源 × 库」任务清单命令行解析器（批量迁移与 ops 建表入口共用）。

    Args:
        description: 解析器描述（各入口自定措辞）。

    Returns:
        argparse.ArgumentParser: 解析器。
    """
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--target", default="all", choices=_TARGETS, help="迁移目标（缺省 all）")
    parser.add_argument(
        "--unit",
        "--service",
        dest="unit",
        action="append",
        default=[],
        help="部署单元标识（可重复；`--service` 为同义别名；缺省全部启用服务）",
    )
    parser.add_argument("--code", action="append", default=[], help="租户编码（可重复；库键 tenant_{unit}_{code}）")
    parser.add_argument("--all-tenants", action="store_true", help="租户取注册库（platform_tenant）未软删全集")
    parser.add_argument("--db-key", default="", help="指定单个库键（单库模式：platform_{unit} / tenant_{unit}_{code}）")
    parser.add_argument("--url", default="", help="显式连接串（单库模式；含密码，禁止写入日志）")
    parser.add_argument("--schema", default="", help="达梦目标模式（仅达梦生效）")
    parser.add_argument(
        "--allow-destructive",
        action="store_true",
        help="显式放行破坏性操作（drop table / drop column；缺省拒绝）",
    )
    parser.add_argument("--dry-run", action="store_true", help="仅打印清单（不建连）")
    return parser


def build_parser() -> argparse.ArgumentParser:
    """构建命令行解析器。

    Returns:
        argparse.ArgumentParser: 解析器。
    """
    return build_task_parser("批量迁移（单元 × 数据源 × 租户；幂等）")


def _masked(url: str) -> str:
    """连接串脱敏（隐藏密码）。

    Args:
        url: 连接串。

    Returns:
        str: 脱敏连接串。
    """
    return make_url(url).render_as_string(hide_password=True)


async def tenant_refs(registry_url: str) -> ConcurrentStableList[TenantRef]:
    """枚举租户引用（租户注册库查询；库名基经对照表；达梦走同步驱动线程）。

    实现已下沉 `bms_core.tenant.registry.tenant_refs`（14_04）；本函数保留同名转发，
    使既有调用方（`ops.init_tenant` / `ops.provision_tenant` / `ops.seed_user`）零改动。

    Args:
        registry_url: 租户注册库连接串。

    Returns:
        ConcurrentStableList[TenantRef]: 租户引用列表（按主键序）。
    """
    return await tenant_refs_base(registry_url)


def resolve_units(requested: ConcurrentStableList[str], *, use_default: bool = True) -> ConcurrentStableList[str]:
    """解析单元维度（显式指定须为已登记单元；缺省取全部启用服务——缺省形态下单元即服务）。

    Args:
        requested: 命令行指定的单元标识列表。
        use_default: 未指定时是否回落全部启用服务（False 时返回空列表）。

    Returns:
        ConcurrentStableList[str]: 单元标识列表（保序去重）。

    Raises:
        ConfigError: 指定单元未登记 / 目录无启用服务。
    """
    if requested:
        return ConcurrentStableList(dict.fromkeys(requested))
    if not use_default:
        return ConcurrentStableList()
    units = enabled_service_keys()
    if not units:
        raise ConfigError("服务目录无已启用单元（service_key 非空且 status=enabled），请显式 --unit")
    return ConcurrentStableList(units)


def _series_or_empty(unit: str, datasource: str) -> ConcurrentStableList[MigrationSeries]:
    """取单元在某库类别的清单序列（该库无域时为空；归档固定单清单）。

    Args:
        unit: 部署单元标识。
        datasource: 数据源段。

    Returns:
        ConcurrentStableList[MigrationSeries]: 清单序列（执行序）。
    """
    if datasource == DATASOURCE_ARCHIVE:
        return ConcurrentStableList([archive_series()])
    return unit_series(unit, datasource)


def unit_tasks(
    units: ConcurrentStableList[str],
    tenants: ConcurrentStableList[TenantRef],
    *,
    settings: Settings | None = None,
    include_platform: bool = True,
    include_tenants: bool = True,
    include_archive: bool = False,
    allow_destructive: bool = False,
) -> ConcurrentStableList[MigrationTask]:
    """构建「单元 × 数据源 × 租户」迁移任务清单（建库入口与批量迁移共用）。

    Args:
        units: 单元标识列表。
        tenants: 租户引用列表（`include_tenants` 为真时使用；库键按 `db_basis` 派生）。
        settings: 应用配置；None 取全局配置单例。
        include_platform: 是否包含各单元的平台服务库。
        include_tenants: 是否包含各单元的租户库。
        include_archive: 是否包含归档库。

    Returns:
        ConcurrentStableList[MigrationTask]: 任务清单（保序：平台 → 各单元租户 → 归档）。
    """
    resolved = settings or get_settings()
    factory = EngineFactory(resolved, allow_cross_service=True)  # 运维通道：批量迁移按各单元库执行
    tasks: ConcurrentStableList[MigrationTask] = ConcurrentStableList()
    for unit in units:
        if include_platform:
            key = build_platform_db_key(unit)
            tasks.add(
                MigrationTask(
                    unit=unit,
                    datasource=DATASOURCE_PLATFORM,
                    series=_series_or_empty(unit, DATASOURCE_PLATFORM),
                    label=key,
                    url=factory.resolved_url(key),
                    allow_destructive=allow_destructive,
                )
            )
        if not include_tenants:
            continue
        for tenant in tenants:
            key = build_tenant_db_key(tenant.db_basis, service=unit)
            tasks.add(
                MigrationTask(
                    unit=unit,
                    datasource=DATASOURCE_TENANT,
                    series=_series_or_empty(unit, DATASOURCE_TENANT),
                    label=key,
                    url=factory.resolved_url(key),
                    allow_destructive=allow_destructive,
                )
            )
    if include_archive:
        tasks.add(
            MigrationTask(
                unit=archive_series().domain,
                datasource=DATASOURCE_ARCHIVE,
                series=ConcurrentStableList([archive_series()]),
                label="archive",
                url=factory.resolved_url("archive"),
                allow_destructive=allow_destructive,
            )
        )
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
    use_default_units = args.target in ("all", "platform", "tenants")
    units = resolve_units(ConcurrentStableList(args.unit), use_default=use_default_units)
    allow_destructive = bool(args.allow_destructive)

    if args.target == "tenant":
        if not args.url:
            raise ConfigError("`--target tenant` 需显式 `--url`（单库模式：演练 / 指定库）")
        unit = units[0] if units else settings.app.unit or settings.app.service
        return ConcurrentStableList(
            [
                MigrationTask(
                    unit=unit,
                    datasource=DATASOURCE_TENANT,
                    series=_series_or_empty(unit, DATASOURCE_TENANT),
                    label=args.db_key or "tenant",
                    url=args.url,
                    schema=args.schema,
                    allow_destructive=allow_destructive,
                )
            ]
        )

    if args.target == "archive":
        series = archive_series()
        url = args.url or factory.resolved_url("archive")
        return ConcurrentStableList(
            [
                MigrationTask(
                    unit=series.domain,
                    datasource=DATASOURCE_ARCHIVE,
                    series=ConcurrentStableList([series]),
                    label="archive",
                    url=url,
                    schema=args.schema,
                    allow_destructive=allow_destructive,
                )
            ]
        )

    if args.target == "platform":
        if args.url:  # 单库模式（演练）：指定单元（缺省取 [app].unit / [app].service）的平台服务库
            unit = units[0] if units else settings.app.unit or settings.app.service
            if not unit:
                raise ConfigError("`--target platform --url` 需 `--unit` 或 [app].unit / [app].service 指定单元")
            return ConcurrentStableList(
                [
                    MigrationTask(
                        unit=unit,
                        datasource=DATASOURCE_PLATFORM,
                        series=_series_or_empty(unit, DATASOURCE_PLATFORM),
                        label=args.db_key or build_platform_db_key(unit),
                        url=args.url,
                        schema=args.schema,
                        allow_destructive=allow_destructive,
                    )
                ]
            )
        return unit_tasks(
            units,
            ConcurrentStableList(),
            settings=settings,
            include_tenants=False,
            allow_destructive=allow_destructive,
        )

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
    return unit_tasks(
        units,
        refs,
        settings=settings,
        include_platform=args.target == "all",
        include_tenants=bool(refs),
        include_archive=args.target == "all",
        allow_destructive=allow_destructive,
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
    """库数量统计（按库类别）。

    Args:
        tasks: 任务清单。

    Returns:
        str: 统计文案（如「平台服务库 9 / 服务租户库 18」）。
    """
    by_datasource = Counter(task.datasource for task in tasks)
    labels = {
        DATASOURCE_PLATFORM: "平台服务库",
        DATASOURCE_TENANT: "服务租户库",
        DATASOURCE_ARCHIVE: "归档库",
    }
    detail = "、".join(f"{labels.get(name, name)} {count}" for name, count in sorted(by_datasource.items()))
    return f"共 {len(tasks)} 个目标（{detail}）"


def _fail(failed: ConcurrentStableList[str], label: str, reason: str) -> None:
    """记录单库失败（打印明细并计入汇总）。

    Args:
        failed: 失败汇总（就地追加）。
        label: 目标标签。
        reason: 失败原因。
    """
    failed.add(label)
    print(f"[migrate_tenants] {label} → 失败：{reason}")


async def run_tasks(tasks: ConcurrentStableList[MigrationTask]) -> MigrationSummary:
    """逐库执行迁移（执行期校验 + 库级锁 + 幂等；单库失败不中断整批）。

    Args:
        tasks: 任务清单。

    Returns:
        MigrationSummary: 结果汇总。
    """
    succeeded: ConcurrentStableList[str] = ConcurrentStableList()
    skipped: ConcurrentStableList[str] = ConcurrentStableList()
    failed: ConcurrentStableList[str] = ConcurrentStableList()
    for task in tasks:
        guard_problems = MigrationGuard(
            task.unit, task.datasource, allow_destructive=task.allow_destructive
        ).preflight()
        if guard_problems:
            _fail(failed, task.label, "执行前校验不通过 → " + "；".join(guard_problems))
            continue
        with library_lock(task.url) as acquired:
            if not acquired:
                _fail(failed, task.label, "库级锁被占用（另有实例正在改结构），本次不执行")
                continue
            ran = False
            broken = ""
            for series in task.series:
                try:
                    head = head_revision(series)
                    if head is None:
                        print(f"[migrate_tenants] {series.name} {task.label} → 无脚本（跳过）")
                        continue
                    current = await current_revision(task.url, version_table=series.version_table, schema=task.schema)
                    problems = check_version_known(series, current)
                    problems.update(check_monotonic(series, current, head))
                    if problems:
                        broken = "；".join(problems)
                        break
                    if current == head:
                        print(f"[migrate_tenants] {series.name} {task.label} → 已是最新（跳过）")
                        continue
                    await asyncio.to_thread(upgrade_series, series, task.url, schema=task.schema)
                except Exception as exc:  # 单清单失败：该库整体失败，不回滚已成功清单
                    broken = f"{series.name}：{type(exc).__name__}: {exc}"
                    break
                ran = True
                print(
                    f"[migrate_tenants] {series.name} {task.label} → 迁移完成"
                    f"（{current or '未迁移'} → {head or '无脚本'}）"
                )
        if broken:
            _fail(failed, task.label, broken)
        elif ran:
            succeeded.add(task.label)
        else:
            skipped.add(task.label)
    return MigrationSummary(succeeded=succeeded, skipped=skipped, failed=failed)


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
        print(f"[migrate_tenants] {task.unit:<18} {task.label:<28} 域：{task.domains} {_masked(task.url)}{suffix}")
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
