"""表归属登记校验（06_02）：离线断言 + 可选接库双向对账（CI 硬门禁）。

用法：

```bash
cd backend
uv run python -m ops.check_tables              # 离线断言 + 接库对账（URL 读配置解析）
uv run python -m ops.check_tables --offline    # 仅离线断言（无库场景）
```

离线断言（不连库，零依赖）：

1. **清单自校验**：`TableOwnershipRegistry().validate()`（表名唯一与格式 / 归属与库类别合法 / 前缀归属一致）；
2. **模型表必登记**：各启用服务模型（按服务 `MODEL_MODULES` + 公共模型模块导入）的 `__tablename__`
   必须已登记（未登记即失败——防「模型落地却未进归属登记」）；
3. **enabled 表必入清单**：`status = enabled` 的归属表必须出现在其**归属业务域 + 库类别**对应清单的
   `series_tables` 中（派生自证 + 防漏；`*` 基础设施表跳过——它们不进域清单、由单元级建表集追加）；
4. **脚本表集不越界（净新建口径）**：每条**有脚本**的清单，按**整清单汇总**后
   `（建表 ∪ 批量改表）− 删表 ⊆ 该清单 series_tables`——同一清单内先建后删的表**净零**放行
   （表迁出后历史建表脚本 + 补删表迁移即属此类）；
5. **form_key 一致**（02_11）：`FormRegistry().validate()`（标识格式与跨表全局唯一）+ `FORM_CATALOG`
   与模型元数据**双向一致**（清单表须有 `form_key` 列；有 `form_key` 列的模型表须在清单）。

接库（`--url`）：读平台服务库 `sys_table_ownership`（未软删行）与清单**双向对账**（缺行 / 清单外行 /
字段不符），只读不写；空库判失败（种子未执行）。

冲突 / 非法 → 打印明细并退出码 1；通过 → 退出码 0。
"""

import argparse
import asyncio
import re
from pathlib import Path
from typing import cast

from sqlalchemy import Table, select
from sqlalchemy import create_engine as create_sync_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from bms_core.boundary.domains import DEFAULT_LAYOUT_RELATIVE, load_layout
from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList, ConcurrentStableSet
from bms_core.db.keys import PLATFORM_SERVICE_KEY
from bms_core.db.migration import (
    COMMON_MODEL_MODULES,
    DATASOURCES,
    VERSIONS_ROOT,
    apply_session_schema,
    import_service_models,
    require_service_model_modules,
    resolve_series,
)
from bms_core.db.sync import is_sync_only_url
from bms_core.models.base import Base
from bms_core.models.ownership import SysTableOwnership
from bms_core.registry.forms import FORM_CATALOG, FormRegistry
from bms_core.services.module_registry import enabled_service_keys
from bms_core.services.table_registry import (
    OWNER_EVERY_SERVICE,
    TableOwnershipRegistry,
    TableRecord,
    series_tables,
    table_names,
    table_ownership_view,
    validate_table_ownership,
)
from ops.seed_tenant import resolve_url

RUN_IMAGE = "*"
"""本脚本只依赖 `bms_core` 与 `ops`（不导入任何服务包），任意服务镜像均可运行。"""
_CREATE_TABLE_RE = re.compile(r"op\.create_table\(\s*[\"']([a-z0-9_]+)[\"']")
_BATCH_TABLE_RE = re.compile(r"op\.batch_alter_table\(\s*[\"']([a-z0-9_]+)[\"']")
_DROP_TABLE_RE = re.compile(r"op\.drop_table\(\s*[\"']([a-z0-9_]+)[\"']")
_REPO_ROOT = Path(__file__).resolve().parents[2]
"""本脚本所在 bms 仓库根（域布局声明定位用；镜像内无该文件时按「不做成员校验」降级）。"""


def _domain_services() -> ConcurrentStableDict[str, str] | None:
    """取域 → 承载服务映射（域布局声明；仓库内缺失时返回 None 表示不做成员校验）。

    Returns:
        ConcurrentStableDict[str, str] | None: 域 → 承载服务；无声明时 None。
    """
    mapping = load_layout(_REPO_ROOT / DEFAULT_LAYOUT_RELATIVE).domain_services()
    return mapping if mapping else None


def build_parser() -> argparse.ArgumentParser:
    """构建命令行解析器。

    Returns:
        argparse.ArgumentParser: 解析器。
    """
    parser = argparse.ArgumentParser(description="表归属登记校验（离线断言 + 可选接库对账）")
    parser.add_argument("--url", default="", help="平台服务库连接串（显式覆盖；缺省按配置解析）")
    parser.add_argument("--offline", action="store_true", help="仅离线断言，不接库")
    parser.add_argument("--schema", default="", help="目标模式名（达梦等同步方言必填，如 BMS_TEST_DM）")
    return parser


def imported_model_tables() -> ConcurrentStableSet[str]:
    """导入各启用服务与公共模型模块后取**已声明模块**的模型表名。

    只统计模块属于「公共模型清单 + 各服务 `MODEL_MODULES`」的模型（按 `__module__` 归属判定），
    以免测试或其他进程内临时模型（同进程共享 `Base.metadata`）干扰本断言。

    Returns:
        ConcurrentStableSet[str]: 模型表名集合。
    """
    declared: ConcurrentStableSet[str] = ConcurrentStableSet(COMMON_MODEL_MODULES)
    for service in enabled_service_keys():
        # 严格入口：已启用服务必有服务包（包名前缀经 `[app].package_prefix`），缺失即报错（12_04）
        declared.update(require_service_model_modules(service))
        import_service_models(service)

    tables: ConcurrentStableSet[str] = ConcurrentStableSet()
    for mapper in Base.registry.mappers:
        module = str(getattr(mapper.class_, "__module__", ""))
        if module not in declared:
            continue
        local = cast("Table | None", mapper.local_table)
        if local is None:
            continue
        tables.add(str(local.name))
    return tables


def check_offline(*, versions_root: Path = VERSIONS_ROOT) -> ConcurrentStableList[str]:
    """离线校验：清单自校验 + 模型表必登记 + enabled 表必入链 + 脚本表集不越界。

    Args:
        versions_root: 版本目录根（自检可指定替身目录）。

    Returns:
        ConcurrentStableList[str]: 冲突 / 非法明细；空列表表示通过。
    """
    errors = ConcurrentStableList(TableOwnershipRegistry().validate(domain_services=_domain_services()))
    registered = table_names()
    modeled = imported_model_tables()

    for table in sorted(modeled - registered):
        errors.add(f"模型表未登记归属：{table}（须在表归属登记【平台清单 + 产品注入】登记）")

    for record in table_ownership_view():
        if record.owner == OWNER_EVERY_SERVICE or record.status != "enabled":
            continue
        owned = series_tables(record.domain, record.datasource)
        if record.table_name not in owned:
            errors.add(f"{record.table_name}：enabled 但未进入归属域 {record.domain} 的 {record.datasource} 清单")

    errors.update(_check_script_tables(versions_root))
    errors.update(_check_form_keys())
    return errors


def _check_form_keys() -> ConcurrentStableList[str]:
    """系统字段 `form_key` 校验（02_11）：清单自校验 + 清单 ↔ 模型双向一致。

    Returns:
        ConcurrentStableList[str]: 违规明细。
    """
    errors = ConcurrentStableList(FormRegistry().validate())
    catalog_tables: ConcurrentStableSet[str] = ConcurrentStableSet(record.table for record in FORM_CATALOG)
    for record in FORM_CATALOG:
        table = Base.metadata.tables.get(record.table)
        if table is None:
            errors.add(f"form_key 清单表缺模型：{record.table}（form_key={record.form_key}）")
        elif "form_key" not in table.columns:
            errors.add(f"模型表缺 form_key 列：{record.table}（须与 form_key 清单一致）")
    for name in sorted(imported_model_tables()):
        table = Base.metadata.tables.get(name)
        if table is None or "form_key" not in table.columns:
            continue
        if name not in catalog_tables:
            errors.add(f"模型表有 form_key 列但未登记 form_key 清单：{name}")
    return errors


def _check_script_tables(versions_root: Path) -> ConcurrentStableList[str]:
    """校验各链迁移脚本的**净新建**表集 ⊆ 该链派生表集（防脚本越界建表）。

    口径：按**整链汇总**计算 `（建表 ∪ 批量改表）− 删表`——同一链内先建后删的表净零放行
    （表迁出场景：历史建表脚本保留 + 补删表迁移，二者相抵）。

    Args:
        versions_root: 版本目录根（`alembic/versions`）。

    Returns:
        ConcurrentStableList[str]: 违规明细。
    """
    errors: ConcurrentStableList[str] = ConcurrentStableList()
    if not versions_root.is_dir():
        return errors
    for domain_dir in sorted(versions_root.iterdir()):
        if not domain_dir.is_dir() or domain_dir.name.startswith("."):
            continue
        for datasource in DATASOURCES:
            location = domain_dir / datasource
            if not location.is_dir():
                continue
            series = resolve_series(f"{domain_dir.name}:{datasource}")
            scripts = ConcurrentStableList(sorted(location.glob("*.py")))
            errors.update(_series_script_errors(series.name, series.tables, scripts))
    return errors


def _series_script_errors(
    series_name: str, series_tables_set: ConcurrentStableSet[str], scripts: ConcurrentStableList[Path]
) -> ConcurrentStableList[str]:
    """单条清单的脚本净新建表集校验（先建后删相抵）。

    Args:
        series_name: 清单名（错误提示用）。
        series_tables_set: 该清单派生表集（归属本域，不含基础设施表）。
        scripts: 该清单版本目录下的脚本（按名排序）。

    Returns:
        ConcurrentStableList[str]: 违规明细。
    """
    origins: ConcurrentStableDict[str, str] = ConcurrentStableDict()
    dropped: ConcurrentStableSet[str] = ConcurrentStableSet()
    for script in scripts:
        text = script.read_text(encoding="utf-8")
        for name in sorted(set(_CREATE_TABLE_RE.findall(text)) | set(_BATCH_TABLE_RE.findall(text))):
            if name not in origins:
                origins.set(name, script.name)
        dropped.update(_DROP_TABLE_RE.findall(text))
    errors: ConcurrentStableList[str] = ConcurrentStableList()
    for name in sorted(origins.keys()):
        if name in dropped or name in series_tables_set:
            continue
        errors.add(
            f"{series_name}/{origins.get(name) or '?'}：建表 / 改表 {name} 不在该清单派生表集内"
            "（须先登记归属域并置 enabled；同清单先建后删的表净零放行）"
        )
    return errors


def _read_ownership_sync(url: str, schema: str) -> ConcurrentStableList[TableRecord]:
    """同步方言（达梦）只读读取归属登记（阻塞驱动走线程池）。

    Args:
        url: 平台服务库连接串。
        schema: 目标模式名（达梦）。

    Returns:
        ConcurrentStableList[TableRecord]: 归属登记记录列表。
    """
    engine = create_sync_engine(url, poolclass=NullPool, isolation_level="AUTOCOMMIT")
    try:
        with engine.connect() as connection:
            apply_session_schema(connection, schema)
            session = Session(bind=connection)
            try:
                statement = select(SysTableOwnership).where(SysTableOwnership.deleted_at.is_(None))
                rows = session.execute(statement).scalars().all()
                return ConcurrentStableList(TableRecord.from_row(row) for row in rows)
            finally:
                session.close()
    finally:
        engine.dispose()


async def _read_ownership(url: str, schema: str = "") -> ConcurrentStableList[TableRecord]:
    """只读读取平台服务库表归属登记（未软删行）。

    Args:
        url: 平台服务库连接串。
        schema: 目标模式名（达梦；同步方言必填）。

    Returns:
        ConcurrentStableList[TableRecord]: 归属登记记录列表。
    """
    if is_sync_only_url(url):
        return await asyncio.to_thread(_read_ownership_sync, url, schema)
    engine = create_async_engine(url)
    factory: async_sessionmaker[AsyncSession] = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            statement = select(SysTableOwnership).where(SysTableOwnership.deleted_at.is_(None))
            rows = (await session.execute(statement)).scalars()
            return ConcurrentStableList(TableRecord.from_row(row) for row in rows.all())
    finally:
        await engine.dispose()


def check_table_db(url: str, *, schema: str = "") -> ConcurrentStableList[str]:
    """接库校验：读库查重与格式 + 与清单双向对账（空库判失败）。

    Args:
        url: 平台服务库连接串（迁移 + 种子后）。
        schema: 目标模式名（达梦；同步方言必填）。

    Returns:
        ConcurrentStableList[str]: 冲突 / 非法明细（含库不可读）。
    """
    try:
        records = asyncio.run(_read_ownership(url, schema))
    except Exception as exc:
        return ConcurrentStableList([f"表归属登记库不可读（请先执行平台服务链迁移）：{exc}"])
    if not records:
        return ConcurrentStableList(["库中无登记行（种子未执行？）"])
    return ConcurrentStableList(validate_table_ownership(table_ownership_view(), ConcurrentStableList(records)))


def main(argv: ConcurrentStableList[str] | None = None) -> int:
    """入口：离线校验（默认）+ 可选接库校验。

    Args:
        argv: 命令行参数。

    Returns:
        int: 退出码（0 通过 / 1 失败）。
    """
    args = build_parser().parse_args(argv)
    errors = check_offline()
    url = "" if args.offline else (args.url or resolve_url(service=PLATFORM_SERVICE_KEY))
    if url:
        errors.update(check_table_db(url, schema=args.schema))
    if errors:
        for error in errors:
            print(f"[表归属] {error}")
        print(f"[表归属] 校验失败（{len(errors)} 项）")
        return 1
    scope = f"清单 {len(table_ownership_view())} 项 + 模型表对账 + 脚本表集"
    if url:
        scope += " + 接库对账"
    print(f"[表归属] 校验通过（{scope}）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
