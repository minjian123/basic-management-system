"""repositories 层数据库实现：BaseDbRepository（异步 CRUD / 作用域 SQL / 软删除 / 乐观锁）。

- 会话经构造注入（`get_db` / `get_write_db` / `get_uow` 同一请求同会话）；仓储只 `flush`
  不 `commit`，事务边界归服务层工作单元。
- 作用域条件（软删除 → 数据范围 → 租户）统一翻译为 SQL WHERE；写入字段严格白名单，
  租户 `create` 注入 / `update` 禁改；乐观锁冲突经 `_guard_version` 统一转 409。
- 排序为基础实现（白名单字段 → ORDER BY，默认 `id` 升序）；四库 NULLS 口径、排序字段
  索引配合与分页限深归 01_04；查询一律不拼用户原始输入。
"""

from abc import ABC
from collections.abc import Callable, Sequence
from typing import Any, ClassVar, cast

from sqlalchemy import ColumnElement, Select, false, func, inspect, select
from sqlalchemy import exists as sa_exists
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from app.core.exceptions import ConfigError
from app.db.tenant import current_tenant_context
from app.models.base import BaseModel
from app.repositories.base_scoped_repository import BaseScopedRepository
from app.schemas.pagination import BaseCursorQuery, BasePageQuery
from app.schemas.sorting import SortDirection, SortSpec
from app.scope.base import ScopeCondition

_WRITE_BLOCKED_FIELDS: frozenset[str] = frozenset(
    {"id", "created_at", "created_by", "updated_at", "updated_by", "deleted_at", "version"}
)
"""写入保留字段：由 ORM 事件 / `soft_delete()` / `version_id_col` 维护，禁止手动赋值。"""


def _build_in(column: InstrumentedAttribute[Any], value: object) -> ColumnElement[bool]:
    """`in` 翻译：空序列恒假（与内存基线 `any(...)` 同义）。

    Args:
        column: 模型列。
        value: 目标值集合。

    Returns:
        ColumnElement[bool]: 条件表达式。

    Raises:
        ConfigError: 值不是序列。
    """
    if not isinstance(value, (list, tuple, set, frozenset)):
        raise ConfigError("作用域条件 `in` 的值须为序列")
    members = list(cast("list[object] | tuple[object, ...] | set[object] | frozenset[object]", value))
    if not members:
        return false()
    return column.in_(members)


def _build_like(column: InstrumentedAttribute[Any], value: object) -> ColumnElement[bool]:
    """`like` 翻译：子串匹配（与内存基线 `target in value` 同义，通配符自动转义）。

    Args:
        column: 模型列。
        value: 目标子串。

    Returns:
        ColumnElement[bool]: 条件表达式。

    Raises:
        ConfigError: 值不是字符串。
    """
    if not isinstance(value, str):
        raise ConfigError("作用域条件 `like` 的值须为字符串")
    return column.contains(value, autoescape=True)


def _build_between(column: InstrumentedAttribute[Any], value: object) -> ColumnElement[bool]:
    """`between` 翻译：闭区间（值须为二元序列）。

    Args:
        column: 模型列。
        value: 区间（两元素）。

    Returns:
        ColumnElement[bool]: 条件表达式。

    Raises:
        ConfigError: 值不是二元序列。
    """
    if not isinstance(value, (list, tuple)):
        raise ConfigError("作用域条件 `between` 的值须为二元序列")
    sequence = cast("list[object] | tuple[object, ...]", value)
    if len(sequence) != 2:
        raise ConfigError("作用域条件 `between` 的值须为二元序列")
    return column.between(sequence[0], sequence[1])


_OPERATOR_BUILDERS: dict[str, Callable[[InstrumentedAttribute[Any], object], ColumnElement[bool]]] = {
    "eq": lambda column, value: column == value,
    "ne": lambda column, value: column != value,
    "in": _build_in,
    "like": _build_like,
    "gt": lambda column, value: column > value,
    "gte": lambda column, value: column >= value,
    "lt": lambda column, value: column < value,
    "lte": lambda column, value: column <= value,
    "between": _build_between,
    "is_null": lambda column, _value: column.is_(None),
    "is_not_null": lambda column, _value: column.is_not(None),
}
"""作用域操作符 → SQL 条件构造器（与内存基线 `_match` 的 11 种操作符一一对应）。"""


class BaseDbRepository[ModelT: BaseModel](BaseScopedRepository[ModelT], ABC):
    """数据库仓储实现：真实异步 CRUD + 作用域过滤 + 软删除 + 乐观锁（会话构造注入）。

    子类声明 `model`（所操作的 ORM 模型）并经依赖注入传入请求级会话；写操作 `flush()`
    后由服务层工作单元提交，仓储不自行 `commit`。
    """

    model: ClassVar[type[BaseModel]]
    """所操作的 ORM 模型（子类声明；泛型参数 `ModelT` 为同一模型的具体类型）。"""

    def __init__(self, session: AsyncSession) -> None:
        """初始化。

        Args:
            session: 请求级异步会话（与服务事务同会话）。
        """
        self._session = session
        self._columns = frozenset(column.key for column in inspect(self.model).columns)

    async def list(self, *, sort: Sequence[SortSpec] | None = None) -> list[ModelT]:
        """查询全部记录（作用域过滤 + 排序，默认 `id` 升序）。

        Args:
            sort: 生效排序规格（经 `_resolve_sort` 白名单校验后传入）。

        Returns:
            list[ModelT]: 记录列表。
        """
        statement = self._apply_sort(self._select(), sort or [])
        result = await self._session.execute(statement)
        return list(result.scalars().all())

    async def get(self, item_id: int) -> ModelT | None:
        """按 ID 查询记录（作用域过滤；已软删 / 不在范围返回 None）。

        Args:
            item_id: 记录 ID。

        Returns:
            ModelT | None: 记录；不存在返回 None。
        """
        statement = self._select().where(self._column("id") == item_id)
        return (await self._session.execute(statement)).scalar_one_or_none()

    async def exists(self, item_id: int) -> bool:
        """记录是否存在（`SELECT EXISTS`，不取整行）。

        Args:
            item_id: 记录 ID。

        Returns:
            bool: 存在 True。
        """
        statement = select(sa_exists().where(self._column("id") == item_id, *self._scope_where()))
        return bool((await self._session.execute(statement)).scalar())

    async def count(self) -> int:
        """记录总数（作用域过滤）。

        Returns:
            int: 记录条数。
        """
        statement = select(func.count()).select_from(self.model).where(*self._scope_where())
        return int((await self._session.execute(statement)).scalar_one())

    async def create(self, **values: object) -> ModelT:
        """创建记录（白名单校验 → 落库 flush，雪花 ID / 审计即时生效）。

        Args:
            **values: 创建字段值（租户仓储自动注入 `tenant_id`）。

        Returns:
            ModelT: 新建记录。

        Raises:
            ConfigError: 字段不在白名单 / 租户值与上下文不一致。
        """
        payload = self._write_values(values, creating=True)
        item = self.model(**payload)
        self._session.add(item)
        await self._session.flush()
        return cast("ModelT", item)

    async def update(self, item_id: int, **values: object) -> ModelT | None:
        """更新记录（作用域内取行 → 赋值 → flush；不存在返回 None）。

        Args:
            item_id: 记录 ID。
            **values: 更新字段值（禁止 `tenant_id`）。

        Returns:
            ModelT | None: 更新后的记录；不存在返回 None。

        Raises:
            ConfigError: 字段不在白名单 / 尝试修改 `tenant_id`。
            ConcurrentConflictError: 乐观锁冲突（`StaleDataError` 转译）。
        """
        payload = self._write_values(values, creating=False)
        item = await self.get(item_id)
        if item is None:
            return None
        for field, value in payload.items():
            setattr(item, field, value)
        async with self._guard_version():
            await self._session.flush()
        return item

    async def delete(self, item_id: int) -> bool:
        """删除记录（`soft_delete_enabled=True` 软删、否则物理删）。

        Args:
            item_id: 记录 ID。

        Returns:
            bool: 删除成功 True；不存在（或不在作用域）False。
        """
        if self.soft_delete_enabled:
            return await self.soft_delete(item_id)
        return await self.hard_delete(item_id)

    async def soft_delete(self, item_id: int) -> bool:
        """软删除记录（置 `deleted_at`；恢复见模型 `restore()`）。

        Args:
            item_id: 记录 ID。

        Returns:
            bool: 删除成功 True；不存在（或不在作用域）False。
        """
        item = await self.get(item_id)
        if item is None:
            return False
        item.soft_delete()
        async with self._guard_version():
            await self._session.flush()
        return True

    async def hard_delete(self, item_id: int) -> bool:
        """物理删除记录（回收站清理 / 运维出口；穿透软删过滤，保留租户与数据范围条件）。

        Args:
            item_id: 记录 ID。

        Returns:
            bool: 删除成功 True；不存在（或不在作用域）False。
        """
        statement = self._select(include_soft_delete=False).where(self._column("id") == item_id)
        item = (await self._session.execute(statement)).scalar_one_or_none()
        if item is None:
            return False
        await self._session.delete(item)
        async with self._guard_version():
            await self._session.flush()
        return True

    async def list_page(self, query: BasePageQuery) -> list[ModelT]:
        """页码分页查询（SQL 侧 `LIMIT/OFFSET`）。

        Args:
            query: 页码分页请求（含排序参数）。

        Returns:
            list[ModelT]: 当前页记录。
        """
        statement = self._apply_sort(self._select(), self._resolve_sort(query))
        statement = statement.limit(query.size).offset((query.page - 1) * query.size)
        result = await self._session.execute(statement)
        return list(result.scalars().all())

    async def list_cursor(self, query: BaseCursorQuery) -> list[ModelT]:
        """游标分页查询（偏移口径：`OFFSET cursor LIMIT limit`；keyset 游标键归 01_04）。

        Args:
            query: 游标分页请求（含排序参数）。

        Returns:
            list[ModelT]: 当前批记录。
        """
        statement = self._apply_sort(self._select(), self._resolve_sort(query))
        offset = int(query.cursor) if query.cursor else 0
        statement = statement.limit(query.limit).offset(offset)
        result = await self._session.execute(statement)
        return list(result.scalars().all())

    def _apply_sort[StatementT](self, statement: StatementT, sort: Sequence[SortSpec]) -> StatementT:
        """排序语句钩子：白名单字段 → 模型列 ORDER BY（未知字段忽略，全忽略回落 `id` 升序）。

        Args:
            statement: 查询语句。
            sort: 生效排序规格。

        Returns:
            StatementT: 附加排序后的语句。
        """
        select_statement = cast("Select[Any]", statement)
        criteria: list[ColumnElement[Any]] = []
        for spec in sort:
            column = self._sort_column(spec.field)
            if column is None:
                continue
            criteria.append(column.asc() if spec.direction is SortDirection.ASC else column.desc())
        if not criteria:
            criteria.append(self._column("id").asc())
        return cast("StatementT", select_statement.order_by(*criteria))

    def _select(self, *, include_soft_delete: bool = True) -> Select[tuple[ModelT]]:
        """基础查询语句：模型全列 + 作用域 WHERE。

        Args:
            include_soft_delete: 是否包含软删除过滤（物理删除出口穿透时为 False）。

        Returns:
            Select[tuple[ModelT]]: 查询语句。
        """
        statement = select(self.model).where(*self._scope_where(include_soft_delete=include_soft_delete))
        return cast("Select[tuple[ModelT]]", statement)

    def _scope_where(self, *, include_soft_delete: bool = True) -> list[ColumnElement[bool]]:
        """作用域条件翻译为 SQL WHERE（次序软删除 → 数据范围 → 租户）。

        Args:
            include_soft_delete: 是否包含软删除过滤。

        Returns:
            list[ColumnElement[bool]]: 条件表达式列表。
        """
        conditions = self._scope_conditions(include_soft_delete=include_soft_delete)
        return [self._condition_expression(condition) for condition in conditions]

    def _condition_expression(self, condition: ScopeCondition) -> ColumnElement[bool]:
        """单条作用域条件 → SQL 条件。

        Args:
            condition: 作用域条件。

        Returns:
            ColumnElement[bool]: 条件表达式。

        Raises:
            ConfigError: 字段不在模型映射列 / 操作符不受支持 / 值形态非法。
        """
        builder = _OPERATOR_BUILDERS.get(condition.operator)
        if builder is None:
            raise ConfigError(f"作用域条件操作符不受支持：{condition.operator}")
        return builder(self._column(condition.field), condition.value)

    def _column(self, field: str) -> InstrumentedAttribute[Any]:
        """字段名 → 模型列对象（非映射列快速失败）。

        Args:
            field: 字段名。

        Returns:
            InstrumentedAttribute[Any]: 模型列。

        Raises:
            ConfigError: 字段不在模型映射列。
        """
        if field not in self._columns:
            raise ConfigError(f"字段不存在：{self.model.__name__}.{field}")
        return cast("InstrumentedAttribute[Any]", getattr(self.model, field))

    def _sort_column(self, field: str) -> InstrumentedAttribute[Any] | None:
        """排序字段 → 模型列（白名单外返回 None，由调用方忽略）。

        Args:
            field: 排序字段。

        Returns:
            InstrumentedAttribute[Any] | None: 模型列；非映射列返回 None。
        """
        if field not in self._columns:
            return None
        return cast("InstrumentedAttribute[Any]", getattr(self.model, field))

    def _write_values(self, values: dict[str, object], *, creating: bool) -> dict[str, object]:
        """写入字段白名单与租户写入口径。

        Args:
            values: 原始字段值。
            creating: 是否创建（区分租户注入与禁改）。

        Returns:
            dict[str, object]: 可写字段值。

        Raises:
            ConfigError: 字段不在模型映射列 / 属保留字段 / 租户写入越界。
        """
        payload: dict[str, object] = {}
        for field, value in values.items():
            if field in _WRITE_BLOCKED_FIELDS:
                raise ConfigError(f"字段不可经仓储写入：{self.model.__name__}.{field}")
            if field not in self._columns:
                raise ConfigError(f"字段不存在：{self.model.__name__}.{field}")
            payload[field] = value
        return self._apply_tenant_scope(payload, creating=creating)

    def _apply_tenant_scope(self, payload: dict[str, object], *, creating: bool) -> dict[str, object]:
        """租户写入口径：create 注入 / 校验，update 禁改。

        Args:
            payload: 已过白名单的字段值。
            creating: 是否创建。

        Returns:
            dict[str, object]: 注入租户后的字段值。

        Raises:
            ConfigError: 模型声明 `tenant_scoped` 但无 `tenant_id` 列 / 租户值与上下文不一致 / 尝试修改租户。
        """
        if not self.tenant_scoped:
            return payload
        tenant_id = current_tenant_context().tenant_id
        if tenant_id is None:
            return payload
        if "tenant_id" not in self._columns:
            raise ConfigError(f"{self.model.__name__} 声明 tenant_scoped 但无 tenant_id 列")
        if not creating:
            if "tenant_id" in payload:
                raise ConfigError("禁止修改 tenant_id（跨租户搬移）")
            return payload
        explicit = payload.get("tenant_id")
        if explicit is None:
            payload["tenant_id"] = tenant_id
        elif explicit != tenant_id:
            raise ConfigError("tenant_id 与当前租户不一致")
        return payload
