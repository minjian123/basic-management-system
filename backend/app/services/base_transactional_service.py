"""services 层事务基类：在通用服务之上叠加事务边界（写操作包事务）。"""

from app.db.unit_of_work import NullUnitOfWork, UnitOfWork
from app.repositories.base_repository import BaseRepository
from app.services.base_service import BaseService


class BaseTransactionalService[ModelT](BaseService[ModelT]):
    """事务服务基类：写操作经工作单元进入事务，读操作不包事务。

    事务公共方法收敛到 `UnitOfWork`（单点干涉）；需要事务的模块服务继承本类，
    无事务需求的通用服务可留在 `BaseService`。
    """

    def __init__(self, repository: BaseRepository[ModelT], uow: UnitOfWork | None = None) -> None:
        super().__init__(repository)
        self._uow = uow if uow is not None else NullUnitOfWork()

    def create(self, **values: object) -> ModelT:
        """创建记录（事务内）。

        Args:
            **values: 创建字段值。

        Returns:
            ModelT: 新建记录。
        """
        with self._uow.begin():
            return super().create(**values)

    def update(self, item_id: int, **values: object) -> ModelT:
        """更新记录（事务内），不存在抛 NotFoundError。

        Args:
            item_id: 记录 ID。
            **values: 更新字段值。

        Returns:
            ModelT: 更新后的记录。

        Raises:
            NotFoundError: 记录不存在。
        """
        with self._uow.begin():
            return super().update(item_id, **values)

    def delete(self, item_id: int) -> None:
        """删除记录（事务内），不存在抛 NotFoundError。

        Args:
            item_id: 记录 ID。

        Raises:
            NotFoundError: 记录不存在。
        """
        with self._uow.begin():
            super().delete(item_id)
