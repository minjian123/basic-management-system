"""SnowflakeIdStr 契约测试（Kiwi 2395）：内部 int、JSON 输出字符串、请求接受字符串。"""

import json

import pytest

from bms_core.core.id import MAX_ID
from bms_core.schemas.base import BaseSchema, SnowflakeIdStr


class _Sample(BaseSchema):
    """ID 字段样例契约：主键 / 逻辑外键 / 审计人 / 非 ID 整数。"""

    id: SnowflakeIdStr
    tenant_id: SnowflakeIdStr | None = None
    created_by: SnowflakeIdStr | None = None
    count: int = 0


@pytest.mark.kiwi_id(2395)
def test_json_output_is_string() -> None:
    """JSON 输出：`id` / `tenant_id` / `created_by` 均为字符串（含 126 位上限值）。"""
    sample = _Sample(id=MAX_ID, tenant_id=str(MAX_ID - 1), created_by=MAX_ID)
    payload = json.loads(sample.model_dump_json())
    assert payload == {
        "id": str(MAX_ID),
        "tenant_id": str(MAX_ID - 1),
        "created_by": str(MAX_ID),
        "count": 0,
    }


@pytest.mark.kiwi_id(2395)
def test_python_dump_keeps_internal_types() -> None:
    """python 模式 dump：`id` / `*_id` 经全局兜底为字符串，`created_by` 保持 int；非 ID 整数不受影响。"""
    sample = _Sample(id=MAX_ID, created_by=MAX_ID, count=3)
    dumped = sample.model_dump()
    assert dumped["id"] == str(MAX_ID)
    assert dumped["created_by"] == MAX_ID
    assert dumped["count"] == 3


@pytest.mark.kiwi_id(2395)
def test_validation_accepts_numeric_string() -> None:
    """请求校验：接受十进制字符串（含补零）并转内部 int。"""
    sample = _Sample.model_validate({"id": str(MAX_ID).zfill(38), "tenant_id": "0"})
    assert sample.id == MAX_ID
    assert sample.tenant_id == 0


@pytest.mark.kiwi_id(2395)
def test_json_schema_validation_integer_serialization_string() -> None:
    """JSON Schema：校验模式为 integer（请求契约不变），序列化模式为 string（响应契约）。"""
    validation = _Sample.model_json_schema(mode="validation")["properties"]
    serialization = _Sample.model_json_schema(mode="serialization")["properties"]
    assert validation["id"]["type"] == "integer"
    assert serialization["id"]["type"] == "string"
    assert serialization["created_by"]["anyOf"][0]["type"] == "string"
    assert serialization["count"]["type"] == "integer"
