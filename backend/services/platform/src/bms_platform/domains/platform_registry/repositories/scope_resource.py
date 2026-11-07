"""作用域资源类型仓储（07D `01_01`）：运营期停用读行 + 视图重建的全量读取。

- 归属：读写平台服务库 `bms_platform` 的 `sys_scope_resource_type`（平台 `platform` 服务）；
- 写入口**唯一**：声明态由注册通道（`DeclarationRepository`）写，运营态由本仓储所在服务写；
- 只提供本域所需的两个读方法（按类型取行 / 取未退役全量），不重复实现注册表的对账写入。
"""

from bms_core.core.concurrent import ConcurrentStableList, ConcurrentStableSet
from bms_core.models.platform.declaration import SysScopeResourceType
from bms_core.repositories.base_db_repository import BaseDbRepository
from bms_core.resource_scope import SCOPE_RESOURCE_RETIRED

__all__ = ["ScopeResourceTypeRepository"]


class ScopeResourceTypeRepository(BaseDbRepository[SysScopeResourceType]):
    """作用域资源类型仓储（`sys_scope_resource_type`）。"""

    model = SysScopeResourceType
    sortable_fields = ConcurrentStableSet({"id"})

    async def get_by_key(self, resource_type_key: str) -> SysScopeResourceType | None:
        """按类型标识取单行（未软删）。

        Args:
            resource_type_key: 类型标识（`{module_key}.{kind}`）。

        Returns:
            SysScopeResourceType | None: 记录行；不存在为 None。
        """
        statement = self._select().where(self._column("resource_type_key") == resource_type_key)
        return (await self._session.execute(statement)).scalars().first()

    async def list_declared(self) -> ConcurrentStableList[SysScopeResourceType]:
        """取未退役的全部类型行（视图重建用；`retired` 不进视图）。

        Returns:
            ConcurrentStableList[SysScopeResourceType]: 类型行（插入序）。
        """
        statement = self._select().where(self._column("status") != SCOPE_RESOURCE_RETIRED).order_by(self._column("id"))
        return ConcurrentStableList((await self._session.execute(statement)).scalars().all())

    async def flush(self) -> None:
        """把挂起写入刷到会话（事务边界由服务层工作单元负责）。"""
        await self._session.flush()
