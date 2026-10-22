"""共享模型下沉基座：子包登记 / 建表链发现 / 表归属一致性（Kiwi 2341）。

对应任务 14_01（需求 14-1）：platform / identity / tenant 三包整包下沉到
`bms_core.models.{platform,identity,tenant}` 后——

- 三子包 `MODEL_MODULES` 是「有哪些共享模型」的**唯一登记点**，`COMMON_MODEL_MODULES` 只做组合；
- 模型表仍须落在 `TABLE_OWNERSHIP` 登记内（代码位置不改归属）；
- 各链 `chain_metadata` 表集固定，防「漏登记 → 静默漏表 / 静默 0 表」。
"""

from typing import cast

import pytest
from sqlalchemy import Table

from bms_core.core.concurrent import ConcurrentStableList, ConcurrentStableSet
from bms_core.db.migration import (
    COMMON_MODEL_MODULES,
    chain_metadata,
    import_models,
    resolve_chain,
)
from bms_core.models.base import Base
from bms_core.models.identity import MODEL_MODULES as IDENTITY_MODEL_MODULES
from bms_core.models.platform import MODEL_MODULES as PLATFORM_MODEL_MODULES
from bms_core.models.tenant import MODEL_MODULES as TENANT_MODEL_MODULES
from bms_core.services.table_registry import TableStatus, table_names, table_record

_SHARED_MODULE_COUNT = 15
"""共享模型模块总数（platform 6 / identity 4 / tenant 5）。"""

_SHARED_TABLE_COUNT = 38
"""共享模型表总数（platform 29 / identity 4 / tenant 5；含 `planned` 的 `demo`）。"""

_EXPECTED_CHAIN_TABLES = {
    "platform:platform": 19,
    "platform:tenant": 15,
    "identity:platform": 4,
    "identity:tenant": 6,
    "tenant:platform": 8,
}
"""各链 `chain_metadata` 表数（归属表 + 发件箱三表；迁移前口径，迁包后须零漂移）。"""


def _shared_module_names() -> ConcurrentStableList[str]:
    """三子包声明的共享模型模块清单（拼接序：platform → identity → tenant）。

    Returns:
        ConcurrentStableList[str]: 模块名清单。
    """
    names: ConcurrentStableList[str] = ConcurrentStableList(PLATFORM_MODEL_MODULES)
    names.update(IDENTITY_MODEL_MODULES)
    names.update(TENANT_MODEL_MODULES)
    return names


def _shared_tables() -> ConcurrentStableSet[str]:
    """导入全部共享模型模块后，取 `__module__` 属于共享模型清单的模型表名。

    Returns:
        ConcurrentStableSet[str]: 共享模型表名集合。
    """
    import_models("platform")
    modules = ConcurrentStableSet(_shared_module_names())
    tables: ConcurrentStableSet[str] = ConcurrentStableSet()
    for mapper in Base.registry.mappers:
        if str(getattr(mapper.class_, "__module__", "")) not in modules:
            continue
        local = cast("Table | None", mapper.local_table)
        if local is None:
            continue
        tables.add(str(local.name))
    return tables


@pytest.mark.kiwi_id(2341)
def test_shared_model_modules_declared_and_composed() -> None:
    """三子包自声明清单与 `COMMON_MODEL_MODULES` 一致（15 模块，均以基座新路径命名）。"""
    names = _shared_module_names()

    assert len(names) == _SHARED_MODULE_COUNT
    assert len(set(names)) == _SHARED_MODULE_COUNT, "子包清单存在重复模块"
    for name in names:
        assert name.startswith(("bms_core.models.platform.", "bms_core.models.identity.", "bms_core.models.tenant."))
        assert name in COMMON_MODEL_MODULES, f"共享模型模块未纳入 COMMON_MODEL_MODULES：{name}"


@pytest.mark.kiwi_id(2341)
def test_shared_models_importable_and_registered() -> None:
    """共享模型可导入、共 38 表，且全部已登记表归属（代码下沉不改归属）。"""
    tables = _shared_tables()

    assert len(tables) == _SHARED_TABLE_COUNT
    registered = table_names()
    missing = sorted(tables - registered)
    assert not missing, f"共享模型表未登记归属：{missing}"


@pytest.mark.kiwi_id(2341)
def test_chain_metadata_includes_shared_models() -> None:
    """各链 `chain_metadata` 表数与迁包前一致（防漏登记导致静默漏表）。"""
    for chain_name, expected in _EXPECTED_CHAIN_TABLES.items():
        chain = resolve_chain(chain_name)
        metadata = chain_metadata(chain)
        assert len(chain.tables) == expected, f"{chain_name} 归属派生表集漂移"
        assert len(metadata.tables) == expected, f"{chain_name} 模型表集漂移（漏登记 → 静默漏表）"


@pytest.mark.kiwi_id(2341)
def test_planned_shared_model_stays_out_of_chains() -> None:
    """`planned` 的 `demo` 表有模型但不进链（建表链由归属登记状态驱动，与代码位置无关）。"""
    assert "demo" in _shared_tables(), "demo 模型应在共享模型内（平台服务五层示例表）"

    record = table_record("demo")
    assert record is not None
    assert record.status == TableStatus.PLANNED

    chained: ConcurrentStableSet[str] = ConcurrentStableSet()
    for chain_name in _EXPECTED_CHAIN_TABLES:
        chained.update(resolve_chain(chain_name).tables)
    assert "demo" not in chained, "planned 表不得进链"
