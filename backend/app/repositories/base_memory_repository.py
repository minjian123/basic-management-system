"""repositories 层内存基线：BaseMemoryRepository（测试替身 / 骨架期实现）。"""

from abc import abstractmethod

from app.repositories.base_repository import BaseRepository


class BaseMemoryRepository[ModelT](BaseRepository[ModelT]):
    """内存基线仓储：字典存储 + 自增 ID；子类只实现 `_build` / `_apply`。"""

    def __init__(self) -> None:
        self._items: dict[int, ModelT] = {}
        self._next_id = 1

    @abstractmethod
    def _build(self, item_id: int, values: dict[str, object]) -> ModelT:
        """按字段值构造新实体（子类实现）。

        Args:
            item_id: 待分配的自增 ID。
            values: 创建字段值。

        Returns:
            ModelT: 新实体。
        """

    @abstractmethod
    def _apply(self, item: ModelT, values: dict[str, object]) -> ModelT:
        """按字段值生成更新后的实体（子类实现）。

        Args:
            item: 原实体。
            values: 更新字段值。

        Returns:
            ModelT: 更新后的实体。
        """

    def list(self) -> list[ModelT]:
        """返回全部记录（按 ID 升序）。

        Returns:
            list[ModelT]: 记录列表。
        """
        return [self._items[key] for key in sorted(self._items)]

    def get(self, item_id: int) -> ModelT | None:
        """按 ID 查询记录。

        Args:
            item_id: 记录 ID。

        Returns:
            ModelT | None: 存在时返回记录，否则 None。
        """
        return self._items.get(item_id)

    def count(self) -> int:
        """记录总数。

        Returns:
            int: 记录条数。
        """
        return len(self._items)

    def create(self, **values: object) -> ModelT:
        """创建记录并分配自增 ID。

        Args:
            **values: 创建字段值。

        Returns:
            ModelT: 新建记录。
        """
        item = self._build(self._next_id, values)
        self._items[self._next_id] = item
        self._next_id += 1
        return item

    def update(self, item_id: int, **values: object) -> ModelT | None:
        """更新记录。

        Args:
            item_id: 记录 ID。
            **values: 更新字段值。

        Returns:
            ModelT | None: 更新后的记录，不存在时 None。
        """
        item = self._items.get(item_id)
        if item is None:
            return None
        updated = self._apply(item, values)
        self._items[item_id] = updated
        return updated

    def delete(self, item_id: int) -> bool:
        """删除记录。

        Args:
            item_id: 记录 ID。

        Returns:
            bool: 删除成功 True，不存在 False。
        """
        if item_id not in self._items:
            return False
        del self._items[item_id]
        return True
