"""存量租户列回填（10_04）：`code → 雪花 id`（结构与数据分离；列类型迁移前一次性执行）。

用法：

```bash
cd backend
uv run python -m ops.backfill_tenant_id_columns --dry-run                 # 计划预演（不建连）
uv run python -m ops.backfill_tenant_id_columns                           # 全部库（启用服务 × 租户）
uv run python -m ops.backfill_tenant_id_columns --service identity        # 仅指定服务（可重复）
uv run python -m ops.backfill_tenant_id_columns --code demo --code acme   # 仅指定租户
```

- **执行序（停机窗口一次性，10_01 §7）**：全库备份 → **本脚本** → `ops.migrate_tenants`（列类型
  改 `BIGINT`）→ 代码上线 → 冒烟；空库 / 新建库场景本脚本为空操作；
- **映射源**：租户注册库（键 `platform_tenant`）`sys_tenant`（未软删）`code → id`；注册库不可读即失败；
- **目标**：
  - `sys_user_identity`（identity 服务**平台库**）：`tenant_id` code→id、`idp_key` 前缀
    `{code}`→`{id}`；**不可解析即报错中止并列出明细**（列非空，不可置 NULL）；
  - `sys_outbox` / `sys_event_dead_letter`（各服务**平台库** + 各服务**租户库**）：`tenant_id`
    code→id；平台库不可解析的租户位按 10_01 §7.2 **置 NULL**（不阻断），租户库不可解析即报错中止；
- **幂等**：已是十进制 id 的行跳过；重复执行输出 0 变更；
- **缺库容错**：目标库不可达 / 未建（如尚未开通的服务库）→ 记 WARNING 跳过，不阻断整批；
- **不写结构**：本脚本只改数据，列类型变更由 Alembic 迁移负责。
"""

import argparse
import asyncio
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from sqlalchemy import Connection, create_engine, inspect, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from bms_core.core.config import get_settings
from bms_core.core.exceptions import ConfigError
from bms_core.core.objects import BaseValueObject
from bms_core.db.engine import EngineFactory
from bms_core.db.keys import build_platform_db_key, build_tenant_db_key
from bms_core.db.tenant_source import TENANT_SERVICE_KEY
from bms_core.services.module_registry import enabled_service_keys

_DM = "dm"
_OUTBOX_TABLES = ("sys_outbox", "sys_event_dead_letter")


@dataclass(frozen=True)
class TenantRecord(BaseValueObject):
    """注册租户（编码 / 库名基 / 雪花主键）。"""

    code: str
    db_basis: str
    tenant_id: int


@dataclass
class BackfillStats:
    """单库回填统计（扫描 / 更新行数）。"""

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


class BackfillError(ConfigError):
    """存量行不可解析（报错中止；明细在消息内）。"""


def build_parser() -> argparse.ArgumentParser:
    """构建命令行解析器。

    Returns:
        argparse.ArgumentParser: 解析器。
    """
    parser = argparse.ArgumentParser(description="存量租户列回填（code → 雪花 id；幂等）")
    parser.add_argument("--service", action="append", default=[], help="服务标识（可重复；缺省全部启用服务）")
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


def _is_id(value: object) -> bool:
    """判断值是否已是雪花 id 十进制字符串。

    Args:
        value: 待判断值。

    Returns:
        bool: 是否十进制数字串。
    """
    return isinstance(value, str) and value.isdigit()


def _resolve_code(value: str, id_map: Mapping[str, int], *, detail: str) -> int:
    """按编码取租户 id（不可解析抛 `BackfillError`）。

    Args:
        value: 租户编码（原值）。
        id_map: `code → id` 映射。
        detail: 明细描述（表 / 主键 / 字段）。

    Returns:
        int: 租户主键。

    Raises:
        BackfillError: 编码无法映射（含软删除租户）。
    """
    tenant_id = id_map.get(value)
    if tenant_id is None:
        raise BackfillError(f"存量行不可解析：{detail} = {value!r}（注册库无该未软删租户）")
    return tenant_id


def _update_row(connection: Connection, statement: str, params: Mapping[str, object]) -> None:
    """执行单行更新。

    Args:
        connection: 同步连接。
        statement: 参数化 SQL。
        params: 绑定参数。
    """
    connection.execute(text(statement), params)


def backfill_user_identity(connection: Connection, id_map: Mapping[str, int]) -> BackfillStats:
    """回填 `sys_user_identity`（`tenant_id` 与 `idp_key` 前缀；不可解析中止）。

    Args:
        connection: 同步连接（identity 平台库）。
        id_map: `code → id` 映射。

    Returns:
        BackfillStats: 统计。

    Raises:
        BackfillError: 存在不可解析行（明细列于消息）。
    """
    stats = BackfillStats()
    rows = connection.execute(
        text("SELECT id, idp_key, tenant_id FROM sys_user_identity WHERE deleted_at IS NULL")
    ).all()
    for row_id, idp_key, tenant_id in rows:
        stats.scanned += 1
        prefix, separator, provider_key = str(idp_key).partition(":")
        old_tenant_id = int(tenant_id) if _is_id(tenant_id) else None
        new_tenant_id = (
            old_tenant_id
            if old_tenant_id is not None
            else _resolve_code(str(tenant_id), id_map, detail=f"sys_user_identity(id={row_id}).tenant_id")
        )
        if _is_id(prefix):
            new_key = str(idp_key)
        else:
            mapped = _resolve_code(prefix, id_map, detail=f"sys_user_identity(id={row_id}).idp_key")
            new_key = f"{mapped}{separator}{provider_key}"
        if old_tenant_id != new_tenant_id or new_key != idp_key:
            _update_row(
                connection,
                "UPDATE sys_user_identity SET tenant_id = :tenant_id, idp_key = :idp_key WHERE id = :id",
                {"tenant_id": new_tenant_id, "idp_key": new_key, "id": row_id},
            )
            stats.updated += 1
    return stats


def backfill_outbox(connection: Connection, id_map: Mapping[str, int], *, strict: bool) -> BackfillStats:
    """回填发件箱 / 死信 `tenant_id`（严格模式不可解析中止；否则置 NULL）。

    Args:
        connection: 同步连接。
        id_map: `code → id` 映射。
        strict: 严格模式（租户库：不可解析即中止）；False（平台库：不可解析置 NULL）。

    Returns:
        BackfillStats: 统计（`unresolved` 为置 NULL 明细，仅非严格模式）。

    Raises:
        BackfillError: 严格模式下存在不可解析行。
    """
    stats = BackfillStats()
    tables = [name for name in _OUTBOX_TABLES if name in inspect(connection).get_table_names()]
    for table in tables:
        rows = connection.execute(text(f"SELECT id, tenant_id FROM {table} WHERE tenant_id IS NOT NULL")).all()
        for row_id, tenant_id in rows:
            stats.scanned += 1
            if _is_id(tenant_id):
                continue
            new_value = id_map.get(str(tenant_id))
            if new_value is None:
                detail = f"{table}(id={row_id}).tenant_id = {tenant_id!r}"
                if strict:
                    raise BackfillError(f"存量行不可解析：{detail}")
                stats.unresolved = (*stats.unresolved, detail)
                _update_row(
                    connection,
                    f"UPDATE {table} SET tenant_id = NULL WHERE id = :id",
                    {"id": row_id},
                )
            else:
                _update_row(
                    connection,
                    f"UPDATE {table} SET tenant_id = :tenant_id WHERE id = :id",
                    {"tenant_id": new_value, "id": row_id},
                )
            stats.updated += 1
    return stats


def process_database(
    connection: Connection,
    id_map: Mapping[str, int],
    *,
    with_identity: bool,
    strict: bool,
) -> BackfillStats:
    """处理单个库（按表存在性回填；identity 平台库另处理映射表）。

    Args:
        connection: 同步连接。
        id_map: `code → id` 映射。
        with_identity: 是否处理 `sys_user_identity`（identity 平台库）。
        strict: 发件箱 / 死信严格模式（租户库）。

    Returns:
        BackfillStats: 统计。
    """
    stats = BackfillStats()
    if with_identity and "sys_user_identity" in inspect(connection).get_table_names():
        stats.merge(backfill_user_identity(connection, id_map))
    stats.merge(backfill_outbox(connection, id_map, strict=strict))
    return stats


def _tenant_records_sync(url: str) -> Sequence[TenantRecord]:
    """同步读注册租户（达梦等无异步方言驱动；`code` / `db_basis` / `id`）。

    Args:
        url: 租户注册库连接串。

    Returns:
        list[TenantRecord]: 注册租户列表。
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
            return [_record(code, tenant_id, basis) for code, tenant_id, basis in connection.execute(statement).all()]
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


async def tenant_records(registry_url: str) -> Sequence[TenantRecord]:
    """读注册租户（达梦走同步驱动线程）。

    Args:
        registry_url: 租户注册库连接串。

    Returns:
        list[TenantRecord]: 注册租户列表。
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
            return [_record(code, tenant_id, basis) for code, tenant_id, basis in result.all()]
    finally:
        await engine.dispose()


async def _load_records(registry_url: str) -> Sequence[TenantRecord]:
    """读注册租户（不可读即明确报错）。

    Args:
        registry_url: 租户注册库连接串。

    Returns:
        list[TenantRecord]: 注册租户列表。

    Raises:
        ConfigError: 注册库不可读。
    """
    try:
        return await tenant_records(registry_url)
    except Exception as exc:
        raise ConfigError(f"租户注册库不可读：{type(exc).__name__}: {exc}") from exc


def _run_sync(url: str, id_map: Mapping[str, int], *, with_identity: bool, strict: bool) -> BackfillStats:
    """同步执行单库回填（达梦；SQLite 演练）。

    Args:
        url: 目标库连接串。
        id_map: `code → id` 映射。
        with_identity: 是否处理 `sys_user_identity`。
        strict: 发件箱 / 死信严格模式。

    Returns:
        BackfillStats: 统计。
    """
    engine = create_engine(url, poolclass=NullPool)
    try:
        with engine.begin() as connection:
            return process_database(connection, id_map, with_identity=with_identity, strict=strict)
    finally:
        engine.dispose()


async def run_database(url: str, id_map: Mapping[str, int], *, with_identity: bool, strict: bool) -> BackfillStats:
    """执行单库回填（非达梦走异步引擎，经 `run_sync` 复用同步逻辑）。

    Args:
        url: 目标库连接串。
        id_map: `code → id` 映射。
        with_identity: 是否处理 `sys_user_identity`。
        strict: 发件箱 / 死信严格模式。

    Returns:
        BackfillStats: 统计。
    """
    if make_url(url).get_backend_name() == _DM:
        return await asyncio.to_thread(_run_sync, url, id_map, with_identity=with_identity, strict=strict)
    engine = create_async_engine(url, poolclass=NullPool)
    try:
        async with engine.begin() as connection:
            return await connection.run_sync(
                lambda sync_connection: process_database(
                    sync_connection, id_map, with_identity=with_identity, strict=strict
                )
            )
    finally:
        await engine.dispose()


async def run(args: argparse.Namespace) -> int:
    """执行回填（全部目标库；单库失败不中断，不可解析即中止）。

    Args:
        args: 命令行参数。

    Returns:
        int: 退出码（0 成功 / 1 存在失败或不可解析）。
    """
    settings = get_settings()
    factory = EngineFactory(settings, allow_cross_service=True)  # 运维通道：按各服务库执行
    services = tuple(dict.fromkeys(args.service)) or enabled_service_keys()
    if not services:
        raise ConfigError("服务目录无已启用服务，请显式 --service")

    records = await _load_records(factory.resolved_url(build_platform_db_key(TENANT_SERVICE_KEY)))
    wanted = set(args.code)
    selected = [record for record in records if not wanted or record.code in wanted]
    if wanted and len({record.code for record in selected}) != len(wanted):
        missing = sorted(wanted - {record.code for record in selected})
        raise ConfigError(f"注册库未找到租户：{', '.join(missing)}")
    id_map = {record.code: record.tenant_id for record in selected}

    targets: list[tuple[str, str, bool, bool]] = []
    for service in services:
        platform_key = build_platform_db_key(service)
        targets.append((platform_key, factory.resolved_url(platform_key), service == "identity", False))
    for service in services:
        for record in selected:
            key = build_tenant_db_key(record.db_basis, service=service)
            targets.append((key, factory.resolved_url(key), False, True))

    print(f"[backfill_tenant_id_columns] 目标 {len(targets)} 个库（服务 {len(services)} 个 / 租户 {len(selected)} 个）")
    if args.dry_run:
        for key, url, with_identity, strict in targets:
            mode = "identity+发件箱" if with_identity else ("租户库" if strict else "平台库")
            print(f"[backfill_tenant_id_columns] {key:<28} {mode:<12} {_masked(url)}（dry-run）")
        print("[backfill_tenant_id_columns] dry-run：不写数据（枚举租户已读注册库）")
        return 0

    total = BackfillStats()
    skipped = 0
    for key, url, with_identity, strict in targets:
        try:
            stats = await run_database(url, id_map, with_identity=with_identity, strict=strict)
        except BackfillError:
            raise
        except Exception as exc:  # 缺库 / 不可达：记 WARNING 跳过（不阻断整批）
            skipped += 1
            print(f"[backfill_tenant_id_columns] {key} → 跳过（{type(exc).__name__}: {exc}）")
            continue
        total.merge(stats)
        for detail in stats.unresolved:
            print(f"[backfill_tenant_id_columns] {key} → 置 NULL：{detail}")
        print(f"[backfill_tenant_id_columns] {key} → 扫描 {stats.scanned}、更新 {stats.updated}")
    print(
        f"[backfill_tenant_id_columns] 汇总：更新 {total.updated} 行、置 NULL {len(total.unresolved)} 行、"
        f"跳过 {skipped} 库"
    )
    return 0


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
    except (ConfigError, BackfillError) as exc:
        print(f"[backfill_tenant_id_columns] 失败：{exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
