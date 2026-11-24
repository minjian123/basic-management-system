"""本轮自建字段变更声明（前置到初始化阶段；13_10 需求第 5 条）。

口径：运行期新增字段只落 `pending`，脚本在运行期**没有**执行时机。要验证「列已生效」的
结构变更，必须先在这里**声明**，由初始化阶段生成脚本并执行；用例只验证结果与 `pending` 分支。

新增变更时同步维护 `CHANGES`：初始化阶段会按声明生成脚本、执行、回读校验（不一致直接失败）。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList, ConcurrentStableSet
from bms_core.core.objects import BaseValueObject
from bms_core.models.platform.form_design import DDL_STATUS_PENDING, SysFieldExt

SCRIPT_RECORD_NAME = "form_design_script.json"
"""初始化阶段落盘的实际脚本文件名（落会话测试库目录）。"""


def script_record_path() -> Path:
    """实际脚本记录文件路径（会话测试库目录下）。

    Returns:
        Path: 记录文件路径。
    """
    from bms_core.testing.fixtures import test_db_dir

    return test_db_dir() / SCRIPT_RECORD_NAME


def write_script_record(entries: ConcurrentStableList[Any], executed: ConcurrentStableList[str]) -> None:
    """把初始化阶段实际生成并执行的脚本落盘（供测试断言「测的就是跑的」）。

    Args:
        entries: 生成段产出的脚本条目（`ScriptEntry`）。
        executed: 执行回执（实际执行的语句）。
    """
    payload = {
        "entries": [
            {
                "field_id": entry.field_id,
                "label": entry.label,
                "table": entry.table_name,
                "column": entry.column_name,
                "sql": entry.sql,
                "skipped": entry.skipped,
            }
            for entry in entries
        ],
        "executed": list(executed),
    }
    script_record_path().write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")


def read_script_record() -> ConcurrentStableDict[str, Any]:
    """读取初始化阶段落盘的实际脚本记录。

    Returns:
        ConcurrentStableDict[str, Any]: `entries`（脚本条目）与 `executed`（执行清单）。

    Raises:
        FileNotFoundError: 初始化阶段未落盘（共享库未初始化或未跑过该阶段）。
    """
    path = script_record_path()
    if not path.exists():
        raise FileNotFoundError(f"初始化脚本记录不存在：{path}（先跑一次依赖共享库的用例）")
    return ConcurrentStableDict(json.loads(path.read_text(encoding="utf-8")))


@dataclass(frozen=True)
class FormChange(BaseValueObject):
    """一条结构变更声明（初始化阶段据此生成并执行补列脚本）。"""

    form_code: str
    """表单标识。"""

    field_key: str
    """字段键（列名派生为 `ext_{field_key}`）。"""

    table: str
    """目标物理表名（须是测试库中已存在的表）。"""

    type: str = "text"
    """字段类型（自建字段白名单）。"""

    name: str = "初始化建列"
    """字段显示名（列注释）。"""


CHANGES: ConcurrentStableList[FormChange] = ConcurrentStableList(
    (FormChange(form_code="probe_biz", field_key="seeded", table="biz_ext_probe"),)
)
"""本轮声明的结构变更（初始化阶段生成并执行；新增即追加）。"""


async def apply_changes(url: str) -> None:
    """初始化阶段：按声明生成补列脚本并执行，最后回读校验。

    一致性要求（缺一不可）：
    - 执行段只接受生成段产出的脚本条目；
    - 实际执行语句 == 生成脚本非跳过语句；
    - 执行后回读库结构，脚本声明的列全部存在。

    Args:
        url: 共享平台库连接串。

    Raises:
        RuntimeError: 执行语句与生成脚本不一致，或执行后仍缺列。
    """
    from ops.build_ext_columns import (
        apply_script,
        build_script,
        existing_columns,
        script_statements,
        verify_applied,
    )

    engine = create_async_engine(url, poolclass=NullPool)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            for change in CHANGES:
                await session.execute(
                    delete(SysFieldExt).where(
                        SysFieldExt.form_code == change.form_code,
                        SysFieldExt.field_key == change.field_key,
                    )
                )
                session.add(
                    SysFieldExt(
                        form_code=change.form_code,
                        field_key=change.field_key,
                        name=change.name,
                        type=change.type,
                        option_set_key=None,
                        column_name=f"ext_{change.field_key}",
                        table_name=change.table,
                        ddl_status=DDL_STATUS_PENDING,
                        sort=0,
                        status="enabled",
                    )
                )
            await session.commit()
            declared: ConcurrentStableSet[tuple[str, str]] = ConcurrentStableSet(
                (change.form_code, change.field_key) for change in CHANGES
            )
            statement = (
                select(SysFieldExt)
                .where(SysFieldExt.ddl_status == DDL_STATUS_PENDING, SysFieldExt.deleted_at.is_(None))
                .order_by(SysFieldExt.id)
            )
            fetched = (await session.execute(statement)).scalars().all()
            fields = ConcurrentStableList(item for item in fetched if (item.form_code, item.field_key) in declared)
            tables: ConcurrentStableSet[str] = ConcurrentStableSet(change.table for change in CHANGES)
            present = await existing_columns(session, tables)
            script = build_script(fields, present, dialect=session.get_bind().dialect)
            applied = await apply_script(session, script)
            if applied.executed != script_statements(script):
                raise RuntimeError(
                    f"初始化补列：执行语句与生成脚本不一致（执行 {len(applied.executed)} 条 / "
                    f"生成 {len(script_statements(script))} 条）"
                )
            missing = await verify_applied(session, script)
            if missing:
                raise RuntimeError(f"初始化补列：脚本声明的列未生效：{list(missing)}")
            write_script_record(script, applied.executed)
    finally:
        await engine.dispose()
