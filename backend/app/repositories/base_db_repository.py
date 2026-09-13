"""repositories 层数据库实现骨架：占位，不连库（02-5-1 接入引擎 / 会话）。"""

from app.repositories.base_repository import BaseRepository

_PLACEHOLDER = "数据库实现由 02-5-1 数据访问底座接入"


class BaseDbRepository[ModelT](BaseRepository[ModelT]):
    """数据库实现骨架（占位，不连库）。

    冻结数据库侧继承点：真实实现（异步引擎 / 会话 / 四库方言 / 读写分离）由
    02-5-1 数据访问底座在基类统一切换异步后覆写 CRUD 方法；`exists` 沿用派生链，
    真实实现只需提供 `get` / `count`。
    """

    def list(self) -> list[ModelT]:
        """查询全部（占位）。

        Raises:
            NotImplementedError: 始终抛出（占位）。
        """
        raise NotImplementedError(_PLACEHOLDER)

    def get(self, item_id: int) -> ModelT | None:
        """按 ID 查询（占位）。

        Raises:
            NotImplementedError: 始终抛出（占位）。
        """
        raise NotImplementedError(_PLACEHOLDER)

    def count(self) -> int:
        """记录总数（占位）。

        Raises:
            NotImplementedError: 始终抛出（占位）。
        """
        raise NotImplementedError(_PLACEHOLDER)

    def create(self, **values: object) -> ModelT:
        """创建记录（占位）。

        Raises:
            NotImplementedError: 始终抛出（占位）。
        """
        raise NotImplementedError(_PLACEHOLDER)

    def update(self, item_id: int, **values: object) -> ModelT | None:
        """更新记录（占位）。

        Raises:
            NotImplementedError: 始终抛出（占位）。
        """
        raise NotImplementedError(_PLACEHOLDER)

    def delete(self, item_id: int) -> bool:
        """删除记录（占位）。

        Raises:
            NotImplementedError: 始终抛出（占位）。
        """
        raise NotImplementedError(_PLACEHOLDER)
