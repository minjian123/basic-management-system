"""字典高级查询（02_09 改指）：条件引擎（Python 过滤）+ 结果分页。

- 数据源：经**统一出口**（`BaseDataSource`）按 `data_source_key` 取条目，**不再查字典类型 / 属性表**。
- `load_attrs`：无扩展属性表；返回**固定字段** schema（`value` / `label` / `code` / `sort` / `status`）。
- 条件引擎：条件组（AND/OR 分组树，深度 ≤ `DICT_ADV_MAX_DEPTH`）——字段 / 操作符白名单 + 值比较，
  在条目集上做 Python 过滤（不拼 SQL）。
- `advanced_query`：`target=items` 走条件引擎分页；`target=business` 经查询提供者注册表（未注册 404）。
"""

from collections.abc import Mapping
from typing import Annotated, cast

from pydantic import Field

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList, ConcurrentStableSet
from bms_core.core.exceptions import ParamError
from bms_core.core.objects import BaseFrameworkObject
from bms_core.dict.base import BaseDataSource, DictItem, DictQuery
from bms_core.query.base import BaseQueryProviderRegistry
from bms_core.schemas.base import CONTRACT_COLLECTION, CONTRACT_STABLE_DICT, BaseSchema

__all__ = [
    "DICT_ADV_FIXED_FIELDS",
    "DICT_ADV_MAX_DEPTH",
    "DICT_ADV_PAGE_SIZE_DEFAULT",
    "DICT_ADV_PAGE_SIZE_MAX",
    "DICT_OPERATORS_BY_TYPE",
    "DictAdvItem",
    "DictAdvQueryPayload",
    "DictAdvQueryResult",
    "DictAttrInfo",
    "DictQueryProviderInfo",
    "DictQueryService",
]

DICT_ADV_MAX_DEPTH = 2
"""条件组最大嵌套深度（与组件设计口径一致）。"""

DICT_ADV_PAGE_SIZE_DEFAULT = 20
"""高级查询缺省页长。"""

DICT_ADV_PAGE_SIZE_MAX = 100
"""高级查询页长上限。"""

DICT_ADV_FIXED_FIELDS: tuple[str, ...] = ("value", "label", "code", "sort", "status")
"""固定可查字段。"""

DICT_FIXED_FIELD_TYPES: ConcurrentStableDict[str, str] = ConcurrentStableDict(
    {
        "value": "text",
        "label": "text",
        "code": "text",
        "sort": "number",
        "status": "enum",
    }
)
"""固定字段数据类型。"""

DICT_OPERATORS_BY_TYPE: ConcurrentStableDict[str, tuple[str, ...]] = ConcurrentStableDict(
    {
        "text": ("eq", "ne", "contains", "not_contains", "starts_with", "is_null", "not_null", "in", "not_in"),
        "number": ("eq", "ne", "gt", "lt", "between", "is_null", "not_null", "in", "not_in"),
        "date": ("eq", "ne", "gt", "lt", "between", "is_null", "not_null"),
        "enum": ("eq", "ne", "in", "not_in", "is_null", "not_null"),
        "bool": ("eq", "ne", "is_null", "not_null"),
    }
)
"""按数据类型派生的可用操作符。"""

_ALL_OPERATORS: ConcurrentStableSet[str] = ConcurrentStableSet(
    {
        "eq",
        "ne",
        "contains",
        "not_contains",
        "starts_with",
        "between",
        "gt",
        "lt",
        "is_null",
        "not_null",
        "in",
        "not_in",
    }
)
"""全部合法操作符（防注入白名单）。"""


class DictAttrInfo(BaseSchema):
    """属性 schema（高级查询条件字段；本期为固定字段）。"""

    attr_key: str = Field(description="字段键")
    name: str = Field(description="字段名")
    data_type: str = Field(description="数据类型（text/number/enum）")
    operators: tuple[str, ...] = Field(default=(), description="可用操作符")
    widget: str | None = Field(default=None, description="值控件")
    options: tuple[Annotated[ConcurrentStableDict[str, object], CONTRACT_COLLECTION], ...] = Field(
        default=(), description="枚举选项集"
    )
    sort: int = Field(default=0, description="排序值")
    scope: str = Field(default="platform", description="来源（platform/tenant）")


class DictQueryProviderInfo(BaseSchema):
    """查询提供者清单项（发现—选择—调用）。"""

    key: str = Field(description="提供者标识")
    name: str = Field(description="显示名")
    target: str = Field(default="business", description="目标（items/business）")
    data_source_keys: tuple[str, ...] = Field(default=(), description="适用字典标识（空 = 全部）")
    param_schema: Annotated[ConcurrentStableDict[str, object], CONTRACT_COLLECTION] = Field(
        default_factory=CONTRACT_STABLE_DICT, description="参数 JSON Schema 子集"
    )


class DictAdvItem(BaseSchema):
    """高级查询结果条目（普通字段）。"""

    value: str = Field(description="条目值")
    label: str = Field(description="条目标签（按 locale）")
    code: str = Field(default="", description="条目编码")
    parent_id: str | None = Field(default=None, description="上级条目 ID")
    sort: int = Field(default=0, description="排序值")
    status: str = Field(default="enabled", description="状态")
    color: str | None = Field(default=None, description="语义色")


class DictAdvQueryResult(BaseSchema):
    """高级查询结果（`items` 取项 / `rows` 业务筛选二选一）。"""

    items: tuple[DictAdvItem, ...] = Field(default=(), description="字典条目（target=items）")
    rows: tuple[Annotated[ConcurrentStableDict[str, object], CONTRACT_COLLECTION], ...] = Field(
        default=(), description="业务记录（target=business）"
    )
    total: int = Field(default=0, description="命中总数")
    page: int = Field(default=1, description="页码（自 1）")
    size: int = Field(default=DICT_ADV_PAGE_SIZE_DEFAULT, description="页长")


class DictAdvQueryPayload(BaseSchema):
    """高级查询请求体（统一入口）。"""

    target: str = Field(default="items", description="目标（items/business）")
    conditions: Annotated[ConcurrentStableDict[str, object] | None, CONTRACT_COLLECTION] = Field(
        default=None, description="条件组 JSON"
    )
    provider: str | None = Field(default=None, description="查询提供者键（target=business）")
    params: Annotated[ConcurrentStableDict[str, object] | None, CONTRACT_COLLECTION] = Field(
        default=None, description="提供者参数"
    )
    page: int = Field(default=1, description="页码（自 1）")
    size: int = Field(default=DICT_ADV_PAGE_SIZE_DEFAULT, description="页长（≤ 100）")


class DictQueryService(BaseFrameworkObject):
    """字典高级查询服务（固定字段 schema + 条件引擎 + 分页执行；经统一出口取数）。"""

    def __init__(self, *, source: BaseDataSource) -> None:
        """初始化。

        Args:
            source: 字典统一出口取数契约。
        """
        self._source = source

    async def load_attrs(self, data_source_key: str, locale: str | None = None) -> tuple[DictAttrInfo, ...]:
        """返回固定字段 schema（无扩展属性表）。

        Args:
            data_source_key: 字典标识。
            locale: 语言（本期固定字段不分语言，保留参数以兼容调用面）。

        Returns:
            tuple[DictAttrInfo, ...]: 固定字段清单。
        """
        result: ConcurrentStableList[DictAttrInfo] = ConcurrentStableList()
        for index, field in enumerate(DICT_ADV_FIXED_FIELDS):
            data_type = DICT_FIXED_FIELD_TYPES.get(field, "text")
            result.add(
                DictAttrInfo(
                    attr_key=field,
                    name=field,
                    data_type=data_type,
                    operators=DICT_OPERATORS_BY_TYPE.get(data_type, ()),
                    widget=None,
                    options=(),
                    sort=index,
                    scope="platform",
                )
            )
        return tuple(result)

    async def advanced_query(
        self,
        data_source_key: str,
        payload: DictAdvQueryPayload,
        *,
        registry: BaseQueryProviderRegistry | None = None,
    ) -> DictAdvQueryResult:
        """执行高级查询（items 条件引擎 / business 提供者）。

        Args:
            data_source_key: 字典标识。
            payload: 查询请求体。
            registry: 查询提供者注册表（`target=business` 必填）。

        Returns:
            DictAdvQueryResult: 分页结果。

        Raises:
            ParamError: 目标 / 条件 / 提供者非法。
        """
        page = max(1, payload.page)
        size = min(max(1, payload.size), DICT_ADV_PAGE_SIZE_MAX)
        if payload.target == "business":
            if registry is None:
                raise ParamError("查询提供者注册表未就绪")
            key = payload.provider or "builtin"
            params: ConcurrentStableDict[str, object] = (
                ConcurrentStableDict(payload.params) if payload.params is not None else ConcurrentStableDict()
            )
            params.put_if_absent("data_source_key", data_source_key)
            params.set("page", page)
            params.set("size", size)
            result = await registry.query(key, params)
            return DictAdvQueryResult(
                rows=tuple(ConcurrentStableDict(row) for row in result.rows),
                total=result.total,
                page=page,
                size=size,
            )
        loaded = await self._source.by_type(DictQuery(data_source_key=data_source_key))
        items = tuple(loaded.items or ())
        if payload.conditions is not None:
            items = tuple(item for item in items if _match_group(payload.conditions, item, depth=1))
        total = len(items)
        page_items = items[(page - 1) * size : (page - 1) * size + size]
        return DictAdvQueryResult(
            items=tuple(_to_adv_item(item) for item in page_items),
            total=total,
            page=page,
            size=size,
        )


def _to_adv_item(item: DictItem) -> DictAdvItem:
    """条目 → 高级查询结果条目。

    Args:
        item: 字典条目。

    Returns:
        DictAdvItem: 结果条目。
    """
    return DictAdvItem(
        value=item.value,
        label=item.label,
        code=item.code,
        parent_id=str(item.parent_id) if item.parent_id is not None else None,
        sort=item.sort,
        status=item.status,
        color=item.color,
    )


def _match_group(group: ConcurrentStableDict[str, object], item: DictItem, *, depth: int) -> bool:
    """判定条目是否命中条件组（递归 AND/OR；深度 ≤ 2）。

    Args:
        group: 条件组（`{logic, children}`）。
        item: 字典条目。
        depth: 当前深度（自 1）。

    Returns:
        bool: 命中 True。

    Raises:
        ParamError: 深度 / 逻辑 / 结构非法。
    """
    if depth > DICT_ADV_MAX_DEPTH:
        raise ParamError(f"条件组嵌套超过 {DICT_ADV_MAX_DEPTH} 层")
    logic = str(group.get("logic", "AND")).upper()
    if logic not in ("AND", "OR"):
        raise ParamError("条件组逻辑仅支持 AND / OR")
    children = group.get("children")
    if not isinstance(children, list):
        return True
    raw_children = cast("list[object]", children)
    if len(raw_children) == 0:
        return True
    results: ConcurrentStableList[bool] = ConcurrentStableList()
    for child in raw_children:
        if not isinstance(child, Mapping):
            raise ParamError("条件项结构非法")
        node = ConcurrentStableDict(cast("Mapping[str, object]", child))
        if "children" in node:
            results.add(_match_group(node, item, depth=depth + 1))
        else:
            results.add(_match_item(node, item))
    return any(results) if logic == "OR" else all(results)


def _match_item(node: ConcurrentStableDict[str, object], item: DictItem) -> bool:
    """判定条目是否命中单个条件项。

    Args:
        node: 条件项（`{field, operator, value}`）。
        item: 字典条目。

    Returns:
        bool: 命中 True。

    Raises:
        ParamError: 字段 / 操作符非法。
    """
    field = str(node.get("field", ""))
    operator = str(node.get("operator", ""))
    value = node.get("value")
    if field not in DICT_ADV_FIXED_FIELDS:
        raise ParamError(f"字段不在白名单：{field}")
    if operator not in _ALL_OPERATORS:
        raise ParamError(f"不支持的操作符：{operator}")
    data_type = DICT_FIXED_FIELD_TYPES.get(field, "text")
    if operator not in DICT_OPERATORS_BY_TYPE.get(data_type, ()):
        raise ParamError(f"操作符 {operator} 不适用于 {data_type} 类型")
    actual = getattr(item, field)
    return _compare(actual, operator, value, data_type)


def _compare(actual: object, operator: str, value: object, data_type: str) -> bool:
    """比较条目字段值与条件值。

    Args:
        actual: 条目字段值。
        operator: 操作符。
        value: 条件值。
        data_type: 数据类型。

    Returns:
        bool: 命中 True。

    Raises:
        ParamError: 值非法。
    """
    if operator == "is_null":
        return actual is None
    if operator == "not_null":
        return actual is not None
    if operator in ("in", "not_in"):
        members = _as_list(value)
        hit = any(str(actual) == str(member) for member in members)
        return hit if operator == "in" else not hit
    if operator in ("contains", "not_contains", "starts_with"):
        text = _as_text(value)
        hay = "" if actual is None else str(actual)
        hit = text in hay if operator != "starts_with" else hay.startswith(text)
        return hit if operator != "not_contains" else not hit
    if operator in ("eq", "ne"):
        hit = str(actual) == str(value)
        return hit if operator == "eq" else not hit
    if operator in ("gt", "lt", "between"):
        return _compare_ordered(actual, operator, value)
    raise ParamError(f"不支持的操作符：{operator}")


def _compare_ordered(actual: object, operator: str, value: object) -> bool:
    """有序比较（number 转 float；非法回落字符串比较）。

    Args:
        actual: 条目字段值。
        operator: 操作符（gt/lt/between）。
        value: 条件值。

    Returns:
        bool: 命中 True。

    Raises:
        ParamError: 值非法。
    """
    left = _as_number(actual)
    if operator == "between":
        low, high = _as_pair(value)
        return _as_number(low) <= left <= _as_number(high)
    right = _as_number(value)
    return left > right if operator == "gt" else left < right


def _as_number(value: object) -> float:
    """值 → 数值（非法则取原字符串长度序，仅供有序比较兜底）。

    Args:
        value: 原始值。

    Returns:
        float: 数值（不可转则 0.0）。
    """
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if isinstance(value, int | float):
        return float(value)
    try:
        return float(str(value))
    except ValueError:
        return 0.0


def _as_list(value: object) -> ConcurrentStableList[object]:
    """条件值 → 列表（单值包成单元素）。

    Args:
        value: 条件值。

    Returns:
        ConcurrentStableList[object]: 列表。

    Raises:
        ParamError: 值为空。
    """
    if isinstance(value, list):
        items = cast("list[object]", value)
        if not items:
            raise ParamError("in / not_in 需要至少一个值")
        return ConcurrentStableList(items)
    if value is None:
        raise ParamError("in / not_in 需要至少一个值")
    return ConcurrentStableList([value])


def _as_pair(value: object) -> tuple[object, object]:
    """条件值 → 区间双值。

    Args:
        value: 条件值（长度 2 的列表）。

    Returns:
        tuple[object, object]: 区间双值。

    Raises:
        ParamError: 值非法。
    """
    if isinstance(value, list):
        items = cast("list[object]", value)
        if len(items) == 2:
            return items[0], items[1]
    raise ParamError("between 需要两个值")


def _as_text(value: object) -> str:
    """条件值 → 字符串。

    Args:
        value: 条件值。

    Returns:
        str: 字符串值。

    Raises:
        ParamError: 值为空。
    """
    if value is None:
        raise ParamError("模糊匹配需要文本值")
    return value if isinstance(value, str) else str(value)
