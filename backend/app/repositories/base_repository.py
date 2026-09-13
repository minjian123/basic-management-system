"""repositories 层基类契约：统一 CRUD 契约、派生方法与数据源 / 分片路由钩子。

- 只定义契约（抽象方法）与路由钩子，不含存储实现。
- 内存基线见 `BaseMemoryRepository`；数据库实现见 `BaseDbRepository`。
"""

from abc import ABC, abstractmethod

from app.core.base import BaseObject
from app.scope.base import DataScope
from app.sharding.base import ShardingRouter


class BaseRepository[ModelT](BaseObject, ABC):
    """仓储契约基类：CRUD 契约 + `exists` 派生方法 + 路由钩子。"""

    _data_scope: DataScope | None = None
    _sharding_router: ShardingRouter | None = None

    @abstractmethod
    def list(self) -> list[ModelT]:
        """返回全部记录（顺序由实现定义，内存基线按 ID 升序）。"""

    @abstractmethod
    def get(self, item_id: int) -> ModelT | None:
        """按 ID 查询记录；不存在返回 None（仓储层不抛业务异常）。"""

    def exists(self, item_id: int) -> bool:
        """记录是否存在（派生方法）。

        Args:
            item_id: 记录 ID。

        Returns:
            bool: 存在 True。
        """
        return self.get(item_id) is not None

    @abstractmethod
    def count(self) -> int:
        """记录总数。"""

    @abstractmethod
    def create(self, **values: object) -> ModelT:
        """创建记录。"""

    @abstractmethod
    def update(self, item_id: int, **values: object) -> ModelT | None:
        """更新记录；不存在返回 None。"""

    @abstractmethod
    def delete(self, item_id: int) -> bool:
        """删除记录；不存在返回 False。"""

    def _resolve_binding(self, *, read_only: bool) -> str:
        """数据源绑定钩子（占位：单源同源，读写同库）。

        Args:
            read_only: 是否只读请求（供读写分离路由使用）。

        Returns:
            str: 数据源键（db_key）。
        """
        return "default"

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
