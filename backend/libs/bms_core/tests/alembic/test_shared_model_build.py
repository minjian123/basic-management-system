"""共享模型建表核对（Kiwi 2342）：enabled 共享表全部建出 / planned 不进链 / 逐链表数零漂移。

对应任务 14_02（需求 14-2）：14_01 把 38 张共享表模型整包下沉到
`bms_core.models.{platform,identity,tenant}` 后，建表链路由「表归属登记派生 ∩ 已导入模型」决定
（`chain_metadata` 单一派生点）。本用例**真实建表**（临时 SQLite）核对：

- 五条启用链的建表结果表数固定（19 / 15 / 4 / 6 / 8），与归属登记派生表集一致；
- 34 张 enabled 共享模型表逐链全部落地（`planned` 的 4 张不得出现）；
- 归档链无表集（不建连、不产生库文件）。
"""

import sqlite3
from pathlib import Path

import pytest

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableSet
from bms_core.db.bootstrap import apply_chain_schema
from bms_core.db.migration import resolve_chain

_EXPECTED_CHAIN_TABLES = {
    "platform:platform": 19,
    "platform:tenant": 15,
    "identity:platform": 4,
    "identity:tenant": 6,
    "tenant:platform": 8,
}
"""五条启用链的建表表数（链表集 = 归属表 + 基座基础设施表，脚本清空后仍照建）。"""

_SHARED_TABLES_BY_CHAIN = {
    "platform:platform": {
        "sys_module",
        "sys_module_i18n",
        "sys_product",
        "sys_business",
        "sys_business_i18n",
        "sys_action",
        "sys_action_i18n",
        "sys_permission",
        "sys_menu",
        "sys_menu_i18n",
        "sys_form",
        "sys_menu_form",
        "sys_field",
        "sys_field_i18n",
        "sys_button",
    },
    "platform:tenant": {
        "sys_user",
        "sys_account_lock",
        "sys_role",
        "sys_user_role",
        "sys_role_permission",
        "sys_role_field",
        "sys_data_scope",
        "sys_icon",
        "sys_icon_i18n",
        "sys_user_extension",
    },
    "identity:platform": {"sys_user_identity"},
    "identity:tenant": {"sys_session", "sys_identity_provider", "sys_client"},
    "tenant:platform": {
        "sys_tenant",
        "sys_tenant_database",
        "sys_tenant_module",
        "sys_tenant_quota",
        "sys_user_tenant",
    },
}
"""各链应建出的共享模型表（合计 34 张 enabled；`planned` 表不在此列）。"""

_PLANNED_SHARED_TABLES = ("sys_task", "sys_task_log", "sys_user_preference", "demo")
"""有模型但 `status = planned` 的共享表：不进任何链（随所属阶段转 enabled 后自动进链）。"""

_SHARED_ENABLED_COUNT = 34
"""enabled 共享模型表总数（38 张共享表 − 4 张 planned）。"""


def _tables(path: Path) -> ConcurrentStableSet[str]:
    """取 SQLite 库文件的实际表名集合。

    Args:
        path: 库文件路径。

    Returns:
        ConcurrentStableSet[str]: 表名集合（插入序）。
    """
    connection = sqlite3.connect(path)
    try:
        return ConcurrentStableSet(
            str(row[0]) for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        )
    finally:
        connection.close()


@pytest.mark.kiwi_id(2342)
async def test_shared_models_built_by_chain_schema(tmp_path: Path) -> None:
    """逐链真实建表：表数零漂移、34 张 enabled 共享表全部建出、planned 表与归档链不落地。"""
    built: ConcurrentStableDict[str, ConcurrentStableSet[str]] = ConcurrentStableDict()
    for chain_name, expected in _EXPECTED_CHAIN_TABLES.items():
        chain = resolve_chain(chain_name)
        target = tmp_path / f"{chain_name.replace(':', '_')}.db"
        outcome = await apply_chain_schema(chain, f"sqlite+aiosqlite:///{target}", target=chain_name)

        assert outcome.total == expected, f"{chain_name} 建表表集漂移（漏登记 → 静默漏表）"
        assert (outcome.created, outcome.existing) == (expected, 0), f"{chain_name} 首建应全为新建"
        assert len(chain.tables) == expected, f"{chain_name} 归属派生表集与模型表集不一致"
        built[chain_name] = _tables(target)

    for chain_name, shared_tables in _SHARED_TABLES_BY_CHAIN.items():
        missing = shared_tables - built[chain_name]
        assert not missing, f"{chain_name} 缺共享模型表：{sorted(missing)}"

    all_shared: ConcurrentStableSet[str] = ConcurrentStableSet()
    for shared_tables in _SHARED_TABLES_BY_CHAIN.values():
        all_shared.update(shared_tables)
    assert len(all_shared) == _SHARED_ENABLED_COUNT

    union: ConcurrentStableSet[str] = ConcurrentStableSet()
    for tables in built.values():
        union.update(tables)
    assert not [name for name in _PLANNED_SHARED_TABLES if name in union], "planned 表不得建表（未转 enabled 前）"

    archive_target = tmp_path / "archive.db"
    archive = await apply_chain_schema(resolve_chain("platform:archive"), f"sqlite+aiosqlite:///{archive_target}")
    assert (archive.total, archive.created, archive.existing) == (0, 0, 0), "归档链表集应为空"
    assert not archive_target.exists(), "表集空即不建连（不产生库文件）"
