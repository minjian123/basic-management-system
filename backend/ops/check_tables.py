"""表归属登记校验（06_02）：离线断言 + 可选接库双向对账（CI 硬门禁）。

用法：

```bash
cd backend
uv run python -m ops.check_tables
uv run python -m ops.check_tables --url sqlite+aiosqlite:///./bms_platform.db
```

离线断言（不连库，零依赖）：

1. **清单自校验**：`TableOwnershipRegistry().validate()`（表名唯一与格式 / 归属与库类别合法 / 前缀归属一致）；
2. **模型表必登记**：各启用服务模型（按服务 `MODEL_MODULES` + 公共模型模块导入）的 `__tablename__`
   必须已登记（未登记即失败——防「模型落地却未进归属登记」）；
3. **enabled 表必入链**：`status = enabled` 的归属表必须出现在其归属服务 + 库类别对应链的
   `chain_tables` 中（派生自证 + 防漏；`*` 基础设施表跳过）；
4. **脚本表集不越界**：每条**有脚本**的链，其迁移脚本建表 / 改表的表名集合 ⊆ 该链 `chain_tables`。

接库（`--url`）：读平台服务库 `sys_table_ownership`（未软删行）与清单**双向对账**（缺行 / 清单外行 /
字段不符），只读不写；空库判失败（种子未执行）。

冲突 / 非法 → 打印明细并退出码 1；通过 → 退出码 0。
"""

import argparse
import asyncio
import re
from collections.abc import Sequence
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from bms_core.db.migration import (
    COMMON_MODEL_MODULES,
    DATASOURCES,
    VERSIONS_ROOT,
    import_models,
    resolve_chain,
    service_model_modules,
)
from bms_core.models.base import Base
from bms_core.models.ownership import SysTableOwnership
from bms_core.services.module_registry import enabled_service_keys
from bms_core.services.table_registry import (
    OWNER_EVERY_SERVICE,
    TABLE_OWNERSHIP,
    TableOwnershipRegistry,
    TableRecord,
    chain_tables,
    table_names,
    validate_table_ownership,
)

_CREATE_TABLE_RE = re.compile(r"op\.create_table\(\s*[\"']([a-z0-9_]+)[\"']")
_BATCH_TABLE_RE = re.compile(r"op\.batch_alter_table\(\s*[\"']([a-z0-9_]+)[\"']")
_DROP_TABLE_RE = re.compile(r"op\.drop_table\(\s*[\"']([a-z0-9_]+)[\"']")


def build_parser() -> argparse.ArgumentParser:
    """构建命令行解析器。

    Returns:
        argparse.ArgumentParser: 解析器。
    """
    parser = argparse.ArgumentParser(description="表归属登记校验（离线断言 + 可选接库对账）")
    parser.add_argument("--url", default="", help="平台服务库连接串（给定后追加接库对账；迁移 + 种子后执行）")
    return parser


def imported_model_tables() -> set[str]:
    """导入各启用服务与公共模型模块后取**已声明模块**的模型表名。

    只统计模块属于「公共模型清单 + 各服务 `MODEL_MODULES`」的模型（按 `__module__` 归属判定），
    以免测试或其他进程内临时模型（同进程共享 `Base.metadata`）干扰本断言。

    Returns:
        set[str]: 模型表名集合。
    """
    declared: set[str] = set(COMMON_MODEL_MODULES)
    for service in enabled_service_keys():
        import_models(service)
        declared.update(service_model_modules(service))

    tables: set[str] = set()
    for mapper in Base.registry.mappers:
        module = str(getattr(mapper.class_, "__module__", ""))
        if module in declared and mapper.local_table is not None:
            tables.add(str(mapper.local_table.name))
    return tables


def check_offline(*, versions_root: Path = VERSIONS_ROOT) -> list[str]:
    """离线校验：清单自校验 + 模型表必登记 + enabled 表必入链 + 脚本表集不越界。

    Args:
        versions_root: 版本目录根（自检可指定替身目录）。

    Returns:
        list[str]: 冲突 / 非法明细；空列表表示通过。
    """
    errors = TableOwnershipRegistry().validate()
    registered = table_names()
    modeled = imported_model_tables()

    for table in sorted(modeled - registered):
        errors.append(f"模型表未登记归属：{table}（须在 TABLE_OWNERSHIP 登记）")

    for record in TABLE_OWNERSHIP:
        if record.owner == OWNER_EVERY_SERVICE or record.status != "enabled":
            continue
        owned_chain = chain_tables(record.owner, record.datasource)
        if record.table_name not in owned_chain:
            errors.append(f"{record.table_name}：enabled 但未进入归属服务 {record.owner} 的 {record.datasource} 链")

    errors.extend(_check_script_tables(versions_root))
    return errors


def _check_script_tables(versions_root: Path) -> list[str]:
    """校验各链迁移脚本建表 / 改表的表名 ⊆ 该链派生表集（防脚本越界建表）。

    Args:
        versions_root: 版本目录根（`alembic/versions`）。

    Returns:
        list[str]: 违规明细。
    """
    errors: list[str] = []
    if not versions_root.is_dir():
        return errors
    for service_dir in sorted(versions_root.iterdir()):
        if not service_dir.is_dir() or service_dir.name.startswith("."):
            continue
        for datasource in DATASOURCES:
            location = service_dir / datasource
            if not location.is_dir():
                continue
            chain = resolve_chain(f"{service_dir.name}:{datasource}")
            for script in sorted(location.glob("*.py")):
                text = script.read_text(encoding="utf-8")
                names = set(_CREATE_TABLE_RE.findall(text))
                names |= set(_BATCH_TABLE_RE.findall(text)) - set(_DROP_TABLE_RE.findall(text))
                for name in sorted(names):
                    if name not in chain.tables:
                        errors.append(
                            f"{chain.name}/{script.name}：建表 / 改表 {name} 不在该链派生表集内"
                            "（须先登记归属并置 enabled）"
                        )
    return errors


async def _read_ownership(url: str) -> list[TableRecord]:
    """只读读取平台服务库表归属登记（未软删行）。

    Args:
        url: 平台服务库连接串。

    Returns:
        list[TableRecord]: 归属登记记录列表。
    """
    engine = create_async_engine(url)
    factory: async_sessionmaker[AsyncSession] = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            statement = select(SysTableOwnership).where(SysTableOwnership.deleted_at.is_(None))
            rows = (await session.execute(statement)).scalars()
            return [TableRecord.from_row(row) for row in rows.all()]
    finally:
        await engine.dispose()


def check_table_db(url: str) -> list[str]:
    """接库校验：读库查重与格式 + 与清单双向对账（空库判失败）。

    Args:
        url: 平台服务库连接串（迁移 + 种子后）。

    Returns:
        list[str]: 冲突 / 非法明细（含库不可读）。
    """
    try:
        records = asyncio.run(_read_ownership(url))
    except Exception as exc:
        return [f"表归属登记库不可读（请先执行平台服务链迁移）：{exc}"]
    if not records:
        return ["库中无登记行（种子未执行？）"]
    return validate_table_ownership(TABLE_OWNERSHIP, records)


def main(argv: Sequence[str] | None = None) -> int:
    """入口：离线校验（默认）+ 可选接库校验。

    Args:
        argv: 命令行参数。

    Returns:
        int: 退出码（0 通过 / 1 失败）。
    """
    args = build_parser().parse_args(argv)
    errors = check_offline()
    if args.url:
        errors.extend(check_table_db(args.url))
    if errors:
        for error in errors:
            print(f"[表归属] {error}")
        print(f"[表归属] 校验失败（{len(errors)} 项）")
        return 1
    scope = f"清单 {len(TABLE_OWNERSHIP)} 项 + 模型表对账 + 脚本表集"
    if args.url:
        scope += " + 接库对账"
    print(f"[表归属] 校验通过（{scope}）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
