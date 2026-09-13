"""services 层基类：通用 CRUD 委派、统一不存在语义与分页。"""

from app.core.base import BaseObject
from app.core.exceptions import NotFoundError
from app.repositories.base_repository import BaseRepository
from app.schemas.pagination import BaseCursorQuery, BaseCursorResponse, BasePageQuery, BasePageResponse


class BaseService[ModelT](BaseObject):
    """业务服务基类：包装仓储通用 CRUD，不存在统一抛 NotFoundError。

    只承载业务无关的通用能力；事务边界由 `BaseTransactionalService` 叠加。
    """

    def __init__(self, repository: BaseRepository[ModelT]) -> None:
        """初始化。

        Args:
            repository: 仓储契约实现。
        """
        self._repository = repository

    async def list(self) -> list[ModelT]:
        """返回全部记录。

        Returns:
            list[ModelT]: 记录列表。
        """
        return await self._repository.list()

    async def exists(self, item_id: int) -> bool:
        """记录是否存在。

        Args:
            item_id: 记录 ID。

        Returns:
            bool: 存在 True。
        """
        return await self._repository.exists(item_id)

    async def count(self) -> int:
        """记录总数。

        Returns:
            int: 记录条数。
        """
        return await self._repository.count()

    async def get(self, item_id: int) -> ModelT:
        """按 ID 查询记录，不存在抛 NotFoundError。

        Args:
            item_id: 记录 ID。

        Returns:
            ModelT: 记录。

        Raises:
            NotFoundError: 记录不存在。
        """
        item = await self._repository.get(item_id)
        if item is None:
            raise NotFoundError(f"记录不存在：{item_id}")
        return item

    async def create(self, **values: object) -> ModelT:
        """创建记录。

        Args:
            **values: 创建字段值。

        Returns:
            ModelT: 新建记录。
        """
        return await self._repository.create(**values)

    async def update(self, item_id: int, **values: object) -> ModelT:
        """更新记录，不存在抛 NotFoundError。

        Args:
            item_id: 记录 ID。
            **values: 更新字段值。

        Returns:
            ModelT: 更新后的记录。

        Raises:
            NotFoundError: 记录不存在。
        """
        item = await self._repository.update(item_id, **values)
        if item is None:
            raise NotFoundError(f"记录不存在：{item_id}")
        return item

    async def delete(self, item_id: int) -> None:
        """删除记录，不存在抛 NotFoundError。

        Args:
            item_id: 记录 ID。

        Raises:
            NotFoundError: 记录不存在。
        """
        if not await self._repository.delete(item_id):
            raise NotFoundError(f"记录不存在：{item_id}")

    async def page(self, query: BasePageQuery) -> BasePageResponse[ModelT]:
        """页码分页查询。

        Args:
            query: 页码分页请求。

        Returns:
            BasePageResponse[ModelT]: 分页响应（当前页 + 总数）。
        """
        items = await self._repository.list_page(query)
        total = await self._repository.count()
        return BasePageResponse[ModelT](list=items, total=total, page=query.page, size=query.size)

    async def cursor_page(self, query: BaseCursorQuery) -> BaseCursorResponse[ModelT]:
        """游标分页查询。

        Args:
            query: 游标分页请求。

        Returns:
            BaseCursorResponse[ModelT]: 游标分页响应（当前批 + 下批游标）。
        """
        items = await self._repository.list_cursor(query)
        has_more = len(items) == query.limit
        offset = int(query.cursor) if query.cursor else 0
        next_cursor = str(offset + query.limit) if has_more else None
        return BaseCursorResponse[ModelT](list=items, next_cursor=next_cursor, has_more=has_more)
