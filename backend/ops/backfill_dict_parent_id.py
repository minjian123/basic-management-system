"""字典条目上级 ID 回填（02_07）：`sys_dict_item.parent_id` 由「父条目 `value`」改为「父条目 `id`」。

用法：

```bash
cd backend
uv run python -m ops.backfill_dict_parent_id --dry-run              # 计划预演（不建连）
uv run python -m ops.backfill_dict_parent_id                        # 全部注册租户（platform 服务租户库）
uv run python -m ops.backfill_dict_parent_id --code demo --code acme  # 仅指定租户（可重复）
```

- **执行序（停机窗口一次性）**：全库备份 → **本脚本** → `alembic -n alembic:platform:tenant upgrade head`
  （列类型改 `BIGINT`）→ 代码上线 → 字典缓存版本 bump（全局版本键 `INCR`，见 02_07 详细设计）→ 冒烟；
- **目标**：`platform` 服务各**租户库**（`bms_platform_{db_basis}`）的 `sys_dict_item`——按 `type_id` 分组把
  `parent_id`（父条目 `value`）改写为父条目 `id` 的十进制字符串；
- **幂等**：`parent_id` 已是十进制数字的行跳过；重复执行输出 0 变更；
- **悬空处理**：父 `value` 在同类型内无对应条目 → 置 `NULL`（顶层）并计入明细——保证改列型前列内无非数字值；
- **缺库容错**：目标库不可达 / 未建 → 记 WARNING 跳过，不阻断整批；
- **不写结构**：本脚本只改数据，列类型变更由 Alembic 迁移（`0010_dict_item_parent_id_bigint`）负责。
"""

import argparse
import asyncio
from dataclasses import dataclass

from sqlalchemy import Connection, create_engine, inspect, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.config import get_settings
from bms_core.core.exceptions import ConfigError
from bms_core.core.objects import BaseValueObject
from bms_core.db.engine import EngineFactory
from bms_core.db.keys import build_platform_db_key, build_tenant_db_key
from bms_core.db.tenant_source import TENANT_SERVICE_KEY

_DM = "dm"
_SERVICE = "platform"
"""字典表归属服务（`sys_dict_*` 在 platform 服务的租户库）。"""

_ITEM_TABLE = "sys_dict_item"
"""目标表名。"""


@dataclass(frozen=True)
class TenantRecord(BaseValueObject):
    """注册租户（编码 / 库名基 / 雪花主键）。"""

    code: str
    db_basis: str
    tenant_id: int


@dataclass
class BackfillStats:
    """单库回填统计（扫描 / 更新行数 + 悬空明细）。"""

    scanned: int = 0
    updated: int = 0
    unresolved: tuple[str, ...] = ()

    def merge(self, other: BackfillStats) -> None:
        """合并另一统计。

        Args:
            other: 另一统计。
        """
        self.scanned += other.scanned
        self.updated += other.updated
        self.unresolved = (*self.unresolved, *other.unresolved)


def build_parser() -> argparse.ArgumentParser:
    """构建命令行解析器。

    Returns:
        argparse.ArgumentParser: 解析器。
    """
    parser = argparse.ArgumentParser(description="字典条目上级 ID 回填（父 value → 父 id；幂等）")
    parser.add_argument("--code", action="append", default=[], help="租户编码（可重复；缺省全部注册租户）")
    parser.add_argument("--dry-run", action="store_true", help="仅打印计划（不建连、不写数据）")
    return parser


def _masked(url: str) -> str:
    """连接串脱敏（隐藏密码）。

    Args:
        url: 连接串。

    Returns:
        str: 脱敏连接串。
    """
    return make_url(url).render_as_string(hide_password=True)


def _item_value_key(type_id: object, value: object) -> str:
    """拼条目在同类型内的查键（`{type_id}:{value}`）。

    Args:
        type_id: 字典类型 ID。
        value: 条目 value。

    Returns:
        str: 查键。
    """
    return f"{type_id}:{value}"


def backfill_items(connection: Connection) -> BackfillStats:
    """回填 `sys_dict_item.parent_id`（父 `value` → 父 `id`；悬空置 NULL）。

    Args:
        connection: 同步连接（platform 服务租户库）。

    Returns:
        BackfillStats: 统计（`unresolved` 为置 NULL 明细）。
    """
    stats = BackfillStats()
    if _ITEM_TABLE not in inspect(connection).get_table_names():
        return stats
    rows = connection.execute(text(f"SELECT id, type_id, value FROM {_ITEM_TABLE}")).all()
    id_by_value: ConcurrentStableDict[str, int] = ConcurrentStableDict()
    for row_id, type_id, value in rows:
        id_by_value.set(_item_value_key(type_id, value), int(row_id))
    targets = connection.execute(
        text(f"SELECT id, type_id, parent_id FROM {_ITEM_TABLE} WHERE parent_id IS NOT NULL")
    ).all()
    for row_id, type_id, parent_id in targets:
        stats.scanned += 1
        parent_value = str(parent_id)
        if parent_value.isdigit():
            continue
        parent_row_id = id_by_value.get(_item_value_key(type_id, parent_value))
        if parent_row_id is None:
            stats.unresolved = (*stats.unresolved, f"{_ITEM_TABLE}(id={row_id}).parent_id = {parent_value!r}")
            connection.execute(
                text(f"UPDATE {_ITEM_TABLE} SET parent_id = NULL WHERE id = :id"),
                ConcurrentStableDict({"id": row_id}),
            )
        else:
            connection.execute(
                text(f"UPDATE {_ITEM_TABLE} SET parent_id = :parent_id WHERE id = :id"),
                ConcurrentStableDict({"parent_id": str(parent_row_id), "id": row_id}),
            )
        stats.updated += 1
    return stats


def _tenant_records_sync(url: str) -> ConcurrentStableList[TenantRecord]:
    """同步读注册租户（达梦等无异步方言驱动；`code` / `db_basis` / `id`）。

    Args:
        url: 租户注册库连接串。

    Returns:
        ConcurrentStableList[TenantRecord]: 注册租户列表。
    """
    from bms_tenant.models.tenant import SysTenant  # 惰性：仅读租户注册库时需要
    from bms_tenant.models.tenant_database import SysTenantDatabase

    engine = create_engine(url, poolclass=NullPool)
    try:
        with engine.connect() as connection:
            statement = (
                select(SysTenant.code, SysTenant.id, SysTenantDatabase.db_basis)
                .outerjoin(
                    SysTenantDatabase,
                    (SysTenantDatabase.tenant_id == SysTenant.id) & (SysTenantDatabase.deleted_at.is_(None)),
                )
                .where(SysTenant.deleted_at.is_(None))
            )
            return ConcurrentStableList(
                _record(code, tenant_id, basis) for code, tenant_id, basis in connection.execute(statement).all()
            )
    finally:
        engine.dispose()


def _record(code: object, tenant_id: object, db_basis: object) -> TenantRecord:
    """行值 → 注册租户记录（库名基缺行回落编码）。

    Args:
        code: 租户编码。
        tenant_id: 雪花主键。
        db_basis: 库名基（可空）。

    Returns:
        TenantRecord: 注册租户记录。
    """
    basis = str(db_basis) if isinstance(db_basis, str) and db_basis else str(code)
    return TenantRecord(code=str(code), db_basis=basis, tenant_id=int(str(tenant_id)))


async def tenant_records(registry_url: str) -> ConcurrentStableList[TenantRecord]:
    """读注册租户（达梦走同步驱动线程）。

    Args:
        registry_url: 租户注册库连接串。

    Returns:
        ConcurrentStableList[TenantRecord]: 注册租户列表。
    """
    if make_url(registry_url).get_backend_name() == _DM:
        return await asyncio.to_thread(_tenant_records_sync, registry_url)
    from bms_tenant.models.tenant import SysTenant  # 惰性：仅读租户注册库时需要
    from bms_tenant.models.tenant_database import SysTenantDatabase

    engine = create_async_engine(registry_url, poolclass=NullPool)
    try:
        async with engine.connect() as connection:
            statement = (
                select(SysTenant.code, SysTenant.id, SysTenantDatabase.db_basis)
                .outerjoin(
                    SysTenantDatabase,
                    (SysTenantDatabase.tenant_id == SysTenant.id) & (SysTenantDatabase.deleted_at.is_(None)),
                )
                .where(SysTenant.deleted_at.is_(None))
            )
            result = await connection.execute(statement)
            return ConcurrentStableList(_record(code, tenant_id, basis) for code, tenant_id, basis in result.all())
    finally:
        await engine.dispose()


async def _load_records(registry_url: str) -> ConcurrentStableList[TenantRecord]:
    """读注册租户（不可读即明确报错）。

    Args:
        registry_url: 租户注册库连接串。

    Returns:
        ConcurrentStableList[TenantRecord]: 注册租户列表。

    Raises:
        ConfigError: 注册库不可读。
    """
    try:
        return await tenant_records(registry_url)
    except Exception as exc:
        raise ConfigError(f"租户注册库不可读：{type(exc).__name__}: {exc}") from exc


def _run_sync(url: str) -> BackfillStats:
    """同步执行单库回填（达梦；SQLite 演练）。

    Args:
        url: 目标库连接串。

    Returns:
        BackfillStats: 统计。
    """
    engine = create_engine(url, poolclass=NullPool)
    try:
        with engine.begin() as connection:
            return backfill_items(connection)
    finally:
        engine.dispose()


async def run_database(url: str) -> BackfillStats:
    """执行单库回填（非达梦走异步引擎，经 `run_sync` 复用同步逻辑）。

    Args:
        url: 目标库连接串。

    Returns:
        BackfillStats: 统计。
    """
    if make_url(url).get_backend_name() == _DM:
        return await asyncio.to_thread(_run_sync, url)
    engine = create_async_engine(url, poolclass=NullPool)
    try:
        async with engine.begin() as connection:
            return await connection.run_sync(backfill_items)
    finally:
        await engine.dispose()


async def run(args: argparse.Namespace) -> int:
    """执行回填（全部注册租户的平台服务租户库；单库失败不中断）。

    Args:
        args: 命令行参数。

    Returns:
        int: 退出码（0 成功）。
    """
    settings = get_settings()
    factory = EngineFactory(settings, allow_cross_service=True)  # 运维通道：按各服务租户库执行
    records = await _load_records(factory.resolved_url(build_platform_db_key(TENANT_SERVICE_KEY)))
    wanted = set(args.code)
    selected = [record for record in records if not wanted or record.code in wanted]
    if wanted and len({record.code for record in selected}) != len(wanted):
        missing = sorted(wanted - {record.code for record in selected})
        raise ConfigError(f"注册库未找到租户：{', '.join(missing)}")

    targets: ConcurrentStableList[tuple[str, str]] = ConcurrentStableList()
    for record in selected:
        key = build_tenant_db_key(record.db_basis, service=_SERVICE)
        targets.add((key, factory.resolved_url(key)))

    print(f"[backfill_dict_parent_id] 目标 {len(targets)} 个租户库（租户 {len(selected)} 个）")
    if args.dry_run:
        for key, url in targets:
            print(f"[backfill_dict_parent_id] {key:<28} {_masked(url)}（dry-run）")
        print("[backfill_dict_parent_id] dry-run：不写数据（枚举租户已读注册库）")
        return 0

    total = BackfillStats()
    skipped = 0
    for key, url in targets:
        try:
            stats = await run_database(url)
        except Exception as exc:  # 缺库 / 不可达：记 WARNING 跳过（不阻断整批）
            skipped += 1
            print(f"[backfill_dict_parent_id] {key} → 跳过（{type(exc).__name__}: {exc}）")
            continue
        total.merge(stats)
        for detail in stats.unresolved:
            print(f"[backfill_dict_parent_id] {key} → 置 NULL：{detail}")
        print(f"[backfill_dict_parent_id] {key} → 扫描 {stats.scanned}、更新 {stats.updated}")
    print(
        f"[backfill_dict_parent_id] 汇总：更新 {total.updated} 行、置 NULL {len(total.unresolved)} 行、"
        f"跳过 {skipped} 库"
    )
    return 0


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
        print(f"[backfill_dict_parent_id] 失败：{exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
