"""schemas 层筛选契约：筛选条件（字段 / 操作符 / 值）与列表筛选请求基类。

- 操作符白名单复用数据范围 `SCOPE_OPERATORS`（`eq` / `ne` / `in` / `like` / `gt` / `gte` / `lt` / `lte` /
  `between` / `is_null` / `is_not_null`，11 种），避免两处漂移。
- 序列化口径（《API接口规范》「参数与分页」节）：字段名直传；多值（`in` / `not_in`）逗号分隔；
  区间（`between`）`{field}_start` / `{field}_end`（单边可空）；布尔 1 / 0。
- 与排序契约（`app/schemas/sorting.py`）同源：列表请求 = 分页（`BasePageQuery` / `BaseCursorQuery`）
  + 排序（`BaseSortQuery`）+ 筛选（本模块）。
"""

from collections.abc import Sequence
from typing import cast

from pydantic import Field

from bms_core.schemas.base import BaseSchema
from bms_core.scope.base import SCOPE_OPERATORS

__all__ = [
    "FILTER_MULTI_SEPARATOR",
    "FILTER_OPERATORS",
    "BaseFilterQuery",
    "FilterSpec",
    "serialize_filters",
]

FILTER_OPERATORS: tuple[str, ...] = SCOPE_OPERATORS
"""筛选操作符白名单（复用数据范围操作符，11 种）。"""

FILTER_MULTI_SEPARATOR = ","
"""多值（`in` / `not_in`）分隔符（`field=v1,v2`）。"""


class FilterSpec(BaseSchema):
    """单条筛选条件：字段 + 操作符 + 值。"""

    field: str = Field(description="筛选字段（数据库字段名口径）")
    operator: str = Field(default="eq", description="操作符（取 FILTER_OPERATORS）")
    value: object = Field(default=None, description="筛选值（多值 / 区间用数组）")

    def serialize(self) -> dict[str, object]:
        """按《API接口规范》口径序列化为查询参数。

        Returns:
            dict[str, object]: 查询参数（字段名 → 值）。
        """
        value = self.value
        if isinstance(value, (list, tuple)):
            items = cast("list[object]", value)
            if self.operator == "between" and len(items) == 2:
                return {f"{self.field}_start": items[0], f"{self.field}_end": items[1]}
            if self.operator in ("in", "not_in"):
                joined = FILTER_MULTI_SEPARATOR.join(str(item) for item in items)
                return {self.field: joined}
        if self.operator == "is_null":
            return {f"{self.field}_is_null": "1"}
        if self.operator == "is_not_null":
            return {f"{self.field}_is_not_null": "1"}
        return {self.field: value}


def serialize_filters(filters: Sequence[FilterSpec]) -> dict[str, object]:
    """把筛选条件列表序列化为查询参数（同名字段后者覆盖）。

    Args:
        filters: 筛选条件列表。

    Returns:
        dict[str, object]: 查询参数字典。
    """
    params: dict[str, object] = {}
    for spec in filters:
        params.update(spec.serialize())
    return params


class BaseFilterQuery(BaseSchema):
    """列表筛选请求契约：关键字 + 条件列表。

    与分页 / 排序契约同源（`app/schemas/pagination.py` / `sorting.py`）；列表请求可组合二者。
    """

    keyword: str | None = Field(default=None, description="关键字（跨字段模糊，命中列由后端定义）")
    filters: list[FilterSpec] = Field(default_factory=list[FilterSpec], description="筛选条件列表")

    def to_query_params(self) -> dict[str, object]:
        """序列化为请求查询参数（筛选条件 + 关键字；空关键字不传）。

        Returns:
            dict[str, object]: 查询参数字典。
        """
        params = serialize_filters(self.filters)
        if self.keyword:
            params["keyword"] = self.keyword
        return params
