"""表单定制自建字段补建列（**数据初始化通道**；13_08 T7 / 10_01 配套）。

用法：

```bash
cd backend
uv run python -m ops.build_ext_columns --dry-run                       # 只扫描待建列，不执行 DDL
uv run python -m ops.build_ext_columns                                 # 全部启用租户
uv run python -m ops.build_ext_columns --code demo --code acme         # 指定租户
uv run python -m ops.build_ext_columns --url "sqlite+aiosqlite:///./bms_platform_demo.db"
```

口径（与《表单定制》「结构生命周期」一致）：

- **运行期 DDL 在测试 / 生产关闭**（`app.allow_runtime_ddl=false`）：请求路径登记自建字段时只写
  元数据（`ddl_status=pending`），**不改表结构**；
- 本脚本是补齐结构的**唯一通道**（与 `ops.init_schema` / `ops.migrate_tenants` 同属数据初始化）：
  扫描 `sys_field_ext` 中 `pending` 行 → 复用 `FormDdlExecutor` 建列 → 回写 `active`；
- **幂等**：列已存在即命中（`FormDdlExecutor` 的幂等分支），重复执行不报错；单条失败置 `failed`
  且不中断其它字段（失败信息留给前端标记与重试）；
- `--dry-run` 仍连库（要读 `pending` 行），只是不执行任何 DDL；
- 单库失败不中断，末尾汇总；存在失败时退出码 1。
"""

import argparse
from dataclasses import dataclass
from typing import Any

from sqlalchemy import inspect, select, text, update
from sqlalchemy.engine import Dialect, make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from bms_core.core.concurrent import (
    ConcurrentStableDict,
    ConcurrentStableFrozenList,
    ConcurrentStableList,
    ConcurrentStableSet,
)
from bms_core.core.config import get_settings
from bms_core.core.exceptions import ConfigError
from bms_core.core.objects import BaseValueObject
from bms_core.db.engine import EngineFactory
from bms_core.db.keys import build_platform_db_key, build_tenant_db_key
from bms_core.db.tenant_source import TENANT_SERVICE_KEY
from bms_core.fieldtype.mapping import ext_column_type
from bms_core.formdesign.identifier import validate_column_name, validate_table_name
from bms_core.models.platform.form_design import (
    DDL_STATUS_ACTIVE,
    DDL_STATUS_FAILED,
    DDL_STATUS_PENDING,
    SysFieldExt,
)
from bms_platform.domains.form_design.services.ddl import compile_add_column
from ops._worker import run_with_worker_id
from ops.migrate_tenants import tenant_refs

RUN_IMAGE = "platform"
"""本脚本复用平台服务的 DDL 执行器（`bms_platform.domains.form_design`），只能跑平台服务镜像。"""


@dataclass(frozen=True)
class LibraryResult(BaseValueObject):
    """单个租户库的补建列结果。"""

    url: str
    """连接串（已脱敏）。"""

    scanned: int
    """扫描到的 `pending` 字段数。"""

    built: int
    """本次真正建出的列数。"""

    skipped: int
    """列已存在（幂等命中）数。"""

    failed: ConcurrentStableList[str]
    """失败明细（`form_code.field_key：原因`）。"""


@dataclass(frozen=True)
class BuildResult(BaseValueObject):
    """整体结果（多库汇总）。"""

    libraries: ConcurrentStableList[LibraryResult]
    """各库结果（处理顺序）。"""

    @property
    def built(self) -> int:
        """合计建出的列数。

        Returns:
            int: 建出的列数。
        """
        return sum(item.built for item in self.libraries)

    @property
    def failed(self) -> int:
        """合计失败条数。

        Returns:
            int: 失败条数。
        """
        return sum(len(item.failed) for item in self.libraries)


@dataclass(frozen=True)
class ScriptEntry(BaseValueObject):
    """迁移脚本的一条条目（`skipped=True` 表示列已存在、无需执行）。"""

    field_id: int
    """`sys_field_ext` 主键（执行段回写状态用）。"""

    label: str
    """字段标识（`form_code.field_key`，日志与失败明细用）。"""

    table_name: str
    """物理表名（已过白名单）。"""

    column_name: str
    """物理列名（已过白名单）。"""

    sql: str
    """迁移语句（`skipped=True` 时为空串）。"""

    skipped: bool
    """列已存在，无需执行。"""


def build_script(
    fields: ConcurrentStableList[SysFieldExt],
    existing: ConcurrentStableDict[str, ConcurrentStableFrozenList[str]],
    *,
    dialect: Dialect,
) -> ConcurrentStableList[ScriptEntry]:
    """生成「补建列」迁移脚本内容（**纯逻辑**：不连库、不执行 DDL）。

    Args:
        fields: 待建列字段（`pending`）。
        existing: 目标表现有列（表名 → 小写列名）。
        dialect: 目标方言（决定 `VARCHAR2` 等方言落点）。

    Returns:
        ConcurrentStableList[ScriptEntry]: 每条字段的迁移语句或「已存在」标记。
    """
    entries: ConcurrentStableList[ScriptEntry] = ConcurrentStableList()
    for field in fields:
        table_name = validate_table_name(field.table_name)
        column_name = validate_column_name(field.column_name)
        label = f"{field.form_code}.{field.field_key}"
        present = existing.get(table_name, ConcurrentStableFrozenList())
        if column_name.lower() in present:
            entries.add(ScriptEntry(int(field.id or 0), label, table_name, column_name, "", True))
            continue
        sql = compile_add_column(dialect, table_name, column_name, ext_column_type(field.type), field.name)
        entries.add(ScriptEntry(int(field.id or 0), label, table_name, column_name, sql, False))
    return entries


async def _existing_columns(
    session: AsyncSession, tables: ConcurrentStableSet[str]
) -> ConcurrentStableDict[str, ConcurrentStableFrozenList[str]]:
    """探测目标表现有列（只读库，不执行 DDL）。

    Args:
        session: 异步会话。
        tables: 目标表名集合。

    Returns:
        ConcurrentStableDict[str, ConcurrentStableFrozenList[str]]: 表名 → 小写列名。
    """

    def _collect(sync_session: Any) -> ConcurrentStableDict[str, ConcurrentStableFrozenList[str]]:
        inspector = inspect(sync_session.get_bind())
        result: ConcurrentStableDict[str, ConcurrentStableFrozenList[str]] = ConcurrentStableDict()
        for table in tables:
            columns: ConcurrentStableList[str]
            try:
                columns = ConcurrentStableList(str(item["name"]).lower() for item in inspector.get_columns(table))
            except Exception:
                columns = ConcurrentStableList()
            result.set(table, ConcurrentStableFrozenList(columns))
        return result

    return await session.run_sync(_collect)


async def apply_script(session: AsyncSession, entries: ConcurrentStableList[ScriptEntry]) -> AppliedScript:
    """执行迁移脚本并回写字段状态（单条失败置 `failed`、不中断其它字段）。

    只接受生成段产出的 `ScriptEntry`（单一来源），并返回实际执行的语句清单，
    供调用方与生成脚本逐条比对。

    Args:
        session: 异步会话。
        entries: 迁移脚本条目。

    Returns:
        AppliedScript: 执行回执（执行清单 + 计数 + 失败明细）。
    """
    executed: ConcurrentStableList[str] = ConcurrentStableList()
    built = 0
    skipped = 0
    failed: ConcurrentStableList[str] = ConcurrentStableList()
    for entry in entries:
        if entry.skipped:
            skipped += 1
            continue
        executed.add(entry.sql)
        try:
            await session.execute(text(entry.sql))
        except Exception as exc:
            await session.rollback()
            await session.execute(
                update(SysFieldExt).where(SysFieldExt.id == entry.field_id).values(ddl_status=DDL_STATUS_FAILED)
            )
            await session.commit()
            failed.add(f"{entry.label}：{type(exc).__name__}: {exc}")
            print(f"[build_ext_columns] 建列失败 {entry.label}：{type(exc).__name__}: {exc}")
            continue
        await session.execute(
            update(SysFieldExt).where(SysFieldExt.id == entry.field_id).values(ddl_status=DDL_STATUS_ACTIVE)
        )
        await session.commit()
        built += 1
        print(f"[build_ext_columns] 建列 {entry.label} → {entry.column_name}")
    return AppliedScript(executed=executed, built=built, skipped=skipped, failed=failed)


@dataclass(frozen=True)
class AppliedScript(BaseValueObject):
    """执行回执：实际执行的语句清单与结果计数。"""

    executed: ConcurrentStableList[str]
    """实际执行的语句（与生成脚本中非跳过项逐条对应）。"""

    built: int
    """建出列数。"""

    skipped: int
    """列已存在跳过数。"""

    failed: ConcurrentStableList[str]
    """失败明细。"""


def script_statements(script: ConcurrentStableList[ScriptEntry]) -> ConcurrentStableList[str]:
    """生成脚本中**要执行**的语句（非跳过项，保持顺序）。

    Args:
        script: 生成段产出的脚本条目。

    Returns:
        ConcurrentStableList[str]: 语句清单（用于与执行回执比对）。
    """
    return ConcurrentStableList(entry.sql for entry in script if not entry.skipped)


async def existing_columns(
    session: AsyncSession, tables: ConcurrentStableSet[str]
) -> ConcurrentStableDict[str, ConcurrentStableFrozenList[str]]:
    """探测目标表现有列（公开入口；供初始化阶段生成脚本用）。

    Args:
        session: 异步会话。
        tables: 目标表名集合。

    Returns:
        ConcurrentStableDict[str, ConcurrentStableFrozenList[str]]: 表名 → 小写列名。
    """
    return await _existing_columns(session, tables)


async def verify_applied(session: AsyncSession, script: ConcurrentStableList[ScriptEntry]) -> ConcurrentStableList[str]:
    """回读库结构，返回脚本声明但**未生效**的列（空表示已全部生效）。

    Args:
        session: 异步会话。
        script: 生成段产出的脚本条目。

    Returns:
        ConcurrentStableList[str]: 未生效的「表.列」清单。
    """
    tables: ConcurrentStableSet[str] = ConcurrentStableSet()
    for entry in script:
        if not entry.skipped:
            tables.add(entry.table_name)
    existing = await _existing_columns(session, tables)
    missing: ConcurrentStableList[str] = ConcurrentStableList()
    for entry in script:
        if entry.skipped:
            continue
        if entry.column_name.lower() not in existing.get(entry.table_name, ConcurrentStableFrozenList()):
            missing.add(f"{entry.table_name}.{entry.column_name}")
    return missing


def build_parser() -> argparse.ArgumentParser:
    """构建命令行解析器。

    Returns:
        argparse.ArgumentParser: 解析器。
    """
    parser = argparse.ArgumentParser(description="表单定制自建字段补建列（数据初始化通道；幂等）")
    parser.add_argument("--code", action="append", default=[], help="租户编码（可重复；缺省配合 --all-tenants）")
    parser.add_argument("--all-tenants", action="store_true", help="按租户注册库枚举全部租户")
    parser.add_argument("--service", default="", help="服务标识（缺省取 [app].service）")
    parser.add_argument("--url", default="", help="单库连接串（排障用；指定后忽略租户维度）")
    parser.add_argument("--dry-run", action="store_true", help="只扫描待建列，不执行 DDL")
    return parser


def _masked(url: str) -> str:
    """连接串脱敏（隐藏密码）。

    Args:
        url: 连接串。

    Returns:
        str: 脱敏连接串。
    """
    return make_url(url).render_as_string(hide_password=True)


async def _resolve_basis(code: str) -> str:
    """取租户库名基（对照表；注册库不可读 / 未注册回落当前编码）。

    Args:
        code: 租户编码。

    Returns:
        str: 库名基。
    """
    settings = get_settings()
    factory = EngineFactory(settings, allow_cross_service=True)
    try:
        registry_url = factory.resolved_url(build_platform_db_key(TENANT_SERVICE_KEY))
        refs = await tenant_refs(registry_url)
    except Exception as exc:
        print(f"[build_ext_columns] 租户注册库不可读，按编码作库名基：{type(exc).__name__}: {exc}")
        return code
    for ref in refs:
        if ref.code == code:
            return ref.db_basis
    return code


async def _resolve_codes(args: argparse.Namespace) -> ConcurrentStableList[str]:
    """解析目标租户编码清单。

    Args:
        args: 命令行参数。

    Returns:
        ConcurrentStableList[str]: 租户编码（保序去重）。

    Raises:
        ConfigError: 既未指定 `--code` 也未指定 `--all-tenants`。
    """
    codes = ConcurrentStableList(dict.fromkeys(args.code))
    if not args.all_tenants:
        if not codes:
            raise ConfigError("需 `--code` 或 `--all-tenants` 指定目标租户（排障可用 `--url` 单库）")
        return codes
    settings = get_settings()
    factory = EngineFactory(settings, allow_cross_service=True)
    registry_url = factory.resolved_url(build_platform_db_key(TENANT_SERVICE_KEY))
    refs = await tenant_refs(registry_url)
    for ref in refs:
        if ref.code not in codes:
            codes.add(ref.code)
    return codes


async def _target_urls(args: argparse.Namespace) -> ConcurrentStableList[str]:
    """解析目标租户库连接串清单。

    Args:
        args: 命令行参数。

    Returns:
        ConcurrentStableList[str]: 连接串（保序去重）。

    Raises:
        ConfigError: 未指定服务标识，无法按模板解析库键。
    """
    if args.url:
        return ConcurrentStableList((args.url,))
    settings = get_settings()
    service = args.service or settings.app.service
    if not service:
        raise ConfigError("需 `--service` 或 `[app].service` 指定部署单元")
    factory = EngineFactory(settings, allow_cross_service=True)
    urls: ConcurrentStableList[str] = ConcurrentStableList()
    for code in await _resolve_codes(args):
        basis = await _resolve_basis(code)
        urls.add(factory.resolved_url(build_tenant_db_key(basis, service=service)))
    return urls


async def _pending_fields(session: AsyncSession) -> ConcurrentStableList[SysFieldExt]:
    """读取待建列字段（`pending`；未软删）。

    Args:
        session: 异步会话。

    Returns:
        ConcurrentStableList[SysFieldExt]: 待建列字段（主键序）。
    """
    statement = (
        select(SysFieldExt)
        .where(SysFieldExt.ddl_status == DDL_STATUS_PENDING, SysFieldExt.deleted_at.is_(None))
        .order_by(SysFieldExt.id)
    )
    rows = (await session.execute(statement)).scalars().all()
    return ConcurrentStableList(rows)


async def build_in_session(session: AsyncSession, *, dry_run: bool) -> tuple[int, int, int, ConcurrentStableList[str]]:
    """在给定会话上生成并执行补建列脚本（供 CLI 与用例共用）。

    Args:
        session: 异步会话。
        dry_run: 只生成脚本并打印，不执行 DDL。

    Returns:
        tuple: (扫描数, 建出列数, 已存在跳过数, 失败明细)。
    """
    fields = await _pending_fields(session)
    tables: ConcurrentStableSet[str] = ConcurrentStableSet()
    for field in fields:
        tables.add(validate_table_name(field.table_name))
    existing = await _existing_columns(session, tables)
    script = build_script(fields, existing, dialect=session.get_bind().dialect)
    if dry_run:
        for entry in script:
            if entry.skipped:
                print(f"[build_ext_columns] 已存在 {entry.label} → {entry.table_name}.{entry.column_name}")
            else:
                print(f"[build_ext_columns] 待建列 {entry.label} → {entry.sql}")
        return len(fields), 0, len([entry for entry in script if entry.skipped]), ConcurrentStableList()
    applied = await apply_script(session, script)
    return len(fields), applied.built, applied.skipped, applied.failed


async def build_library(url: str, *, dry_run: bool) -> LibraryResult:
    """对单个租户库生成并执行补建列脚本（生成与执行分段；单条失败不中断）。

    Args:
        url: 租户库连接串。
        dry_run: 只扫描并输出脚本内容，不执行 DDL。

    Returns:
        LibraryResult: 本库结果。
    """
    engine = create_async_engine(url, poolclass=NullPool)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            scanned, built, skipped, failed = await build_in_session(session, dry_run=dry_run)
            return LibraryResult(url=_masked(url), scanned=scanned, built=built, skipped=skipped, failed=failed)
    finally:
        await engine.dispose()


async def run(args: argparse.Namespace) -> BuildResult:
    """执行补建列（按目标库逐个处理）。

    Args:
        args: 命令行参数。

    Returns:
        BuildResult: 汇总结果。
    """
    libraries: ConcurrentStableList[LibraryResult] = ConcurrentStableList()
    for url in await _target_urls(args):
        result = await build_library(url, dry_run=args.dry_run)
        libraries.add(result)
        print(
            f"[build_ext_columns] 库 {result.url} → 扫描 {result.scanned} / 建列 {result.built} / "
            f"命中 {result.skipped} / 失败 {len(result.failed)}"
        )
    return BuildResult(libraries=libraries)


def main(argv: ConcurrentStableList[str] | None = None) -> int:
    """入口。

    Args:
        argv: 命令行参数（None 取 `sys.argv`）。

    Returns:
        int: 退出码（全部成功 0；存在失败 1）。
    """
    args = build_parser().parse_args(argv)
    try:
        result = run_with_worker_id(lambda: run(args))
    except ConfigError as exc:
        print(f"[build_ext_columns] 失败：{exc}")
        return 1
    if result.failed:
        print(f"[build_ext_columns] 完成（含失败）：建列 {result.built}，失败 {result.failed}")
        return 1
    print(f"[build_ext_columns] 完成：建列 {result.built}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
