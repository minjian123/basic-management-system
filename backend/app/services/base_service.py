"""services 层基类：通用 CRUD 委派与统一不存在语义。"""

from app.core.base import BaseObject
from app.core.exceptions import NotFoundError
from app.repositories.base_repository import BaseRepository


class BaseService[ModelT](BaseObject):
    """业务服务基类：包装仓储通用 CRUD，不存在统一抛 NotFoundError。"""

    def __init__(self, repository: BaseRepository[ModelT]) -> None:
        self._repository = repository

    def list(self) -> list[ModelT]:
        """返回全部记录。

        Returns:
            list[ModelT]: 记录列表。
        """
        return self._repository.list()

    def exists(self, item_id: int) -> bool:
        """记录是否存在。

        Args:
            item_id: 记录 ID。

        Returns:
            bool: 存在 True。
        """
        return self._repository.exists(item_id)

    def count(self) -> int:
        """记录总数。

        Returns:
            int: 记录条数。
        """
        return self._repository.count()

    def get(self, item_id: int) -> ModelT:
        """按 ID 查询记录，不存在抛 NotFoundError。

        Args:
            item_id: 记录 ID。

        Returns:
            ModelT: 记录。

        Raises:
            NotFoundError: 记录不存在。
        """
        item = self._repository.get(item_id)
        if item is None:
            raise NotFoundError(f"记录不存在：{item_id}")
        return item

    def create(self, **values: object) -> ModelT:
        """创建记录。

        Args:
            **values: 创建字段值。

        Returns:
            ModelT: 新建记录。
        """
        return self._repository.create(**values)

    def update(self, item_id: int, **values: object) -> ModelT:
        """更新记录，不存在抛 NotFoundError。

        Args:
            item_id: 记录 ID。
            **values: 更新字段值。

        Returns:
            ModelT: 更新后的记录。

        Raises:
            NotFoundError: 记录不存在。
        """
        item = self._repository.update(item_id, **values)
        if item is None:
            raise NotFoundError(f"记录不存在：{item_id}")
        return item

    def delete(self, item_id: int) -> None:
        """删除记录，不存在抛 NotFoundError。

        Args:
            item_id: 记录 ID。

        Raises:
            NotFoundError: 记录不存在。
        """
        if not self._repository.delete(item_id):
            raise NotFoundError(f"记录不存在：{item_id}")
