"""字典数据源登记注册表用例（02_09）：清单校验、注入合并、查询与非法项。"""

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.dict.registry import (
    DICT_CATALOG,
    DictRecord,
    DictRegistry,
    merge_dict_records,
)


def test_catalog_is_valid() -> None:
    """构建期清单自身通过离线校验。"""
    registry = DictRegistry()
    assert registry.validate() == []
    assert registry.get("org_dept") is not None
    keys = registry.keys()
    assert "org_dept" in keys


def test_merge_inject_appends() -> None:
    """注入记录追加在构建期清单之后（插入序）。"""
    injected = DictRecord(
        dict_key="wms_bin",
        name="仓库储位",
        origin="product",
        product_key="biz",
        data_source="biz.wms_bin",
    )
    merged = merge_dict_records(DICT_CATALOG, (injected,))
    assert merged[-1].dict_key == "wms_bin"
    registry = DictRegistry(merged)
    assert registry.get("wms_bin") is not None
    assert registry.validate() == []


def test_validate_reports_issues() -> None:
    """非法项被逐条报出（格式 / 重复 / 缺名 / 产品缺产品标识 / 策略非法 / 白名单非法）。"""
    records: ConcurrentStableList[DictRecord] = ConcurrentStableList(
        [
            DictRecord(dict_key="Bad-Key", name="", data_source=""),
            DictRecord(dict_key="dup", name="重复", data_source="x"),
            DictRecord(dict_key="dup", name="重复二", data_source="x"),
            DictRecord(dict_key="prod", name="产品", origin="product", data_source="x"),
            DictRecord(dict_key="strat", name="策略", data_source="x", strategies=("nope",)),
            DictRecord(dict_key="allow", name="白名单", data_source="x", allowlist=("Bad Field",)),
        ]
    )
    issues = DictRegistry(records).validate()
    joined = "\n".join(issues)
    assert "字典标识格式非法" in joined
    assert "字典标识重复" in joined
    assert "字典名称缺失" in joined
    assert "数据出口标识缺失" in joined
    assert "产品来源缺产品标识" in joined
    assert "策略取值非法" in joined
    assert "白名单字段名格式非法" in joined
