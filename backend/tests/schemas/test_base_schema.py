"""BaseSchema 公共配置与继承链测试（Kiwi 13）。"""

import pytest

from app.models.demo import Demo
from app.schemas.base import BaseSchema
from app.schemas.demo import DemoCreateRequest, DemoResponse, DemoUpdateRequest


@pytest.mark.kiwi_id(13)
def test_str_strip_whitespace_applies() -> None:
    """字符串字段自动去除首尾空白。"""
    req = DemoCreateRequest(name="  甲  ")
    assert req.name == "甲"


@pytest.mark.kiwi_id(13)
def test_from_attributes_accepts_entity() -> None:
    """from_attributes 允许实体对象直接校验。"""
    resp = DemoResponse.model_validate(Demo(id=1, name="甲"))
    assert resp.id == 1
    assert resp.name == "甲"


@pytest.mark.kiwi_id(13)
def test_demo_schemas_inherit_base_schema() -> None:
    """demo 请求/响应模型继承 BaseSchema（继承约定生效）。"""
    assert issubclass(DemoCreateRequest, BaseSchema)
    assert issubclass(DemoUpdateRequest, BaseSchema)
    assert issubclass(DemoResponse, BaseSchema)
