"""排序契约测试（Kiwi 29）：规格解析、方向容错、白名单校验与继承链。"""

import pytest
from pydantic import ValidationError

from app.schemas.base import BaseSchema
from app.schemas.pagination import BaseCursorQuery, BasePageQuery
from app.schemas.sorting import BaseSortQuery, SortDirection, SortSpec


@pytest.mark.kiwi_id(29)
def test_parse_splits_fields_and_maps_directions() -> None:
    """order_by 逗号分隔多值；方向按位置对应，缺位回退 desc。"""
    specs = SortSpec.parse("status,created_at", ["asc"])
    assert [(spec.field, spec.direction) for spec in specs] == [
        ("status", SortDirection.ASC),
        ("created_at", SortDirection.DESC),
    ]


@pytest.mark.kiwi_id(29)
def test_parse_handles_empty_blank_and_duplicate_fields() -> None:
    """空串 / None → 空列表；空白项忽略；重复字段保留首次。"""
    assert SortSpec.parse(None) == []
    assert SortSpec.parse("") == []
    assert SortSpec.parse(" , ") == []

    specs = SortSpec.parse("name,name,created_at", ["asc", "desc", "asc"])
    assert [(spec.field, spec.direction) for spec in specs] == [
        ("name", SortDirection.ASC),
        ("created_at", SortDirection.ASC),
    ]


@pytest.mark.kiwi_id(29)
def test_parse_normalizes_direction_and_ignores_extra_values() -> None:
    """方向大小写归一、非法方向回退 desc；方向数组超长忽略。"""
    specs = SortSpec.parse("a,b,c,d", ["ASC", "up", "desc", "asc"])
    assert [(spec.field, spec.direction) for spec in specs] == [
        ("a", SortDirection.ASC),
        ("b", SortDirection.DESC),
        ("c", SortDirection.DESC),
        ("d", SortDirection.ASC),
    ]


@pytest.mark.kiwi_id(29)
def test_specs_filters_by_whitelist() -> None:
    """白名单外字段忽略该项；whitelist=None 不做过滤（内部可信调用）。"""
    query = BaseSortQuery(order_by="status,secret", order=["asc", "desc"])
    assert [spec.field for spec in query.specs({"status"})] == ["status"]
    assert [spec.field for spec in query.specs()] == ["status", "secret"]
    assert query.specs(frozenset()) == []


@pytest.mark.kiwi_id(29)
def test_sort_spec_and_query_defaults() -> None:
    """默认方向 desc；排序请求默认为空；非法方向被 Pydantic 拒绝。"""
    assert SortSpec(field="name").direction is SortDirection.DESC
    query = BaseSortQuery()
    assert (query.order_by, query.order) == (None, None)
    assert query.specs({"name"}) == []

    with pytest.raises(ValidationError):
        SortSpec.model_validate({"field": "name", "direction": "up"})


@pytest.mark.kiwi_id(29)
def test_inheritance_chain() -> None:
    """继承链：分页请求 → 排序请求 → BaseSchema；SortSpec → BaseSchema。"""
    assert issubclass(BaseSortQuery, BaseSchema)
    assert issubclass(SortSpec, BaseSchema)
    assert issubclass(BasePageQuery, BaseSortQuery)
    assert issubclass(BaseCursorQuery, BaseSortQuery)

    page = BasePageQuery(order_by="name", order=["asc"])
    assert (page.page, page.size) == (1, 20)
    assert [spec.field for spec in page.specs({"name"})] == ["name"]
    assert BaseCursorQuery(order_by="name").specs({"id"}) == []
