"""字典高级查询（`app/dict/query.py`）：属性 schema / 通用条件引擎 / 结果分页。

- `load_attrs`：读 `sys_dict_attr` + i18n（locale 回退）；`operators` 缺省按 `data_type` 派生。
- 条件引擎：条件组（AND/OR 分组树，深度 ≤ `DICT_ADV_MAX_DEPTH`）→ SQLAlchemy 表达式
  （字段 / 操作符白名单 + 参数绑定，**不拼 SQL**）；字段白名单 = 固定字段 + 该类型已定义属性
  （`attr.<attr_key>`，只支持一层键）；属性值经方言适配 JSON 提取（SQLite / MySQL / PostgreSQL 实现，
  达梦按同构口径编写）。
- `advanced_query`：`target=items` 走条件引擎分页；`target=business` 经查询提供者注册表（未注册 404）。
- 扩展属性 `attr_json` **只在本接口返回**（普通取数与缓存链路不返回）。
"""

from collections.abc import AsyncGenerator, Mapping
from contextlib import asynccontextmanager
from typing import Any, cast

from pydantic import Field
from sqlalchemy import ColumnElement, Integer, Numeric, and_, func, not_, or_, select, true
from sqlalchemy import cast as sa_cast
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base import BaseObject
from app.core.exceptions import ParamError
from app.db.registry import EngineRegistry
from app.db.session import session_scope
from app.dict.models import SysDictAttr, SysDictAttrI18n, SysDictItem, SysDictItemI18n, SysDictType
from app.dict.sql import current_dict_locale
from app.i18n.base import DEFAULT_LOCALE
from app.query.base import BaseQueryProviderRegistry
from app.schemas.base import BaseSchema

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
"""固定可查字段（除扩展属性外）。"""

DICT_FIXED_FIELD_TYPES: Mapping[str, str] = {
    "value": "text",
    "label": "text",
    "code": "text",
    "sort": "number",
    "status": "enum",
}
"""固定字段数据类型。"""

DICT_OPERATORS_BY_TYPE: Mapping[str, tuple[str, ...]] = {
    "text": ("eq", "ne", "contains", "not_contains", "starts_with", "is_null", "not_null", "in", "not_in"),
    "number": ("eq", "ne", "gt", "lt", "between", "is_null", "not_null", "in", "not_in"),
    "date": ("eq", "ne", "gt", "lt", "between", "is_null", "not_null"),
    "enum": ("eq", "ne", "in", "not_in", "is_null", "not_null"),
    "bool": ("eq", "ne", "is_null", "not_null"),
}
"""按数据类型派生的可用操作符（属性未声明 operators 时的缺省）。"""

_ALL_OPERATORS: frozenset[str] = frozenset(
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
    """属性 schema（高级查询条件字段）。"""

    attr_key: str = Field(description="属性键")
    name: str = Field(description="属性名（按 locale）")
    data_type: str = Field(description="数据类型（text/number/date/enum/bool）")
    operators: tuple[str, ...] = Field(default=(), description="可用操作符")
    widget: str | None = Field(default=None, description="值控件")
    options: tuple[dict[str, object], ...] = Field(default=(), description="enum 选项集")
    sort: int = Field(default=0, description="排序值")
    scope: str = Field(default="platform", description="属性来源（platform/tenant）")


class DictQueryProviderInfo(BaseSchema):
    """查询提供者清单项（发现—选择—调用）。"""

    key: str = Field(description="提供者标识")
    name: str = Field(description="显示名")
    target: str = Field(default="business", description="目标（items/business）")
    dict_types: tuple[str, ...] = Field(default=(), description="适用字典类型（空 = 全部）")
    param_schema: dict[str, object] = Field(default_factory=dict[str, object], description="参数 JSON Schema 子集")


class DictAdvItem(BaseSchema):
    """高级查询结果条目（普通字段 + 扩展属性子集）。"""

    value: str = Field(description="条目值")
    label: str = Field(description="条目标签（按 locale）")
    code: str = Field(default="", description="条目编码")
    parent_id: str | None = Field(default=None, description="级联父值")
    sort: int = Field(default=0, description="排序值")
    status: str = Field(default="enabled", description="状态")
    color: str | None = Field(default=None, description="语义色")
    attr: dict[str, object] | None = Field(default=None, description="扩展属性子集（仅本接口返回）")


class DictAdvQueryResult(BaseSchema):
    """高级查询结果（`items` 取项 / `rows` 业务筛选二选一）。"""

    items: tuple[DictAdvItem, ...] = Field(default=(), description="字典条目（target=items）")
    rows: tuple[dict[str, object], ...] = Field(default=(), description="业务记录（target=business）")
    total: int = Field(default=0, description="命中总数")
    page: int = Field(default=1, description="页码（自 1）")
    size: int = Field(default=DICT_ADV_PAGE_SIZE_DEFAULT, description="页长")


class DictAdvQueryPayload(BaseSchema):
    """高级查询请求体（统一入口）。"""

    target: str = Field(default="items", description="目标（items/business）")
    conditions: dict[str, object] | None = Field(default=None, description="条件组 JSON")
    provider: str | None = Field(default=None, description="查询提供者键（target=business）")
    params: dict[str, object] | None = Field(default=None, description="提供者参数")
    page: int = Field(default=1, description="页码（自 1）")
    size: int = Field(default=DICT_ADV_PAGE_SIZE_DEFAULT, description="页长（≤ 100）")


class DictQueryService(BaseObject):
    """字典高级查询服务（属性 schema 读取 + 条件引擎 + 分页执行）。"""

    def __init__(self, *, engines: EngineRegistry) -> None:
        """初始化。

        Args:
            engines: 多租户引擎注册表。
        """
        self._engines = engines

    async def load_attrs(self, dict_type: str, locale: str | None = None) -> tuple[DictAttrInfo, ...]:
        """读属性 schema（i18n 回退 + 排序）。

        Args:
            dict_type: 字典类型码。
            locale: 语言（缺省当前请求语言）。

        Returns:
            tuple[DictAttrInfo, ...]: 属性清单。
        """
        lang = locale or current_dict_locale.get() or DEFAULT_LOCALE
        async with self._session() as session:
            type_row = await _load_type(session, dict_type)
            if type_row is None:
                return ()
            stmt = (
                select(SysDictAttr, SysDictAttrI18n.name)
                .outerjoin(
                    SysDictAttrI18n,
                    and_(SysDictAttrI18n.dict_attr_id == SysDictAttr.id, SysDictAttrI18n.locale == lang),
                )
                .where(
                    SysDictAttr.type_id == type_row.id,
                    SysDictAttr.status == "enabled",
                    SysDictAttr.deleted_at.is_(None),
                )
                .order_by(SysDictAttr.sort, SysDictAttr.id)
            )
            rows = (await session.execute(stmt)).all()
        result: list[DictAttrInfo] = []
        for attr, i18n_name in rows:
            operators = tuple(attr.operators) if attr.operators else DICT_OPERATORS_BY_TYPE.get(attr.data_type, ())
            options = tuple(attr.options) if attr.options else ()
            result.append(
                DictAttrInfo(
                    attr_key=attr.attr_key,
                    name=str(i18n_name or attr.name),
                    data_type=attr.data_type,
                    operators=operators,
                    widget=attr.widget,
                    options=options,
                    sort=attr.sort,
                    scope=attr.scope,
                )
            )
        return tuple(result)

    async def advanced_query(
        self,
        dict_type: str,
        payload: DictAdvQueryPayload,
        *,
        registry: BaseQueryProviderRegistry | None = None,
    ) -> DictAdvQueryResult:
        """执行高级查询（items 条件引擎 / business 提供者）。

        Args:
            dict_type: 字典类型码。
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
            params = dict(payload.params or {})
            params.setdefault("dict_type", dict_type)
            params["page"] = page
            params["size"] = size
            result = await registry.query(key, params)
            return DictAdvQueryResult(
                rows=tuple(dict(row) for row in result.rows),
                total=result.total,
                page=page,
                size=size,
            )
        locale = current_dict_locale.get() or DEFAULT_LOCALE
        attrs = {info.attr_key: info for info in await self.load_attrs(dict_type, locale)}
        async with self._session() as session:
            type_row = await _load_type(session, dict_type)
            if type_row is None:
                return DictAdvQueryResult(page=page, size=size)
            dialect = _dialect_name(session)
            conditions: list[ColumnElement[bool]] = [
                SysDictItem.type_id == type_row.id,
                SysDictItem.status == "enabled",
                SysDictItem.deleted_at.is_(None),
            ]
            if payload.conditions is not None:
                conditions.append(_build_conditions(payload.conditions, attrs, dialect))
            total = int(
                (await session.execute(select(func.count()).select_from(SysDictItem).where(*conditions))).scalar_one()
            )
            stmt = (
                select(SysDictItem, SysDictItemI18n.label)
                .outerjoin(
                    SysDictItemI18n,
                    and_(SysDictItemI18n.dict_item_id == SysDictItem.id, SysDictItemI18n.locale == locale),
                )
                .where(*conditions)
                .order_by(SysDictItem.sort, SysDictItem.id)
                .offset((page - 1) * size)
                .limit(size)
            )
            rows = (await session.execute(stmt)).all()
        items = tuple(
            DictAdvItem(
                value=item.value,
                label=str(i18n_label or item.label),
                code=item.code,
                parent_id=item.parent_id,
                sort=item.sort,
                status=item.status,
                color=item.color,
                attr=dict(item.attr_json) if item.attr_json is not None else None,
            )
            for item, i18n_label in rows
        )
        return DictAdvQueryResult(items=items, total=total, page=page, size=size)

    @asynccontextmanager
    async def _session(self) -> AsyncGenerator[AsyncSession]:
        """租户库会话（统一会话入口：按当前租户上下文取引擎）。

        Yields:
            AsyncSession: 租户库异步会话。
        """
        async with session_scope(self._engines) as session:
            yield session


async def _load_type(session: AsyncSession, dict_type: str) -> SysDictType | None:
    """按类型码取启用类型。

    Args:
        session: 租户库会话。
        dict_type: 字典类型码。

    Returns:
        SysDictType | None: 类型行；不存在 / 停用 / 已删返回 None。
    """
    stmt = select(SysDictType).where(
        SysDictType.type == dict_type,
        SysDictType.status == "enabled",
        SysDictType.deleted_at.is_(None),
    )
    return (await session.execute(stmt)).scalar_one_or_none()


def _dialect_name(session: AsyncSession) -> str:
    """取会话方言名（`sqlite` / `mysql` / `postgresql` / `dm`）。

    Args:
        session: 租户库会话。

    Returns:
        str: 方言名（未识别回落 sqlite）。
    """
    bind = session.get_bind()
    return getattr(getattr(bind, "dialect", None), "name", "sqlite")


def _build_conditions(
    group: Mapping[str, object],
    attrs: Mapping[str, DictAttrInfo],
    dialect: str,
) -> ColumnElement[bool]:
    """把条件组递归构建为 SQL 条件（白名单 + 参数绑定；深度 ≤ 2）。

    Args:
        group: 条件组（`{logic, children}`）。
        attrs: 属性 schema 映射（键为 attr_key）。
        dialect: 方言名。

    Returns:
        ColumnElement[bool]: SQL 条件。

    Raises:
        ParamError: 结构 / 字段 / 操作符非法。
    """
    return _build_group(group, attrs, dialect, depth=1)


def _build_group(
    group: Mapping[str, object],
    attrs: Mapping[str, DictAttrInfo],
    dialect: str,
    *,
    depth: int,
) -> ColumnElement[bool]:
    """递归构建分组条件。

    Args:
        group: 条件组。
        attrs: 属性 schema 映射。
        dialect: 方言名。
        depth: 当前深度（自 1）。

    Returns:
        ColumnElement[bool]: SQL 条件。

    Raises:
        ParamError: 深度 / 结构非法。
    """
    if depth > DICT_ADV_MAX_DEPTH:
        raise ParamError(f"条件组嵌套超过 {DICT_ADV_MAX_DEPTH} 层")
    logic = str(group.get("logic", "AND")).upper()
    if logic not in ("AND", "OR"):
        raise ParamError("条件组逻辑仅支持 AND / OR")
    children = group.get("children")
    if not isinstance(children, list):
        return true()
    raw_children = cast("list[object]", children)
    if len(raw_children) == 0:
        return true()
    parts: list[ColumnElement[bool]] = []
    for child in raw_children:
        if not isinstance(child, Mapping):
            raise ParamError("条件项结构非法")
        item = cast("Mapping[str, object]", child)
        if "children" in item:
            parts.append(_build_group(item, attrs, dialect, depth=depth + 1))
        else:
            parts.append(_build_item(item, attrs, dialect))
    return or_(*parts) if logic == "OR" else and_(*parts)


def _build_item(
    item: Mapping[str, object],
    attrs: Mapping[str, DictAttrInfo],
    dialect: str,
) -> ColumnElement[bool]:
    """构建单个条件项（字段 / 操作符白名单 + 值绑定）。

    Args:
        item: 条件项（`{field, operator, value}`）。
        attrs: 属性 schema 映射。
        dialect: 方言名。

    Returns:
        ColumnElement[bool]: SQL 条件。

    Raises:
        ParamError: 字段 / 操作符非法。
    """
    field = str(item.get("field", ""))
    operator = str(item.get("operator", ""))
    value = item.get("value")
    if operator not in _ALL_OPERATORS:
        raise ParamError(f"不支持的操作符：{operator}")
    expression, data_type = _field_expression(field, attrs, dialect)
    allowed = DICT_OPERATORS_BY_TYPE.get(data_type, ())
    if operator not in allowed:
        raise ParamError(f"操作符 {operator} 不适用于 {data_type} 类型")
    return _apply_operator(expression, data_type, operator, value, dialect)


def _field_expression(
    field: str,
    attrs: Mapping[str, DictAttrInfo],
    dialect: str,
) -> tuple[ColumnElement[Any], str]:
    """解析字段 → SQL 表达式与数据类型。

    Args:
        field: 字段名（固定字段或 `attr.<key>`）。
        attrs: 属性 schema 映射。
        dialect: 方言名。

    Returns:
        tuple[ColumnElement[Any], str]: SQL 表达式与数据类型。

    Raises:
        ParamError: 字段不在白名单。
    """
    if field in DICT_ADV_FIXED_FIELDS:
        column = getattr(SysDictItem, field)
        return cast("ColumnElement[Any]", column), DICT_FIXED_FIELD_TYPES[field]
    if field.startswith("attr."):
        key = field[len("attr.") :]
        info = attrs.get(key)
        if info is None:
            raise ParamError(f"未定义的属性字段：{field}")
        return _json_text(SysDictItem.attr_json, key, dialect), info.data_type
    raise ParamError(f"字段不在白名单：{field}")


def _json_text(column: object, key: str, dialect: str) -> ColumnElement[Any]:
    """按方言生成 JSON 文本提取表达式（一层键）。

    Args:
        column: JSON 列。
        key: 属性键。
        dialect: 方言名。

    Returns:
        ColumnElement[Any]: 提取表达式。
    """
    path = f"$.{key}"
    if dialect == "mysql":
        return cast("ColumnElement[Any]", func.json_unquote(func.json_extract(column, path)))
    if dialect == "postgresql":
        return cast("ColumnElement[Any]", func.json_extract_path_text(column, key))
    if dialect == "dm":
        return cast("ColumnElement[Any]", func.json_value(column, path))
    return cast("ColumnElement[Any]", func.json_extract(column, path))


def _apply_operator(
    expression: ColumnElement[Any],
    data_type: str,
    operator: str,
    value: object,
    dialect: str,
) -> ColumnElement[bool]:
    """按操作符构建条件（空值 / 集合 / 比较 / 模糊）。

    Args:
        expression: 字段表达式。
        data_type: 数据类型。
        operator: 操作符。
        value: 条件值。
        dialect: 方言名。

    Returns:
        ColumnElement[bool]: SQL 条件。

    Raises:
        ParamError: 值非法。
    """
    if operator == "is_null":
        return expression.is_(None)
    if operator == "not_null":
        return expression.is_not(None)
    if operator in ("in", "not_in"):
        values = _as_list(value)
        return expression.in_(values) if operator == "in" else expression.not_in(values)
    if operator in ("contains", "not_contains", "starts_with"):
        text = _as_text(value)
        pattern = f"%{text}%" if operator != "starts_with" else f"{text}%"
        condition = expression.like(pattern)
        return condition if operator != "not_contains" else not_(condition)
    if operator in ("eq", "ne"):
        normalized = _normalize_scalar(value, data_type, dialect)
        return expression == normalized if operator == "eq" else expression != normalized
    if operator in ("gt", "lt"):
        target = _numeric_expression(expression, data_type, dialect)
        return target > value if operator == "gt" else target < value
    if operator == "between":
        low, high = _as_pair(value)
        target = _numeric_expression(expression, data_type, dialect)
        return target.between(low, high)
    raise ParamError(f"不支持的操作符：{operator}")


def _numeric_expression(
    expression: ColumnElement[Any],
    data_type: str,
    dialect: str,
) -> ColumnElement[Any]:
    """数值 / 日期比较表达式（number 经 CAST，date 按 ISO 字符串比较）。

    Args:
        expression: 字段表达式。
        data_type: 数据类型。
        dialect: 方言名。

    Returns:
        ColumnElement[Any]: 比较表达式。
    """
    if data_type == "number":
        return cast("ColumnElement[Any]", sa_cast(expression, Numeric))
    if data_type == "bool" and dialect == "sqlite":
        return cast("ColumnElement[Any]", sa_cast(expression, Integer))
    return expression


def _normalize_scalar(value: object, data_type: str, dialect: str) -> object:
    """归一比较值（bool 在 SQLite 下转 0/1）。

    Args:
        value: 原始值。
        data_type: 数据类型。
        dialect: 方言名。

    Returns:
        object: 归一后的绑定值。
    """
    if data_type == "bool":
        if dialect == "sqlite":
            return 1 if bool(value) else 0
        return "true" if bool(value) else "false"
    if isinstance(value, bool):
        return "true" if value else "false"
    return value


def _as_list(value: object) -> list[object]:
    """条件值 → 列表（单值包成单元素）。

    Args:
        value: 条件值。

    Returns:
        list[object]: 列表。

    Raises:
        ParamError: 值为空。
    """
    if isinstance(value, list):
        items = cast("list[object]", value)
        if not items:
            raise ParamError("in / not_in 需要至少一个值")
        return items
    if value is None:
        raise ParamError("in / not_in 需要至少一个值")
    return [value]


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
