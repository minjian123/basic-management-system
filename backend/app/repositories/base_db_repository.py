"""repositories 层数据库实现骨架：异步占位，不连库（真实 CRUD 随落库阶段回补）。"""

from collections.abc import Sequence

from app.core.capability import BaseStub
from app.repositories.base_scoped_repository import BaseScopedRepository
from app.schemas.sorting import SortSpec


class BaseDbRepository[ModelT](BaseScopedRepository[ModelT], BaseStub):
    """数据库实现骨架（异步占位，不连库）。

    冻结数据库侧继承点：真实实现（异步引擎 / 会话 / 四库方言 / 读写分离 /
    软删除过滤）随落库阶段在基类覆写 CRUD；`exists` 沿用派生链。
    """

    async def list(self, *, sort: Sequence[SortSpec] | None = None) -> list[ModelT]:
        """查询全部（占位；排序经 `_apply_sort` 拼 ORDER BY 随落库阶段回补）。

        Args:
            sort: 生效排序规格（占位不生效）。

        Raises:
            NotImplementedError: 始终抛出（占位）。
        """
        del sort
        raise self._not_implemented("list")

    async def get(self, item_id: int) -> ModelT | None:
        """按 ID 查询（占位）。

        Raises:
            NotImplementedError: 始终抛出（占位）。
        """
        raise self._not_implemented("get")

    async def count(self) -> int:
        """记录总数（占位）。

        Raises:
            NotImplementedError: 始终抛出（占位）。
        """
        raise self._not_implemented("count")

    async def create(self, **values: object) -> ModelT:
        """创建记录（占位）。

        Raises:
            NotImplementedError: 始终抛出（占位）。
        """
        raise self._not_implemented("create")

    async def update(self, item_id: int, **values: object) -> ModelT | None:
        """更新记录（占位）。

        Raises:
            NotImplementedError: 始终抛出（占位）。
        """
        raise self._not_implemented("update")

    async def delete(self, item_id: int) -> bool:
        """删除记录（占位）。

        Raises:
            NotImplementedError: 始终抛出（占位）。
        """
        raise self._not_implemented("delete")
