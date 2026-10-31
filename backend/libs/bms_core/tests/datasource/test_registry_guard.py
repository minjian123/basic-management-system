"""数据源登记护栏（Kiwi 2372）：key 常量唯一落点 / 清单自校验 / 无字典六表残留 / 无散落字面量。

CI 与开发环都会收集本用例（`base-integrity` / 选测），拦截三类回归：

1. `DataSourceKey` 枚举与 `DATA_SOURCE_CATALOG` 键集合不一致（改名只改一处的保证）；
2. 新增登记项格式非法（走 `DataSourceRegistry.validate()` 同一规则）；
3. 声明表之外出现 `data_source_key="字面量"`（把「一处变更」扩散回几十处）。
"""

from pathlib import Path

import pytest

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.datasource.keys import DataSourceKey, platform_data_source_keys
from bms_core.datasource.registry import DATA_SOURCE_CATALOG, DataSourceRegistry
from bms_core.services.table_registry import table_names

_BACKEND_ROOT = Path(__file__).resolve().parents[4]
"""`backend/` 目录（本文件位于 `backend/libs/bms_core/tests/datasource/`）。"""

_DECLARATION_FILES = (
    "libs/bms_core/src/bms_core/datasource/registry.py",
    "libs/bms_core/src/bms_core/registry/forms.py",
    "services/platform/src/bms_platform/domains/platform_registry/sources/dict_specs.py",
)
"""允许出现 `data_source_key="字面量"` 的声明表（其余源码一律用枚举或变量）。"""


@pytest.mark.kiwi_id(2372)
def test_enum_matches_catalog_keys() -> None:
    """枚举值集合与登记清单键集合完全一致（多一个少一个都算漂移）。"""
    enum_keys = ConcurrentStableList(key.value for key in DataSourceKey)
    catalog_keys = ConcurrentStableList(record.data_source_key for record in DATA_SOURCE_CATALOG)
    assert sorted(enum_keys) == sorted(catalog_keys)
    assert len(enum_keys) == 12


@pytest.mark.kiwi_id(2372)
def test_platform_data_source_keys_helper() -> None:
    """`platform_data_source_keys()` 返回 12 个标识且不可变。"""
    keys = platform_data_source_keys()
    assert len(keys) == 12
    assert "role" in keys
    with pytest.raises(Exception):
        keys.add("ghost")  # pyright: ignore[reportAttributeAccessIssue,reportUnknownMemberType]


@pytest.mark.kiwi_id(2372)
def test_catalog_self_check_passes() -> None:
    """登记清单自校验无问题（标识格式 / 唯一 / 名称 / 出口 / 类型 / 白名单）。"""
    assert list(DataSourceRegistry(DATA_SOURCE_CATALOG).validate()) == []


@pytest.mark.kiwi_id(2372)
def test_no_dict_tables_registered() -> None:
    """字典六表不得回到表登记（`sys_dict_type` / `sys_dict_item` / `sys_dict_attr` 及 `_i18n`）。"""
    leftovers = [name for name in table_names() if name.startswith("sys_dict")]
    assert leftovers == []


@pytest.mark.kiwi_id(2372)
def test_no_inline_data_source_key_literals() -> None:
    """声明表之外的源码不得写 `data_source_key="字面量"`（改 key 只改枚举与规格两处）。"""
    offenders: ConcurrentStableList[str] = ConcurrentStableList()
    for path in sorted(_BACKEND_ROOT.glob("**/src/**/*.py")):
        relative = path.relative_to(_BACKEND_ROOT).as_posix()
        if relative in _DECLARATION_FILES:
            continue
        text = path.read_text(encoding="utf-8")
        if 'data_source_key="' in text:
            offenders.add(relative)
    assert list(offenders) == []
