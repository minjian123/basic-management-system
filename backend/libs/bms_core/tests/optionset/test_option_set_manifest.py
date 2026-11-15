# kiwi_id: 2504
"""选项集清单装载、运行时适配与契约派生（任务 09-03-1）。

覆盖：`[[option_sets]]` 解析 → `ManifestOptionSet` 取值 / 判定 → `apply_option_set_contracts`
生成命名组件与 `x-extensible-enum`。
"""

from typing import cast

import pytest

from bms_core.core.concurrent import ConcurrentStableFrozenList
from bms_core.core.exceptions import CatalogError
from bms_core.optionset.base import OptionItem
from bms_core.optionset.contract import apply_option_set_contracts
from bms_core.optionset.manifest import ManifestOptionSet, OptionSetRecord
from bms_core.registry.products import parse_manifest_text

pytestmark = pytest.mark.kiwi_id(2504)

_MANIFEST = """
product_key = "platform"

[[option_sets]]
key = "bms.demo.kind"
name = "示例类型"
contract_name = "DemoKind"
extensible = true
items = [
  { value = "a", label = "甲", label_key = "bms.demo.kind.a", color = "success", sort = 20 },
  { value = "b", label = "乙", color = "warning", disabled = true, sort = 10 },
]
"""


def _record() -> OptionSetRecord:
    """取示例清单中的选项集声明。"""
    return parse_manifest_text(_MANIFEST).option_sets[0]


def _component(openapi: object, name: str) -> object:
    """取组件 schema（契约文档按 JSON 原生结构处理，取用时再收窄类型）。"""
    root = cast("dict[str, object]", openapi)
    components = cast("dict[str, object]", root["components"])
    schemas = cast("dict[str, object]", components["schemas"])
    return schemas[name]


def test_manifest_parses_option_sets() -> None:
    """`[[option_sets]]` 解析为记录：key / 名称 / 契约名 / 可扩展 / 条目字段。"""
    record = _record()

    assert record.option_set_key == "bms.demo.kind"
    assert record.name == "示例类型"
    assert record.contract_name == "DemoKind"
    assert record.extensible is True
    assert [item.value for item in record.items] == ["a", "b"]
    assert record.items[0].label_key == "bms.demo.kind.a"
    assert record.items[1].disabled is True
    assert [item.sort for item in record.items] == [20, 10]


def test_manifest_option_set_adapter() -> None:
    """适配器：条目 / 取值 / 判定 / 元信息。"""
    option_set = ManifestOptionSet(_record())

    assert option_set.key == "bms.demo.kind"
    assert option_set.name == "示例类型"
    assert option_set.describe() == "选项集 bms.demo.kind（清单声明）"
    assert [item.value for item in option_set.items()] == ["a", "b"]
    assert option_set.get("a") == OptionItem(
        value="a", label="甲", label_key="bms.demo.kind.a", color="success", sort=20
    )
    assert option_set.get("absent") is None
    assert list(option_set.validate_value("a")) == []
    assert list(option_set.validate_value("absent")) == ["取值不在选项集 bms.demo.kind 内：'absent'"]


def test_contract_derives_named_component() -> None:
    """字段 `optionSetKey` → 同名组件 + `x-extensible-enum` + 字段 `$ref`（含无描述字段）。"""
    openapi = {
        "components": {
            "schemas": {
                "Sample": {
                    "type": "object",
                    "properties": {
                        "kind": {
                            "type": "string",
                            "description": "类型",
                            "optionSetKey": "bms.demo.kind",
                        },
                        # 无 description 的同值域字段：派生后只留 $ref（不写空描述）
                        "kind_alias": {"type": "string", "optionSetKey": "bms.demo.kind"},
                    },
                }
            }
        }
    }

    apply_option_set_contracts(openapi, [ManifestOptionSet(_record())])

    component = cast("dict[str, object]", _component(openapi, "DemoKind"))
    assert component["type"] == "string"
    assert component["x-extensible-enum"] == ["a", "b"]
    sample = cast("dict[str, object]", _component(openapi, "Sample"))
    properties = cast("dict[str, object]", sample["properties"])
    kind = cast("dict[str, object]", properties["kind"])
    assert kind["$ref"] == "#/components/schemas/DemoKind"
    assert kind["description"] == "类型"
    assert "optionSetKey" not in kind
    alias = cast("dict[str, object]", properties["kind_alias"])
    assert alias == {"$ref": "#/components/schemas/DemoKind"}


def test_contract_skips_unknown_and_non_component() -> None:
    """未登记 key / 无 components 时不报错、不改写。"""
    openapi = {"components": {"schemas": {"Sample": {"type": "string", "optionSetKey": "bms.absent"}}}}
    apply_option_set_contracts(openapi, [ManifestOptionSet(_record())])
    sample = cast("dict[str, object]", _component(openapi, "Sample"))
    assert sample["type"] == "string"
    assert "optionSetKey" not in sample

    apply_option_set_contracts({}, [ManifestOptionSet(_record())])
    apply_option_set_contracts({"components": {}}, [ManifestOptionSet(_record())])
    apply_option_set_contracts({"components": {"schemas": ["not-a-mapping"]}}, [ManifestOptionSet(_record())])
    apply_option_set_contracts(None, [ManifestOptionSet(_record())])


def test_contract_inline_without_contract_name() -> None:
    """无 `contract_name`：就地写扩展键 / enum；无 description 也不报错。"""
    inline_extensible = OptionSetRecord(
        option_set_key="bms.demo.inline",
        name="内联",
        extensible=True,
        items=ConcurrentStableFrozenList((OptionItem(value="a"),)),
    )
    inline_closed = OptionSetRecord(
        option_set_key="bms.demo.closed",
        name="闭集",
        extensible=False,
        items=ConcurrentStableFrozenList((OptionItem(value="b"),)),
    )
    openapi = {
        "components": {
            "schemas": {
                "Sample": {
                    "type": "object",
                    "properties": {
                        "open": {"type": "string", "optionSetKey": "bms.demo.inline"},
                        "closed": {"type": "string", "optionSetKey": "bms.demo.closed"},
                    },
                }
            }
        }
    }

    apply_option_set_contracts(
        openapi,
        [ManifestOptionSet(inline_extensible), ManifestOptionSet(inline_closed)],
    )

    sample = cast("dict[str, object]", _component(openapi, "Sample"))
    properties = cast("dict[str, object]", sample["properties"])
    open_node = cast("dict[str, object]", properties["open"])
    closed_node = cast("dict[str, object]", properties["closed"])
    assert open_node["x-extensible-enum"] == ["a"]
    assert "optionSetKey" not in open_node
    assert closed_node["enum"] == ["b"]
    assert "optionSetKey" not in closed_node


def test_offline_startup_derives_option_sets_from_manifest() -> None:
    """离线口径（无应用实例）：启动校验按仓内清单装载平台选项集；注册表工厂无应用也能建。"""
    from bms_core.application import _validate_data_sources  # pyright: ignore[reportPrivateUsage]
    from bms_core.core.assembly import LocalOptionSetRegistryFactory
    from bms_core.core.config import PluginSelection, get_settings

    settings = get_settings().model_copy(deep=True)
    settings.data_source = PluginSelection(provider="")
    _validate_data_sources(settings)  # pyright: ignore[reportPrivateUsage]
    registry = LocalOptionSetRegistryFactory().create()
    assert list(registry.keys()) == []


def test_manifest_rejects_missing_items() -> None:
    """`[[option_sets]]` 缺 items 数组：结构级拒（CatalogError）。"""
    with pytest.raises(CatalogError, match="选项集缺少 items 数组"):
        parse_manifest_text(
            """
product_key = "platform"

[[option_sets]]
key = "bms.demo.bad"
"""
        )
