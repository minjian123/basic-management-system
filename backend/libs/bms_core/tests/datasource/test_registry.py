"""统一数据源登记注册表用例（Kiwi 2287，02_10；源自 02_09 字典数据源登记）：清单校验、类型 / 注入合并、查询与非法项。"""

import pytest

from bms_core.core.concurrent import ConcurrentStableFrozenList, ConcurrentStableList
from bms_core.core.exceptions import CatalogError
from bms_core.datasource.registry import (
    DATA_SOURCE_CATALOG,
    DataSourceRecord,
    DataSourceRegistry,
    data_source_records_view,
    merge_data_source_records,
    register_data_source_records,
    reset_data_source_records,
)


@pytest.mark.kiwi_id(2287)
def test_catalog_is_valid() -> None:
    """平台内建清单自身通过离线校验（覆盖 bms 侧字典表）；产品条目由产品清单装载、不入常量。"""
    registry = DataSourceRegistry(DATA_SOURCE_CATALOG)
    assert registry.validate() == []
    keys = registry.keys()
    for expected in ("role", "user", "tenant", "config", "module", "icon"):
        assert expected in keys
    assert "org_dept" not in keys


@pytest.mark.kiwi_id(2287)
def test_catalog_kind_and_origin() -> None:
    """类型 / 来源：平台内建条目均为 `dict` / `platform`（产品条目由产品清单装载）。"""
    registry = DataSourceRegistry(DATA_SOURCE_CATALOG)
    assert {record.kind for record in registry.catalog_records()} == {"dict"}
    assert {record.origin for record in registry.catalog_records()} == {"platform"}


@pytest.mark.kiwi_id(2287)
def test_merge_inject_appends() -> None:
    """注入记录追加在构建期清单之后（插入序）。"""
    injected = DataSourceRecord(
        data_source_key="wms_bin",
        name="仓库储位",
        origin="product",
        product_key="biz",
        data_source="biz.wms_bin",
    )
    merged = merge_data_source_records(DATA_SOURCE_CATALOG, ConcurrentStableList((injected,)))
    assert merged[-1].data_source_key == "wms_bin"
    registry = DataSourceRegistry(merged)
    assert registry.get("wms_bin") is not None
    assert registry.validate() == []


@pytest.mark.kiwi_id(2287)
def test_validate_reports_issues() -> None:
    """非法项被逐条报出（格式 / 重复 / 缺名 / 类型非法 / 产品缺产品标识 / 策略非法 / 白名单非法）。"""
    records: ConcurrentStableList[DataSourceRecord] = ConcurrentStableFrozenList(
        [
            DataSourceRecord(data_source_key="Bad-Key", name="", data_source=""),
            DataSourceRecord(data_source_key="dup", name="重复", data_source="x"),
            DataSourceRecord(data_source_key="dup", name="重复二", data_source="x"),
            DataSourceRecord(data_source_key="kindbad", name="类型", data_source="x", kind="nope"),
            DataSourceRecord(data_source_key="prod", name="产品", origin="product", data_source="x"),
            DataSourceRecord(
                data_source_key="strat", name="策略", data_source="x", strategies=ConcurrentStableFrozenList(("nope",))
            ),
            DataSourceRecord(
                data_source_key="allow",
                name="白名单",
                data_source="x",
                allowlist=ConcurrentStableFrozenList(("Bad Field",)),
            ),
        ]
    )
    issues = DataSourceRegistry(records).validate()
    joined = "\n".join(issues)
    assert "数据源标识格式非法" in joined
    assert "数据源标识重复" in joined
    assert "数据源名称缺失" in joined
    assert "数据出口标识缺失" in joined
    assert "类型取值非法" in joined
    assert "产品来源缺产品标识" in joined
    assert "策略取值非法" in joined
    assert "白名单字段名格式非法" in joined


@pytest.mark.kiwi_id(2287)
def test_get_returns_none_for_unregistered_key() -> None:
    """未登记标识取记录返回 `None`（不抛错）。"""
    assert DataSourceRegistry().get("not_registered") is None


@pytest.mark.kiwi_id(2287)
def test_validate_reports_illegal_origin() -> None:
    """来源取值非法被报出（`origin` 不在平台 / 产品两值内）。"""
    records: ConcurrentStableList[DataSourceRecord] = ConcurrentStableList(
        [DataSourceRecord(data_source_key="bad_origin", name="来源非法", data_source="x", origin="vendor")]
    )
    issues = DataSourceRegistry(records).validate()
    assert any("来源取值非法：'bad_origin' → 'vendor'" in issue for issue in issues)


@pytest.mark.kiwi_id(2359)
def test_injected_records_reject_same_key_with_different_value() -> None:
    """产品清单装载的数据源条目同键异值即拒（fail-closed）；同值重复装载幂等。"""
    record = DataSourceRecord(data_source_key="demo_dept", name="部门", data_source="demo.demo.dept")
    try:
        register_data_source_records(ConcurrentStableList([record]))
        with pytest.raises(CatalogError, match="数据源条目同键异值"):
            register_data_source_records(
                ConcurrentStableList(
                    [DataSourceRecord(data_source_key="demo_dept", name="另一个部门", data_source="demo.demo.dept")]
                )
            )
        register_data_source_records(ConcurrentStableList([record]))
        assert "demo_dept" in [item.data_source_key for item in data_source_records_view()]
    finally:
        reset_data_source_records()
