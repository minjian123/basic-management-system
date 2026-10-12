"""系统字段 `form_key` 构建期清单校验（02_11）。"""

import pytest

from bms_core.registry import (
    FORM_CATALOG,
    FormKind,
    FormRecord,
    FormRegistry,
    merge_form_records,
)


@pytest.mark.kiwi_id(2286)
def test_form_catalog_validate_passes() -> None:
    """清单自校验通过（标识格式 / 跨表全局唯一 / 表名唯一 / 类型合法）。"""
    assert list(FormRegistry().validate()) == []


def test_form_key_globally_unique() -> None:
    """`form_key` 跨表全局唯一；表名唯一。"""
    keys = [record.form_key for record in FORM_CATALOG]
    tables = [record.table for record in FORM_CATALOG]
    assert len(keys) == len(set(keys))
    assert len(tables) == len(set(tables))


def test_catalog_kind_valid_and_lookup() -> None:
    """类型取值合法；按标识 / 表名可查。"""
    assert {record.kind for record in FORM_CATALOG} <= {item.value for item in FormKind}
    registry = FormRegistry()
    assert registry.get("role") is not None
    assert registry.by_table("sys_role") is not None
    assert registry.get("__absent__") is None


def test_merge_appends_injected_records() -> None:
    """注入记录并入清单（插入序：清单在前、注入在后），且合并后仍通过校验。"""
    extra = FormRecord(
        form_key="purchase_order",
        table="pur_order",
        name="采购订单",
        kind=FormKind.FORM.value,
        data_source_key="purchase_order",
    )
    merged = merge_form_records(injected=(extra,))
    assert merged[-1].form_key == "purchase_order"
    assert list(FormRegistry(merged).validate()) == []


@pytest.mark.kiwi_id(2287)
def test_form_data_source_backfill_closed() -> None:
    """`form_key → data_source_key` 回填闭合（02_10）：每个 `form_key` 已回填且其数据源已登记。"""
    from bms_core.datasource.registry import DATA_SOURCE_CATALOG

    known = {record.data_source_key for record in DATA_SOURCE_CATALOG}
    for record in FORM_CATALOG:
        assert record.data_source_key, record.form_key
        assert record.data_source_key in known, record.form_key


def test_validate_reports_duplicate_and_bad_format() -> None:
    """反例：跨表重复 / 格式非法 / 数据源标识缺失或非法被拦截。"""
    records = (
        FormRecord(form_key="role", table="sys_role", name="角色"),
        FormRecord(form_key="role", table="sys_role_x", name="重复标识"),
        FormRecord(form_key="Bad-Key", table="sys_bad", name="格式非法"),
        FormRecord(form_key="nosrc", table="sys_nosrc", name="未回填"),
        FormRecord(form_key="badsrc", table="sys_badsrc", name="源格式非法", data_source_key="Bad-Key"),
    )
    from bms_core.core.concurrent import ConcurrentStableList

    issues = list(FormRegistry(ConcurrentStableList(records)).validate())
    assert any("重复" in issue for issue in issues)
    assert any("格式非法" in issue for issue in issues)
    assert any("数据源标识缺失" in issue for issue in issues)
    assert any("数据源标识格式非法" in issue for issue in issues)


@pytest.mark.parametrize("form_key", ["module", "user", "tenant", "identity_provider"])
def test_catalog_contains_expected_keys(form_key: str) -> None:
    """关键字典表标识在清单内。"""
    assert FormRegistry().get(form_key) is not None


def test_catalog_exports_and_validate_remaining_violations() -> None:
    """清单出口（全量副本 / 标识集 / 未登记表回落）与剩余校验分支（表名 / 名称 / 类型 / 状态）。"""
    from bms_core.core.concurrent import ConcurrentStableList

    registry = FormRegistry()
    assert len(registry.catalog_records()) == len(FORM_CATALOG)
    assert registry.keys() == {record.form_key for record in FORM_CATALOG}
    assert registry.by_table("__absent__") is None

    records = (
        FormRecord(form_key="alpha", table="1bad", name="甲", data_source_key="alpha"),
        FormRecord(form_key="beta", table="sys_shared", name="乙", data_source_key="beta"),
        FormRecord(
            form_key="gamma",
            table="sys_shared",
            name="",
            kind="weird",
            status="weird",
            data_source_key="gamma",
        ),
    )
    issues = list(FormRegistry(ConcurrentStableList(records)).validate())
    assert any("表名格式非法" in issue for issue in issues)
    assert any("表名重复登记" in issue for issue in issues)
    assert any("名称缺失" in issue for issue in issues)
    assert any("类型取值非法" in issue for issue in issues)
    assert any("状态取值非法" in issue for issue in issues)
