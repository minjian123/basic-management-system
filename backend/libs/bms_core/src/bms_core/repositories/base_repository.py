"""repositories 层基类契约：统一 CRUD 契约、派生方法与数据源 / 分片路由钩子。

- 只定义契约（抽象方法）与路由钩子，不含存储实现。
- 内存基线见 `BaseMemoryRepository`；数据库实现见 `BaseDbRepository`。
- 统一异步签名：CRUD 为 `async def`，写操作退出事务由工作单元管理。
- 分页：页码分页限深由契约层 `BasePageQuery` 校验；游标分页为 **keyset**（排序键 + 主键），
  默认实现按内存镜像口径（`app/repositories/ordering.py`），数据库实现回补 SQL 谓词。
"""

from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator, Sequence
from contextlib import asynccontextmanager
from typing import Any, ClassVar, cast

from sqlalchemy.orm.exc import StaleDataError

from bms_core.core.base import BaseObject
from bms_core.core.context import is_read_only
from bms_core.core.exceptions import ConcurrentConflictError
from bms_core.db.routing import READ_BINDING, WRITE_BINDING
from bms_core.repositories.ordering import is_after_cursor
from bms_core.schemas.cursor import decode_cursor_for, encode_cursor
from bms_core.schemas.pagination import BaseCursorQuery, BasePageQuery
from bms_core.schemas.sorting import BaseSortQuery, SortSpec
from bms_core.scope.base import DataScope
from bms_core.sharding.base import ShardingRouter


class BaseRepository[ModelT](BaseObject, ABC):
    """仓储契约基类：CRUD 契约 + `exists` 派生方法 + 路由 / 排序钩子。"""

    sortable_fields: ClassVar[frozenset[str]] = frozenset()
    """可排序字段白名单（默认空＝不开放排序，排序请求被整体忽略）。"""

    _data_scope: DataScope | None = None
    _sharding_router: ShardingRouter | None = None

    @abstractmethod
    async def list(self, *, sort: Sequence[SortSpec] | None = None) -> list[ModelT]:
        """返回全部记录（传 `sort` 时按规格排序，不传由实现给默认顺序，内存基线按 ID 升序）。

        Args:
            sort: 生效排序规格（经 `_resolve_sort` 白名单校验后传入）。
        """

    @abstractmethod
    async def get(self, item_id: int) -> ModelT | None:
        """按 ID 查询记录；不存在返回 None（仓储层不抛业务异常）。"""

    async def exists(self, item_id: int) -> bool:
        """记录是否存在（派生方法）。

        Args:
            item_id: 记录 ID。

        Returns:
            bool: 存在 True。
        """
        return (await self.get(item_id)) is not None

    @abstractmethod
    async def count(self) -> int:
        """记录总数。"""

    @abstractmethod
    async def create(self, **values: object) -> ModelT:
        """创建记录。"""

    @abstractmethod
    async def update(self, item_id: int, **values: object) -> ModelT | None:
        """更新记录；不存在返回 None。"""

    @abstractmethod
    async def delete(self, item_id: int) -> bool:
        """删除记录；不存在返回 False。"""

    async def list_page(self, query: BasePageQuery) -> list[ModelT]:
        """页码分页查询（派生：内存基线切片；DB 实现回补 LIMIT/OFFSET）。

        Args:
            query: 页码分页请求（含排序参数）。

        Returns:
            list[ModelT]: 当前页记录（已按白名单校验后的排序规格排序）。
        """
        items = await self.list(sort=self._resolve_sort(query))
        start = (query.page - 1) * query.size
        return items[start : start + query.size]

    async def list_cursor(self, query: BaseCursorQuery) -> list[ModelT]:
        """游标分页查询（派生默认：keyset 口径的内存镜像；DB 实现回补 SQL 谓词）。

        Args:
            query: 游标分页请求（含排序参数与游标令牌）。

        Returns:
            list[ModelT]: 当前批记录（已按白名单校验后的排序规格排序）。

        Raises:
            ParamError: 游标非法或与当前排序不一致。
        """
        sort = self.effective_sort(query)
        items = await self.list(sort=sort)
        if not query.cursor:
            return items[: query.limit]
        payload = decode_cursor_for(query.cursor, sort)
        remaining = [
            item for item in items if is_after_cursor(item, sort, payload.values, payload.item_id, id_of=self._item_id)
        ]
        return remaining[: query.limit]

    def effective_sort(self, query: BaseSortQuery | None = None) -> list[SortSpec]:
        """生效排序规格（白名单已过滤；供服务层生成游标与外部读取）。

        Args:
            query: 排序请求（分页请求继承之）；None 表示不排序。

        Returns:
            list[SortSpec]: 生效排序规格。
        """
        return self._resolve_sort(query)

    def build_cursor(self, query: BaseCursorQuery, items: Sequence[ModelT]) -> str | None:
        """生成 keyset 下一批游标（不足一页返回 None）。

        Args:
            query: 游标分页请求（取 `limit` 与排序）。
            items: 本批记录。

        Returns:
            str | None: 下一批游标；本批不足 `limit` 条时 None（已到末页）。

        Raises:
            ParamError: 排序键值类型不支持（游标编码失败）。
        """
        if len(items) < query.limit:
            return None
        last = items[-1]
        sort = self.effective_sort(query)
        return encode_cursor(sort, [getattr(last, spec.field, None) for spec in sort], self._item_id(last))

    def _item_id(self, item: ModelT) -> int:
        """取条目主键（键集比较兜底键）。

        Args:
            item: 记录。

        Returns:
            int: 主键。
        """
        return int(cast("Any", item).id)

    def _resolve_sort(self, query: BaseSortQuery | None) -> list[SortSpec]:
        """排序请求解析钩子：按类属性白名单校验排序规格（类属性为默认、`specs(whitelist=...)` 可覆盖）。

        Args:
            query: 排序请求（分页请求继承之）；None 表示不排序。

        Returns:
            list[SortSpec]: 生效排序规格（白名单外字段已忽略）。
        """
        if query is None:
            return []
        return query.specs(self.sortable_fields)

    def _apply_sort[StatementT](self, statement: StatementT, sort: Sequence[SortSpec]) -> StatementT:
        """排序语句钩子（默认原样返回：非 SQL 实现无需拼接 ORDER BY）。

        数据库实现侧经 `app/repositories/ordering.py::order_criteria` 拼接 ORDER BY
        （NULL 恒末位 + 主键兜底）；字段须经白名单过滤后再解析为模型列，禁止透传用户原始输入。

        Args:
            statement: 查询语句。
            sort: 生效排序规格。

        Returns:
            StatementT: 附加排序后的语句（默认原样返回）。
        """
        del sort
        return statement

    def _resolve_binding(self, *, read_only: bool | None = None) -> str:
        """数据源绑定钩子：只读走读绑定、写走写绑定（本阶段主从同源）。

        Args:
            read_only: 是否只读；None 时取上下文只读标记。

        Returns:
            str: 数据源键（db_key）。
        """
        flag = is_read_only() if read_only is None else read_only
        return READ_BINDING if flag else WRITE_BINDING

    def _apply_data_scope(self, scope: DataScope | None) -> None:
        """数据范围注入钩子（占位：仅挂载；读写过滤随 RBAC 阶段回补）。

        Args:
            scope: 数据范围契约；None 表示不限制。
        """
        self._data_scope = scope

    def _resolve_shard(self, logical_table: str) -> str:
        """分片路由钩子：经 `ShardingRouter` 解析物理表（未注入则不路由）。

        Args:
            logical_table: 逻辑表名。

        Returns:
            str: 物理表名。
        """
        if self._sharding_router is None:
            return logical_table
        return self._sharding_router.resolve(logical_table).physical_table

    @asynccontextmanager
    async def _guard_version(self) -> AsyncGenerator[None]:
        """乐观锁转译：`StaleDataError` → `ConcurrentConflictError`（HTTP 409）。

        Raises:
            ConcurrentConflictError: 版本冲突。
        """
        try:
            yield
        except StaleDataError as exc:
            raise ConcurrentConflictError("并发更新冲突：记录已被其他事务修改") from exc
