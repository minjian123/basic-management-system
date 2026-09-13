"""repositories 层基类契约：统一 CRUD 契约、派生方法与数据源 / 分片路由钩子。

- 只定义契约（抽象方法）与路由钩子，不含存储实现。
- 内存基线见 `BaseMemoryRepository`；数据库实现见 `BaseDbRepository`。
- 统一异步签名：CRUD 为 `async def`，写操作退出事务由工作单元管理。
"""

from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.orm.exc import StaleDataError

from app.core.base import BaseObject
from app.core.context import is_read_only
from app.core.exceptions import ConcurrentConflictError
from app.db.routing import READ_BINDING, WRITE_BINDING
from app.schemas.pagination import BaseCursorQuery, BasePageQuery
from app.scope.base import DataScope
from app.sharding.base import ShardingRouter


class BaseRepository[ModelT](BaseObject, ABC):
    """仓储契约基类：CRUD 契约 + `exists` 派生方法 + 路由钩子。"""

    _data_scope: DataScope | None = None
    _sharding_router: ShardingRouter | None = None

    @abstractmethod
    async def list(self) -> list[ModelT]:
        """返回全部记录（顺序由实现定义，内存基线按 ID 升序）。"""

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
            query: 页码分页请求。

        Returns:
            list[ModelT]: 当前页记录。
        """
        items = await self.list()
        start = (query.page - 1) * query.size
        return items[start : start + query.size]

    async def list_cursor(self, query: BaseCursorQuery) -> list[ModelT]:
        """游标分页查询（派生：内存基线按序号切片；DB 实现回补 WHERE 游标）。

        Args:
            query: 游标分页请求。

        Returns:
            list[ModelT]: 当前批记录。
        """
        items = await self.list()
        start = int(query.cursor) if query.cursor else 0
        return items[start : start + query.limit]

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
