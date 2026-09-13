"""repositories 层内存基线：BaseMemoryRepository（测试替身 / 骨架期实现）。

排序按契约层 `SortSpec` 规格在内存中完成（多键稳定排序），DB 侧由 `_apply_sort` 占位。
"""

from abc import abstractmethod
from collections.abc import Sequence

from app.repositories.base_scoped_repository import BaseScopedRepository
from app.schemas.sorting import SortDirection, SortSpec


def _sort_key(value: object) -> tuple[int, object]:
    """排序键：空值最大（升序末尾 / 降序首位）；数值与字符串分桶，类型混合按字符串兜底。

    Args:
        value: 实体字段值。

    Returns:
        tuple[int, object]: 可比较的排序键。
    """
    if value is None:
        return (2, "")
    if isinstance(value, bool):
        return (0, int(value))
    if isinstance(value, (int, float)):
        return (0, value)
    if isinstance(value, str):
        return (1, value)
    return (1, str(value))


def _sort_items[ItemT](items: list[ItemT], sort: Sequence[SortSpec] | None) -> list[ItemT]:
    """按排序规格排序（按规格逆序逐次稳定排序，保证主次键语义）。

    Args:
        items: 记录列表（已按默认顺序排列）。
        sort: 排序规格；空表示不排序。

    Returns:
        list[ItemT]: 排序后的记录列表。
    """
    if not sort:
        return items
    result = list(items)
    for spec in reversed(sort):
        result.sort(
            key=lambda item: _sort_key(getattr(item, spec.field, None)),
            reverse=spec.direction is SortDirection.DESC,
        )
    return result


class BaseMemoryRepository[ModelT](BaseScopedRepository[ModelT]):
    """异步内存基线仓储：字典存储 + 自增 ID；子类只实现 `_build` / `_apply`。"""

    def __init__(self) -> None:
        """初始化空存储。"""
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

    async def list(self, *, sort: Sequence[SortSpec] | None = None) -> list[ModelT]:
        """返回全部记录（按 ID 升序，经作用域过滤；传 `sort` 时按规格排序）。

        Args:
            sort: 生效排序规格（经白名单校验）；空则保持 ID 升序。

        Returns:
            list[ModelT]: 记录列表。
        """
        items = [self._items[key] for key in sorted(self._items) if self._matches_scope(self._items[key])]
        return _sort_items(items, sort)

    async def get(self, item_id: int) -> ModelT | None:
        """按 ID 查询记录。

        Args:
            item_id: 记录 ID。

        Returns:
            ModelT | None: 存在时返回记录（经作用域过滤），否则 None。
        """
        item = self._items.get(item_id)
        if item is None or not self._matches_scope(item):
            return None
        return item

    async def count(self) -> int:
        """记录总数（经作用域过滤）。

        Returns:
            int: 记录条数。
        """
        return sum(1 for item in self._items.values() if self._matches_scope(item))

    async def create(self, **values: object) -> ModelT:
        """创建记录并分配自增 ID。

        Args:
            **values: 创建字段值。

        Returns:
            ModelT: 新建记录。
        """
        item_id = self._next_id
        self._next_id += 1
        item = self._build(item_id, values)
        self._items[item_id] = item
        return item

    async def update(self, item_id: int, **values: object) -> ModelT | None:
        """更新记录。

        Args:
            item_id: 记录 ID。
            **values: 更新字段值。

        Returns:
            ModelT | None: 更新后的记录；不存在返回 None。
        """
        item = self._items.get(item_id)
        if item is None or not self._matches_scope(item):
            return None
        updated = self._apply(item, values)
        self._items[item_id] = updated
        return updated

    async def delete(self, item_id: int) -> bool:
        """删除记录。

        Args:
            item_id: 记录 ID。

        Returns:
            bool: 删除成功 True；不存在（或不在作用域）False。
        """
        item = self._items.get(item_id)
        if item is None or not self._matches_scope(item):
            return False
        del self._items[item_id]
        return True
