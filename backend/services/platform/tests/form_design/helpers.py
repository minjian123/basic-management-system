"""表单定制用例共用助手：造业务码 / 表单 / 字段、探针表与清单注入。

**建引擎能力全部下沉 `tests_support/form_design.py`**：测试库隔离护栏只放行共享基座建引擎，
用例侧只调函数（单库叠加口径，见《测试规范》「测试数据」节）。

**隔离靠命名空间，不靠清表**（2026-11-18 修订）：本域四表落共享租户库、全 worker 叠加，
整表 delete 会删掉并行中他人用例正在断言的行（与 `services/identity/tests/auth` 取消
`delete(SysSession)` 同一理由）。所有夹具只**建表（缺则建）**；隔离由
`form_code = {ns.prefix}_{suffix}` 与探针表名 `biz_{form_code}` 保证。业务码 / 表单 / 字段
在平台库同样是命名空间内新建，用例结束不清理。
"""

from __future__ import annotations

import os
from typing import Any

from sqlalchemy import select

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.models.outbox import SysOutbox
from bms_core.models.platform.form_design import (
    SysFieldExt,
    SysFieldExtI18n,
    SysFormFieldAttr,
    SysFormLayout,
)
from bms_core.models.platform.menu_form import SysField, SysForm
from bms_core.models.platform.permission_meta import SysBusiness
from bms_core.registry.forms import FormRecord, FormRegistry, merge_form_records
from tests_support.form_design import (
    create_probe_table,
    drop_probe_table,
    ensure_models,
    list_columns,
    run_statement,
)
from tests_support.shared_access import shared_session

__all__ = [
    "FORM_DESIGN_MODELS",
    "create_probe_table",
    "drop_probe_table",
    "ensure_form_design_tables",
    "list_columns",
    "outbox_types_in_tenant",
    "platform_url",
    "register_form_key",
    "run_statement",
    "seed_business",
    "seed_form_with_fields",
    "tenant_url",
]

FORM_DESIGN_MODELS: ConcurrentStableList[Any] = ConcurrentStableList(
    (
        SysFormLayout,
        SysFormFieldAttr,
        SysFieldExtI18n,
        SysFieldExt,
    )
)
"""表单定制四表（只用于「确保存在」，不做清场）。"""


def platform_url() -> str:
    """当前用例的平台库连接串。

    Returns:
        str: 平台库连接串。
    """
    return os.environ["BMS_DATABASE__PLATFORM__URL"]


def tenant_url() -> str:
    """当前用例的共享测试租户库连接串（单库叠加口径）。

    Returns:
        str: 租户库连接串。
    """
    return os.environ["BMS_DATABASE__TENANTS__URL"]


async def ensure_form_design_tables() -> None:
    """确保表单定制四表存在（缺则建；**不清空**，隔离靠用例命名空间）。"""
    await ensure_models(tenant_url(), FORM_DESIGN_MODELS)


async def seed_business(code: str, name: str = "测试业务") -> int:
    """直插业务码（平台库；`code` 即表单标识，调用方按命名空间派生保证唯一）。

    Args:
        code: 业务码。
        name: 名称。

    Returns:
        int: 业务码主键。
    """
    url = platform_url()
    async with shared_session(url, read_only=False) as session:
        row = SysBusiness(code=code, name=name, status="enabled")
        session.add(row)
        await session.flush()
        business_id = row.id
        await session.commit()
    return business_id


async def seed_form_with_fields(
    business_id: int,
    fields: ConcurrentStableList[tuple[str, str, str, int]],
) -> int:
    """直插表单与平台字段（平台库）。

    Args:
        business_id: 业务码主键。
        fields: 字段清单（`(field_key, name, type, sort)`）。

    Returns:
        int: 表单主键。
    """
    url = platform_url()
    async with shared_session(url, read_only=False) as session:
        form = SysForm(business_id=business_id, component=None, status="enabled")
        session.add(form)
        await session.flush()
        form_id = form.id
        for field_key, name, field_type, sort in fields:
            session.add(
                SysField(
                    form_id=form_id,
                    field_key=field_key,
                    name=name,
                    type=field_type,
                    sort=sort,
                    status="enabled",
                )
            )
        await session.commit()
    return form_id


async def outbox_types_in_tenant(aggregate_key: str) -> ConcurrentStableList[str]:
    """取租户库发件箱中某聚合键的事件类型（本域事件写租户库）。

    Args:
        aggregate_key: 聚合 / 分区键。

    Returns:
        ConcurrentStableList[str]: 事件类型清单（插入序）。
    """
    url = tenant_url()
    async with shared_session(url, read_only=True) as session:
        rows = (
            (await session.execute(select(SysOutbox.event_type).where(SysOutbox.aggregate_key == aggregate_key)))
            .scalars()
            .all()
        )
    return ConcurrentStableList(str(item) for item in rows)


def register_form_key(app: object, form_code: str, table: str) -> None:
    """把测试业务码登记进应用级表单清单（自建字段建列需 `form_key → table` 可解析）。

    Args:
        app: FastAPI 应用。
        form_code: 业务码（即表单标识）。
        table: 目标物理表名（须真实存在）。
    """
    state = getattr(app, "state", None)
    injected: ConcurrentStableList[FormRecord] = ConcurrentStableList()
    current = getattr(state, "form_registry", None) if state is not None else None
    if current is not None:
        for record in current.catalog_records():
            if record.form_key != form_code:
                injected.add(record)
    injected.add(FormRecord(form_key=form_code, table=table, name=form_code, kind="form"))
    if state is not None:
        state.form_registry = FormRegistry(merge_form_records(injected=injected))
