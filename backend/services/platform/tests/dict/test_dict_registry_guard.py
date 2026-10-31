"""平台字典规格护栏（Kiwi 2372）：规格 ↔ 登记清单 ↔ 模型列 ↔ 库域 四方一致。

服务侧再放一份（与基座 `test_registry_guard` 同口径）：只改平台服务时基座用例可能不在选测闭包内，
此处保证「规格漏写 / key 拼错 / 表列改名 / 库域写反」在开发环就红。
"""

import pytest

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.datasource.keys import DataSourceKey
from bms_core.datasource.registry import DATA_SOURCE_CATALOG
from bms_core.dict.table import DictTableScope
from bms_core.services.table_registry import table_ownership_view
from bms_platform.domains.platform_registry.sources.dict_specs import (
    DictSourceMode,
    PLATFORM_DICT_SPECS,
)

_REQUIRED_COLUMNS = ("id", "code", "name", "status", "deleted_at")
"""字典表必须具备的列（`code` 作 value、`name` 作 label、`status` 过滤、`deleted_at` 软删）。"""


@pytest.mark.kiwi_id(2372)
def test_specs_cover_all_platform_keys() -> None:
    """规格键集合 == 枚举 == 平台来源的登记项（11 个 table + 1 个 port）。"""
    catalog_platform_keys = {
        record.data_source_key for record in DATA_SOURCE_CATALOG if record.origin == "platform"
    }
    assert set(PLATFORM_DICT_SPECS.keys()) == catalog_platform_keys
    assert set(PLATFORM_DICT_SPECS.keys()) == {key.value for key in DataSourceKey}


@pytest.mark.kiwi_id(2372)
def test_specs_table_columns_exist() -> None:
    """规格映射的列在模型表上真实存在（改列名 / 换表即刻暴露）。"""
    missing: ConcurrentStableList[str] = ConcurrentStableList()
    for key, spec in PLATFORM_DICT_SPECS.items():
        columns = spec.table.c
        for column in _REQUIRED_COLUMNS:
            if column not in columns:
                missing.add(f"{key}:{spec.table.name}.{column}")
        if spec.value_column not in columns:
            missing.add(f"{key}:{spec.table.name}.{spec.value_column}(value)")
        if spec.label_column not in columns:
            missing.add(f"{key}:{spec.table.name}.{spec.label_column}(label)")
        if spec.sort_column is not None and spec.sort_column not in columns:
            missing.add(f"{key}:{spec.table.name}.{spec.sort_column}(sort)")
    assert list(missing) == []


@pytest.mark.kiwi_id(2372)
def test_specs_i18n_relation_column_exists() -> None:
    """i18n 附表的关联列 / 语言列 / 文案列都存在。"""
    missing: ConcurrentStableList[str] = ConcurrentStableList()
    for key, spec in PLATFORM_DICT_SPECS.items():
        if spec.i18n is None:
            continue
        columns = spec.i18n.table.c
        for column in (spec.i18n.relation_column, spec.i18n.locale_column, spec.i18n.name_column):
            if column not in columns:
                missing.add(f"{key}:{spec.i18n.table.name}.{column}")
    assert list(missing) == []


@pytest.mark.kiwi_id(2372)
def test_specs_db_scope_matches_table_registry() -> None:
    """规格的库域与表登记的 `datasource` 一致（写反会把租户数据读到平台库）。"""
    datasource_by_table = {record.table_name: record.datasource for record in table_ownership_view()}
    mismatched: ConcurrentStableList[str] = ConcurrentStableList()
    for key, spec in PLATFORM_DICT_SPECS.items():
        registered = datasource_by_table.get(spec.table.name)
        expected = DictTableScope.PLATFORM.value if registered == "platform" else DictTableScope.TENANT.value
        if registered is not None and spec.db_scope != expected:
            mismatched.add(f"{key}:{spec.table.name} 登记 {registered} / 规格 {spec.db_scope}")
    assert list(mismatched) == []


@pytest.mark.kiwi_id(2372)
def test_role_uses_port_mode_others_table() -> None:
    """`role` 走域读面（保留角色域过滤语义），其余 11 个走表源（无 per-key 代码）。"""
    assert PLATFORM_DICT_SPECS[DataSourceKey.ROLE.value].mode == DictSourceMode.PORT.value
    table_modes = {spec.mode for key, spec in PLATFORM_DICT_SPECS.items() if key != DataSourceKey.ROLE.value}
    assert table_modes == {DictSourceMode.TABLE.value}


@pytest.mark.kiwi_id(2372)
def test_i18n_only_on_tables_that_have_it() -> None:
    """只有带 `_i18n` 附表的 4 张表声明 i18n（module / business / action / icon）。"""
    with_i18n = {key for key, spec in PLATFORM_DICT_SPECS.items() if spec.i18n is not None}
    assert with_i18n == {
        DataSourceKey.MODULE.value,
        DataSourceKey.BUSINESS.value,
        DataSourceKey.ACTION.value,
        DataSourceKey.ICON.value,
    }
