"""契约序列化模式 JSON Schema 用例（Kiwi 2228）：字段口径输出 + ID 字符串化 + 运行时不变量。"""

import json

import pytest

from bms_core.schemas.base import (  # pyright: ignore[reportPrivateUsage]
    BaseSchema,
    _stringified_value_schema,  # pyright: ignore[reportPrivateUsage]
    _stringify_id_properties,  # pyright: ignore[reportPrivateUsage]
)


class _Item(BaseSchema):
    """含 ID 与普通整型字段的样本模型（覆盖 `id` / `*_id` / 非 ID 边界）。"""

    id: int
    name: str
    user_id: int | None = None
    count: int = 0
    group_ids: int = 0


class _Wrapper[DataT](BaseSchema):
    """参数化泛型包装样本（对齐统一响应体 `ApiResponse[DataT]` 形态）。"""

    code: int = 0
    data: DataT | None = None


class _Blank(BaseSchema):
    """无字段样本模型（覆盖 ID 改写辅助的「无 `properties`」分支）。"""


@pytest.mark.kiwi_id(2228)
def test_serialization_schema_carries_fields() -> None:
    """序列化模式 JSON Schema 具字段（不再塌陷为空对象），且字段集合与校验模式一致。"""
    serialization = _Item.model_json_schema(mode="serialization")
    validation = _Item.model_json_schema(mode="validation")
    assert serialization.get("properties")
    assert set(serialization["properties"]) == set(validation["properties"])


@pytest.mark.kiwi_id(2228)
def test_serialization_schema_stringifies_id_fields() -> None:
    """`id` / `*_id` 标为字符串（含 `Optional` 联合形态）；非 ID 整型字段保持 integer。"""
    properties = _Item.model_json_schema(mode="serialization")["properties"]
    assert properties["id"]["type"] == "string"
    assert properties["user_id"]["anyOf"][0]["type"] == "string"
    assert properties["user_id"]["anyOf"][1]["type"] == "null"
    assert properties["count"]["type"] == "integer"
    assert properties["group_ids"]["type"] == "integer"


@pytest.mark.kiwi_id(2228)
def test_validation_schema_and_runtime_unchanged() -> None:
    """校验模式 schema 与运行时序列化行为均不变（ID 字符串化照旧）。"""
    validation = _Item.model_json_schema(mode="validation")
    assert validation["properties"]["id"]["type"] == "integer"

    item = _Item(id=7, name="甲", user_id=8, count=3)
    assert item.model_dump() == {"id": "7", "name": "甲", "user_id": "8", "count": 3, "group_ids": 0}
    assert json.loads(item.model_dump_json())["id"] == "7"


@pytest.mark.kiwi_id(2228)
def test_blank_model_and_helper_boundaries() -> None:
    """无字段模型的序列化模式 schema 字段为空的映射；ID 改写辅助对非映射值 / 无字段原样返回。"""
    assert _Blank.model_json_schema(mode="serialization")["properties"] == {}
    assert _stringified_value_schema("integer") == "integer"
    assert _stringify_id_properties({"title": "X"}) == {"title": "X"}


@pytest.mark.kiwi_id(2228)
def test_generic_wrapper_serialization_schema() -> None:
    """参数化泛型包装：序列化模式具 `data` 字段，且嵌套模型定义非空并按 ID 口径输出。"""
    schema = _Wrapper[_Item].model_json_schema(mode="serialization")
    assert schema["properties"]["data"]["anyOf"][0]["$ref"] == "#/$defs/_Item"
    assert schema["$defs"]["_Item"]["properties"]["id"]["type"] == "string"
