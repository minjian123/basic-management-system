"""BaseSchema 公共配置、序列化与分页契约测试（Kiwi 13）。"""

import pytest
from pydantic import ValidationError

from app.models.demo import Demo
from app.schemas.base import BaseSchema
from app.schemas.demo import DemoCreateRequest, DemoResponse, DemoUpdateRequest
from app.schemas.pagination import (
    BaseCursorQuery,
    BaseCursorResponse,
    BasePageQuery,
    BasePageResponse,
)


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


@pytest.mark.kiwi_id(13)
def test_schema_to_dict_matches_model_dump() -> None:
    """BaseSchema 序列化走 Pydantic（to_dict == model_dump），to_json 稳定序。"""
    resp = DemoResponse(id=1, name="甲")
    assert resp.to_dict() == resp.model_dump()
    assert resp.to_json() == '{"id": 1, "name": "甲"}'


@pytest.mark.kiwi_id(13)
def test_page_query_defaults_and_bounds() -> None:
    """页码分页请求默认值与范围校验（page≥1、size≤200）。"""
    assert BasePageQuery().model_dump() == {"page": 1, "size": 20}
    with pytest.raises(ValidationError):
        BasePageQuery(page=0)
    with pytest.raises(ValidationError):
        BasePageQuery(size=201)


@pytest.mark.kiwi_id(13)
def test_page_and_cursor_response_contracts() -> None:
    """页码 / 游标分页响应组装与序列化；游标请求默认 cursor 为空。"""
    page = BasePageResponse[DemoResponse](
        list=[DemoResponse(id=1, name="甲")], total=1, page=1, size=20
    )
    assert page.to_dict()["total"] == 1
    assert page.to_dict()["list"] == [{"id": 1, "name": "甲"}]

    cursor = BaseCursorResponse[DemoResponse](list=[], next_cursor=None, has_more=False)
    assert cursor.to_dict() == {"list": [], "next_cursor": None, "has_more": False}

    query = BaseCursorQuery()
    assert (query.cursor, query.limit) == (None, 20)


@pytest.mark.kiwi_id(13)
def test_pagination_inherits_base_schema() -> None:
    """分页契约基类继承 BaseSchema。"""
    for cls in (BasePageQuery, BasePageResponse, BaseCursorQuery, BaseCursorResponse):
        assert issubclass(cls, BaseSchema)
