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
from typing import cast

from sqlalchemy import select, update
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.config import get_settings
from bms_core.core.exceptions import ConfigError
from bms_core.core.objects import BaseValueObject
from bms_core.db.engine import EngineFactory
from bms_core.db.keys import build_platform_db_key, build_tenant_db_key
from bms_core.db.session import DbSession
from bms_core.db.tenant_source import TENANT_SERVICE_KEY
from bms_core.lock.null import NullDistributedLock
from bms_core.models.platform.form_design import (
    DDL_STATUS_ACTIVE,
    DDL_STATUS_FAILED,
    DDL_STATUS_PENDING,
    SysFieldExt,
)
from bms_platform.domains.form_design.services.ddl import FormDdlExecutor
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


async def build_library(url: str, *, dry_run: bool) -> LibraryResult:
    """对单个租户库补建列（幂等；单条失败不中断）。

    Args:
        url: 租户库连接串。
        dry_run: 只扫描不执行 DDL。

    Returns:
        LibraryResult: 本库结果。
    """
    engine = create_async_engine(url, poolclass=NullPool)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    built = 0
    skipped = 0
    failed: ConcurrentStableList[str] = ConcurrentStableList()
    try:
        async with factory() as session:
            fields = await _pending_fields(session)
            if dry_run:
                for field in fields:
                    print(
                        f"[build_ext_columns] 待建列 {field.form_code}.{field.field_key} → "
                        f"{field.table_name}.{field.column_name}（{field.type}）"
                    )
                return LibraryResult(url=_masked(url), scanned=len(fields), built=0, skipped=0, failed=failed)
            executor = FormDdlExecutor(cast("DbSession", session), lock=NullDistributedLock(), tenant=None)
            for field in fields:
                field_id = int(field.id)
                label = f"{field.form_code}.{field.field_key}"
                try:
                    outcome = await executor.add_column(field, comment=field.name)
                except Exception as exc:
                    await session.rollback()
                    await session.execute(
                        update(SysFieldExt).where(SysFieldExt.id == field_id).values(ddl_status=DDL_STATUS_FAILED)
                    )
                    await session.commit()
                    failed.add(f"{label}：{type(exc).__name__}: {exc}")
                    print(f"[build_ext_columns] 建列失败 {label}：{type(exc).__name__}: {exc}")
                    continue
                await session.execute(
                    update(SysFieldExt).where(SysFieldExt.id == field_id).values(ddl_status=DDL_STATUS_ACTIVE)
                )
                await session.commit()
                if outcome.created:
                    built += 1
                    print(f"[build_ext_columns] 建列 {label} → {outcome.column_name}")
                else:
                    skipped += 1
            return LibraryResult(url=_masked(url), scanned=len(fields), built=built, skipped=skipped, failed=failed)
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
