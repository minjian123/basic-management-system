"""筛选契约测试（Kiwi 781）：操作符复用 / 序列化口径 / 列表筛选请求基类。"""

import pytest

from app.schemas.filters import (
    FILTER_MULTI_SEPARATOR,
    FILTER_OPERATORS,
    BaseFilterQuery,
    FilterSpec,
    serialize_filters,
)
from app.scope.base import SCOPE_OPERATORS


@pytest.mark.kiwi_id(781)
def test_filter_operators_reuse_scope() -> None:
    """筛选操作符复用数据范围白名单（11 种）；默认操作符 eq。"""
    assert FILTER_OPERATORS == SCOPE_OPERATORS
    assert len(FILTER_OPERATORS) == 11
    assert FILTER_MULTI_SEPARATOR == ","
    assert FilterSpec(field="status").operator == "eq"


@pytest.mark.kiwi_id(781)
def test_filter_serialization() -> None:
    """筛选序列化口径：等值直传 / 多值逗号 / 区间 _start·_end / 空值判定。"""
    assert FilterSpec(field="status", value="enabled").serialize() == {"status": "enabled"}
    assert FilterSpec(field="status", operator="in", value=["a", "b"]).serialize() == {"status": "a,b"}
    assert FilterSpec(field="created_at", operator="between", value=["2026-09-01", "2026-09-12"]).serialize() == {
        "created_at_start": "2026-09-01",
        "created_at_end": "2026-09-12",
    }
    assert FilterSpec(field="deleted_at", operator="is_null").serialize() == {"deleted_at_is_null": "1"}
    assert FilterSpec(field="deleted_at", operator="is_not_null").serialize() == {"deleted_at_is_not_null": "1"}
    assert serialize_filters([FilterSpec(field="status", value="enabled"), FilterSpec(field="dept_id", value=3)]) == {
        "status": "enabled",
        "dept_id": 3,
    }


@pytest.mark.kiwi_id(781)
def test_base_filter_query_params() -> None:
    """列表筛选请求：条件 + 关键字合并；空关键字不传。"""
    query = BaseFilterQuery(keyword="zhang", filters=[FilterSpec(field="status", value="enabled")])
    assert query.to_query_params() == {"status": "enabled", "keyword": "zhang"}
    assert BaseFilterQuery().to_query_params() == {}
