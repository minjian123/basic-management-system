"""统一数据源登记注册表用例（Kiwi 2287，02_10；源自 02_09 字典数据源登记）：清单校验、类型 / 注入合并、查询与非法项。"""

import pytest

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.datasource.registry import (
    DATA_SOURCE_CATALOG,
    DataSourceRecord,
    DataSourceRegistry,
    merge_data_source_records,
)


@pytest.mark.kiwi_id(2287)
def test_catalog_is_valid() -> None:
    """构建期清单自身通过离线校验，覆盖 bms 侧字典表与跨项目示例。"""
    registry = DataSourceRegistry()
    assert registry.validate() == []
    assert registry.get("org_dept") is not None
    keys = registry.keys()
    for expected in ("role", "user", "tenant", "config", "module", "icon", "org_dept", "org_post"):
        assert expected in keys


@pytest.mark.kiwi_id(2287)
def test_catalog_kind_and_origin() -> None:
    """类型 / 来源：bms 侧字典表均为 `dict` / `platform`；跨项目示例为 `product` + 产品标识。"""
    registry = DataSourceRegistry()
    assert {record.kind for record in registry.catalog_records()} == {"dict"}
    product = registry.get("org_dept")
    assert product is not None and product.origin == "product" and product.product_key == "mdm" and product.cascade


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
    merged = merge_data_source_records(DATA_SOURCE_CATALOG, (injected,))
    assert merged[-1].data_source_key == "wms_bin"
    registry = DataSourceRegistry(merged)
    assert registry.get("wms_bin") is not None
    assert registry.validate() == []


@pytest.mark.kiwi_id(2287)
def test_validate_reports_issues() -> None:
    """非法项被逐条报出（格式 / 重复 / 缺名 / 类型非法 / 产品缺产品标识 / 策略非法 / 白名单非法）。"""
    records: ConcurrentStableList[DataSourceRecord] = ConcurrentStableList(
        [
            DataSourceRecord(data_source_key="Bad-Key", name="", data_source=""),
            DataSourceRecord(data_source_key="dup", name="重复", data_source="x"),
            DataSourceRecord(data_source_key="dup", name="重复二", data_source="x"),
            DataSourceRecord(data_source_key="kindbad", name="类型", data_source="x", kind="nope"),
            DataSourceRecord(data_source_key="prod", name="产品", origin="product", data_source="x"),
            DataSourceRecord(data_source_key="strat", name="策略", data_source="x", strategies=("nope",)),
            DataSourceRecord(data_source_key="allow", name="白名单", data_source="x", allowlist=("Bad Field",)),
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
