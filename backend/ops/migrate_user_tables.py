"""跨库数据搬迁：`sys_user` / `sys_account_lock`（org 服务租户库 → platform 服务租户库）（02_05）。

用法：

```bash
cd backend
uv run python -m ops.migrate_user_tables --dry-run                       # 清单预演（不建连）
uv run python -m ops.migrate_user_tables --code demo --code acme         # 指定租户搬迁
uv run python -m ops.migrate_user_tables --all-tenants                   # 租户取注册库未软删全集
uv run python -m ops.migrate_user_tables --url <源库> --target-url <目标库>   # 单库演练
```

- **背景（需求 07-10 用户（账号）归口平台）**：两表归属由 org 服务租户库改 platform 服务租户库；
  结构迁移由 Alembic 分链负责（platform 链 `0008_user_tables` 建表、org 链 `0006_drop_user_tables` 删表），
  本脚本只搬**数据**，与结构迁移分离、各自可独立重跑；
- **执行顺序（已部署环境·强制）**：① platform 链 `0008_user_tables`（建表）→ ② **本脚本**（搬数据）→
  ③ org 链 `0006_drop_user_tables`（删表）；顺序颠倒会丢数据；本地开发库直接重建，不走本脚本；
- **租户维度**：`--code`（可重复）显式指定，或 `--all-tenants` 从租户注册库（键 `platform_tenant`）
  读未软删租户编码；库名基经对照表 `sys_tenant_database.db_basis` 派生（缺对照行回落编码）；
- **搬迁口径**：按主键 `id` 逐行 upsert——目标已有同 `id` 行则更新，缺失则插入（**幂等**：
  重复执行更新数归 0）；源表不存在（已删 / 未建）按跳过处理；
- **源 / 目标库定位**：源为 `tenant_org_{db_basis}`、目标为 `tenant_platform_{db_basis}`；
  单库演练经 `--url` + `--target-url`（二者须同时给出）；
- **失败不中断**：单租户失败记 ERROR 并继续下一租户，末尾汇总；存在失败时退出码 1（幂等可重跑）；
- **`--dry-run`**：仅打印清单（连接串脱敏），不建连、不搬迁。
"""

import argparse
import asyncio
from dataclasses import dataclass
from typing import cast

from sqlalchemy import Connection, Engine, Table, create_engine, inspect, select, update
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.config import Settings, get_settings
from bms_core.core.exceptions import ConfigError
from bms_core.core.objects import BaseValueObject
from bms_core.db.engine import EngineFactory
from bms_core.db.keys import build_platform_db_key, build_tenant_db_key
from bms_core.db.sync import is_sync_only_url
from bms_core.db.tenant_source import TENANT_SERVICE_KEY
from bms_platform.models.user import SysAccountLock, SysUser
from ops.migrate_tenants import TenantRef, enrich_refs, tenant_refs

SOURCE_SERVICE = "org"
"""源服务标识（两表原归属服务）。"""

TARGET_SERVICE = "platform"
"""目标服务标识（两表终态归属服务）。"""

TABLES: tuple[tuple[str, Table], ...] = (
    ("sys_user", cast("Table", SysUser.__table__)),
    ("sys_account_lock", cast("Table", SysAccountLock.__table__)),
)
"""搬迁表清单（表名 + Core `Table`；结构两库一致，同一元数据读写两侧）。"""


@dataclass(frozen=True)
class MoveOutcome(BaseValueObject):
    """单租户搬迁结果（新增 / 更新行数）。"""

    created: int
    """目标库插入行数。"""

    updated: int
    """目标库更新行数。"""


def build_parser() -> argparse.ArgumentParser:
    """构建命令行解析器。

    Returns:
        argparse.ArgumentParser: 解析器。
    """
    parser = argparse.ArgumentParser(description="跨库数据搬迁：用户 / 账号锁定两表（org → platform；幂等）")
    parser.add_argument("--code", action="append", default=[], help="租户编码（可重复）")
    parser.add_argument("--all-tenants", action="store_true", help="租户取注册库（platform_tenant）未软删全集")
    parser.add_argument("--url", default="", help="单库演练：源 org 租户库连接串（须与 --target-url 同给）")
    parser.add_argument("--target-url", default="", help="单库演练：目标 platform 租户库连接串")
    parser.add_argument("--dry-run", action="store_true", help="仅打印清单（不建连、不搬迁）")
    return parser


def _masked(url: str) -> str:
    """连接串脱敏（隐藏密码）。

    Args:
        url: 连接串。

    Returns:
        str: 脱敏连接串。
    """
    return make_url(url).render_as_string(hide_password=True)


def _sync_has_table(connection: Connection, name: str) -> bool:
    """同步连接上判定表是否存在（经 `run_sync` 在异步连接上复用）。

    Args:
        connection: 同步连接。
        name: 表名。

    Returns:
        bool: 存在 True。
    """
    return inspect(connection).has_table(name)


async def _has_table(connection: AsyncConnection, name: str) -> bool:
    """异步连接上判定表是否存在。

    Args:
        connection: 异步连接。
        name: 表名。

    Returns:
        bool: 存在 True。
    """
    return await connection.run_sync(_sync_has_table, name)


async def _copy_table_async(source: AsyncConnection, target: AsyncConnection) -> MoveOutcome:
    """异步方言搬迁两表（SQLite / MySQL / PostgreSQL）。

    Args:
        source: 源 org 租户库连接。
        target: 目标 platform 租户库连接（事务由调用方管理）。

    Returns:
        MoveOutcome: 单租户搬迁结果。
    """
    created, updated = 0, 0
    for name, table in TABLES:
        if not await _has_table(source, name):
            continue
        rows = (await source.execute(select(table))).mappings().all()
        existing = set((await target.execute(select(table.c.id))).scalars().all())
        for row in rows:
            data = dict(row)
            if data["id"] in existing:
                await target.execute(update(table).where(table.c.id == data["id"]).values(**data))
                updated += 1
            else:
                await target.execute(table.insert().values(**data))
                created += 1
    return MoveOutcome(created=created, updated=updated)


def _copy_table_sync(source: Connection, target: Connection) -> MoveOutcome:
    """同步方言搬迁两表（达梦等无异步驱动）。

    Args:
        source: 源 org 租户库连接。
        target: 目标 platform 租户库连接（事务由调用方管理）。

    Returns:
        MoveOutcome: 单租户搬迁结果。
    """
    created, updated = 0, 0
    inspector = inspect(source)
    for name, table in TABLES:
        if not inspector.has_table(name):
            continue
        rows = [dict(row) for row in source.execute(select(table)).mappings().all()]
        existing = set(target.execute(select(table.c.id)).scalars().all())
        for data in rows:
            if data["id"] in existing:
                target.execute(update(table).where(table.c.id == data["id"]).values(**data))
                updated += 1
            else:
                target.execute(table.insert().values(**data))
                created += 1
    return MoveOutcome(created=created, updated=updated)


async def _move_async(source_url: str, target_url: str) -> MoveOutcome:
    """异步路径：开双连接并在单事务内搬两表。

    Args:
        source_url: 源连接串。
        target_url: 目标连接串。

    Returns:
        MoveOutcome: 单租户搬迁结果。
    """
    source: AsyncEngine = create_async_engine(source_url, poolclass=NullPool)
    target: AsyncEngine = create_async_engine(target_url, poolclass=NullPool)
    try:
        async with source.connect() as src, target.begin() as tgt:
            return await _copy_table_async(src, tgt)
    finally:
        await source.dispose()
        await target.dispose()


def _move_sync(source_url: str, target_url: str) -> MoveOutcome:
    """同步路径：开双连接并在单事务内搬两表。

    Args:
        source_url: 源连接串。
        target_url: 目标连接串。

    Returns:
        MoveOutcome: 单租户搬迁结果。
    """
    source: Engine = create_engine(source_url, poolclass=NullPool)
    target: Engine = create_engine(target_url, poolclass=NullPool)
    try:
        with source.connect() as src, target.begin() as tgt:
            return _copy_table_sync(src, tgt)
    finally:
        source.dispose()
        target.dispose()


async def move_tenant(source_url: str, target_url: str) -> MoveOutcome:
    """搬迁单个租户的两表数据（按方言选异步 / 同步路径）。

    Args:
        source_url: 源 org 租户库连接串。
        target_url: 目标 platform 租户库连接串。

    Returns:
        MoveOutcome: 单租户搬迁结果。
    """
    if is_sync_only_url(source_url):
        return await asyncio.to_thread(_move_sync, source_url, target_url)
    return await _move_async(source_url, target_url)


async def _resolve_refs(args: argparse.Namespace, factory: EngineFactory) -> ConcurrentStableList[TenantRef]:
    """解析租户维度（`--code` 显式，或 `--all-tenants` 读租户注册库）。

    Args:
        args: 命令行参数。
        factory: 引擎工厂（运维通道）。

    Returns:
        ConcurrentStableList[TenantRef]: 租户引用列表（保序去重）。

    Raises:
        ConfigError: 租户维度缺失或租户注册库不可读。
    """
    codes = ConcurrentStableList(dict.fromkeys(args.code))
    refs = ConcurrentStableList(TenantRef(code=code, db_basis=code) for code in codes)
    registry_url = factory.resolved_url(build_platform_db_key(TENANT_SERVICE_KEY))
    if refs:
        refs = await enrich_refs(refs, registry_url)
    if not refs and args.all_tenants:
        try:
            refs = await tenant_refs(registry_url)
        except Exception as exc:
            raise ConfigError(
                f"租户注册库不可读（请先建库并迁移 + 种子 ops.seed_tenant，或改用 --code）：{exc}"
            ) from exc
        if not refs:
            print("[migrate_user_tables] 租户注册库未注册租户（sys_tenant 为空）")
    if not refs:
        raise ConfigError("需 --code（可重复）或 --all-tenants 指定租户")
    return refs


def _pairs(
    args: argparse.Namespace, factory: EngineFactory, refs: ConcurrentStableList[TenantRef]
) -> ConcurrentStableList[tuple[str, str, str]]:
    """构造「租户编码 → (源 / 目标) 连接串」清单。

    Args:
        args: 命令行参数。
        factory: 引擎工厂（运维通道）。
        refs: 租户引用列表。

    Returns:
        ConcurrentStableList[tuple[str, str, str]]: `(租户编码, 源连接串, 目标连接串)` 列表。
    """
    if args.url and args.target_url:
        code = refs[0].code if refs else "drill"
        return ConcurrentStableList([(code, args.url, args.target_url)])
    pairs: ConcurrentStableList[tuple[str, str, str]] = ConcurrentStableList()
    for ref in refs:
        source_url = factory.resolved_url(build_tenant_db_key(ref.db_basis, service=SOURCE_SERVICE))
        target_url = factory.resolved_url(build_tenant_db_key(ref.db_basis, service=TARGET_SERVICE))
        pairs.add((ref.code, source_url, target_url))
    return pairs


async def run(args: argparse.Namespace) -> int:
    """执行跨库搬迁（幂等；单租户失败不中断）。

    Args:
        args: 命令行参数。

    Returns:
        int: 退出码（0 成功 / 1 存在失败）。

    Raises:
        ConfigError: 单库演练参数不成对 / 租户维度缺失。
    """
    if bool(args.url) != bool(args.target_url):
        raise ConfigError("单库演练需 `--url` 与 `--target-url` 同时给出")
    settings: Settings = get_settings()
    factory = EngineFactory(settings, allow_cross_service=True)  # 运维通道：跨服务库键
    drill = bool(args.url and args.target_url)
    refs: ConcurrentStableList[TenantRef] = ConcurrentStableList() if drill else await _resolve_refs(args, factory)
    pairs = _pairs(args, factory, refs)
    print(f"[migrate_user_tables] 待搬迁 {len(pairs)} 个租户（{SOURCE_SERVICE} → {TARGET_SERVICE}）")
    for code, source_url, target_url in pairs:
        print(f"[migrate_user_tables] 租户 {code:<12} {_masked(source_url)} → {_masked(target_url)}")
    if args.dry_run:
        print("[migrate_user_tables] dry-run：不建连、不搬迁")
        return 0
    succeeded: ConcurrentStableList[str] = ConcurrentStableList()
    failed: ConcurrentStableList[str] = ConcurrentStableList()
    created_total = 0
    updated_total = 0
    for code, source_url, target_url in pairs:
        try:
            outcome = await move_tenant(source_url, target_url)
        except Exception as exc:  # 单租户失败不中断整批
            failed.add(code)
            print(f"[migrate_user_tables] 租户 {code} → 失败：{type(exc).__name__}: {exc}")
            continue
        succeeded.add(code)
        created_total += outcome.created
        updated_total += outcome.updated
        print(f"[migrate_user_tables] 租户 {code} → 新增 {outcome.created} 行 / 更新 {outcome.updated} 行")
    print(
        f"[migrate_user_tables] 汇总：成功 {len(succeeded)}、失败 {len(failed)}；"
        f"新增 {created_total} 行 / 更新 {updated_total} 行" + (f"（失败：{', '.join(failed)}）" if failed else "")
    )
    return 1 if failed else 0


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
        print(f"[migrate_user_tables] 失败：{exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
