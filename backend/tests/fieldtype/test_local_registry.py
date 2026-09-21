"""字段类型真实注册表用例（Kiwi 963，02-4-27）：内建类型注册 / 校验 / 列类型 / 未知类型。

- `dict` / `dict_multi` 的 `render_metadata` 与前端 `FIELD_WIDGET_MAP`（`dict-select` / `dict-multi`）对齐；
- 校验为类型级（空值放行，必填由字段规则承载）。
"""

import pytest

from app.core.exceptions import NotFoundError
from app.fieldtype.local import LocalFieldTypeRegistry


@pytest.mark.kiwi_id(963)
def test_local_registry_registers_builtin_types() -> None:
    """内建类型注册：键齐备（含 dict / dict_multi）与解析。"""
    registry = LocalFieldTypeRegistry()
    keys = registry.keys()
    for name in (
        "text",
        "longtext",
        "number",
        "datetime",
        "select",
        "multi_select",
        "switch",
        "file",
        "dict",
        "dict_multi",
    ):
        assert name in keys
    assert registry.get("dict") is not None
    assert registry.get("ghost") is None


@pytest.mark.kiwi_id(963)
def test_dict_field_type_validate_and_metadata() -> None:
    """`dict` / `dict_multi`：校验、渲染元数据（widget / multiple）与列类型。"""
    registry = LocalFieldTypeRegistry()
    assert registry.validate("dict", "enabled") == ()
    assert registry.validate("dict", 1) != ()
    assert registry.validate("dict_multi", ["a", "b"]) == ()
    assert registry.validate("dict_multi", "a") != ()
    assert registry.validate("dict", "") == ()

    metadata = registry.get("dict")
    assert metadata is not None
    assert metadata.render_metadata() == {"widget": "dict-select", "multiple": False}
    multi = registry.get("dict_multi")
    assert multi is not None
    assert multi.render_metadata() == {"widget": "dict-multi", "multiple": True}
    assert registry.column_type("dict", "sqlite") == "varchar(64)"
    assert registry.column_type("dict_multi", "sqlite") == "text"


@pytest.mark.kiwi_id(963)
def test_unknown_field_type_raises() -> None:
    """未知字段类型：校验 / 列类型抛 `NotFoundError`（10002 / 404 语义）。"""
    registry = LocalFieldTypeRegistry()
    with pytest.raises(NotFoundError):
        registry.validate("ghost", "x")
    with pytest.raises(NotFoundError):
        registry.column_type("ghost", "sqlite")
