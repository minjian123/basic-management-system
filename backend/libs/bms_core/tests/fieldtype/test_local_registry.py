"""字段类型真实注册表用例（Kiwi 963，02-4-27 / 02-14）：内建类型注册 / 校验 / 列类型 / 类型分家。

- `option` / `option_multi`（枚举，选项集常量）默认形态 `radio` / `checkbox`；`dict` / `dict_multi`
  （字典，条目整数 `id`）形态 `dict_select` / `dict_multi`；
- 旧名 `select` / `multi_select` 已废弃且不保留别名；
- 校验为类型级（空值放行，必填由字段规则承载）。
"""

import pytest

from bms_core.core.concurrent import ConcurrentStableDict
from bms_core.core.exceptions import NotFoundError
from bms_core.fieldtype.local import (
    OPTION_DROPDOWN_WIDGET,
    OPTION_MULTI_DROPDOWN_WIDGET,
    LocalFieldTypeRegistry,
    SimpleFieldType,
)


@pytest.mark.kiwi_id(963)
def test_local_registry_registers_builtin_types() -> None:
    """内建类型注册：新键齐备、旧名不存在与解析。"""
    registry = LocalFieldTypeRegistry()
    keys = registry.keys()
    for name in (
        "text",
        "longtext",
        "number",
        "datetime",
        "option",
        "option_multi",
        "switch",
        "file",
        "dict",
        "dict_multi",
    ):
        assert name in keys
    assert "select" not in keys
    assert "multi_select" not in keys
    assert registry.get("dict") is not None
    assert registry.get("ghost") is None


@pytest.mark.kiwi_id(963)
def test_dict_field_type_validate_and_metadata() -> None:
    """`dict` / `dict_multi`：条目整数 id 校验、渲染元数据与列类型。"""
    registry = LocalFieldTypeRegistry()
    assert registry.validate("dict", 1) == ()
    assert registry.validate("dict", "1") != ()
    assert registry.validate("dict", 0) != ()
    assert registry.validate("dict", -1) != ()
    assert registry.validate("dict", True) != ()
    assert registry.validate("dict_multi", [1, 2]) == ()
    assert registry.validate("dict_multi", []) == ()
    assert registry.validate("dict_multi", ["1"]) != ()
    assert registry.validate("dict_multi", [1, 0]) != ()
    assert registry.validate("dict_multi", "1") != ()
    assert registry.validate("dict", "") == ()
    assert registry.validate("dict_multi", None) == ()

    metadata = registry.get("dict")
    assert metadata is not None
    assert metadata.render_metadata() == {"widget": "dict_select", "multiple": False}
    multi = registry.get("dict_multi")
    assert multi is not None
    assert multi.render_metadata() == {"widget": "dict_multi", "multiple": True}
    assert registry.column_type("dict", "sqlite") == "bigint"
    assert registry.column_type("dict_multi", "sqlite") == "text"


@pytest.mark.kiwi_id(963)
def test_option_field_type_metadata_and_column_types() -> None:
    """`option` / `option_multi`：默认形态 radio / checkbox、选项集常量校验与列类型。"""
    registry = LocalFieldTypeRegistry()
    option = registry.get("option")
    assert option is not None
    assert option.render_metadata() == {"widget": "radio", "multiple": False}
    multi = registry.get("option_multi")
    assert multi is not None
    assert multi.render_metadata() == {"widget": "checkbox", "multiple": True}

    assert registry.validate("option", "enabled") == ()
    assert registry.validate("option", 1) != ()
    assert registry.validate("option_multi", ["a", "b"]) == ()
    assert registry.validate("option_multi", [1]) != ()
    assert registry.validate("option_multi", "a") != ()

    for dialect in ("mysql", "postgresql", "dm", "sqlite"):
        assert registry.column_type("option", dialect) == "varchar(64)"
        assert registry.column_type("option_multi", dialect) == "text"

    # 下拉形态语义键已登记（字段属性层 / 前端 06_09 使用；内建默认不产出）。
    assert OPTION_DROPDOWN_WIDGET == "dropdown"
    assert OPTION_MULTI_DROPDOWN_WIDGET == "dropdown-multi"


def test_simple_field_type_validate_kinds_and_describe() -> None:
    """数据驱动字段类型：文本 / 数值 / 布尔 / 字符串数组各形态校验、未知类别放行与元信息描述。"""
    registry = LocalFieldTypeRegistry()
    assert registry.validate("text", "x") == ()
    assert registry.validate("text", 1) != ()
    assert registry.validate("number", 1.5) == ()
    assert registry.validate("number", True) != ()
    assert registry.validate("number", "1") != ()
    assert registry.validate("switch", True) == ()
    assert registry.validate("switch", 1) != ()
    assert registry.validate("option_multi", [1]) != ()
    assert registry.validate("option_multi", []) == ()

    unknown_kind = SimpleFieldType(key="ghost", widget="ghost", kind="bogus")
    assert unknown_kind.validate("anything") == ()
    assert unknown_kind.describe() == "字段类型 ghost（ghost）"


@pytest.mark.kiwi_id(963)
def test_unknown_field_type_raises() -> None:
    """未知字段类型（含已废弃旧名）：校验 / 列类型抛 `NotFoundError`（10002 / 404 语义）。"""
    registry = LocalFieldTypeRegistry()
    with pytest.raises(NotFoundError):
        registry.validate("ghost", "x")
    with pytest.raises(NotFoundError):
        registry.column_type("ghost", "sqlite")
    with pytest.raises(NotFoundError):
        registry.validate("select", "enabled")
    with pytest.raises(NotFoundError):
        registry.validate("multi_select", ["enabled"])


@pytest.mark.kiwi_id(2329)
def test_field_type_metadata_isolation_between_option_and_dict() -> None:
    """类型分家：选项集字段与字典字段的元数据互不混用（widget / 校验口径不同）。"""
    registry = LocalFieldTypeRegistry()
    option = registry.get("option")
    dictionary = registry.get("dict")
    assert option is not None and dictionary is not None
    assert option.render_metadata() != dictionary.render_metadata()
    assert registry.validate("option", "enabled") == ()
    assert registry.validate("dict", "enabled") != ()
    assert isinstance(option.render_metadata(), ConcurrentStableDict)
    assert registry.validate("dict_multi", [1, 2]) == ()
