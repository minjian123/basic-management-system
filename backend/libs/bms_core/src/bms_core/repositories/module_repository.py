"""模块仓储：服务目录只读查询（按分组 / 状态 / 服务维度）。

- 会话经构造注入（`get_db` / `get_write_db` / `get_uow` 同一请求同会话）；只读、不提交。
- 仅提供读方法，**不提供写接口**（注册运行时只读边界）；写路径仅开发期种子脚本。
"""

from bms_core.models.platform import SysModule
from bms_core.repositories.base_db_repository import BaseDbRepository


class ModuleRepository(BaseDbRepository[SysModule]):
    """服务目录仓储（`sys_module` 只读查询）。"""

    model = SysModule

    async def list_catalog(
        self,
        *,
        group: str | None = None,
        status: str | None = None,
        service_only: bool = False,
    ) -> list[SysModule]:
        """按分组 / 状态 / 服务维度查询服务目录（默认全部，`id` 升序）。

        Args:
            group: 归属分组筛选（`foundation` / `capability` / `product`）；None 不过滤。
            status: 状态筛选（`enabled` / `disabled` / `planned`）；None 不过滤。
            service_only: 仅返回服务行（`service_key` 非空）。

        Returns:
            list[SysModule]: 记录列表。
        """
        statement = self._select()
        if group is not None:
            statement = statement.where(self._column("service_group") == group)
        if status is not None:
            statement = statement.where(self._column("status") == status)
        if service_only:
            statement = statement.where(self._column("service_key").is_not(None))
        statement = statement.order_by(self._column("id").asc())
        result = await self._session.execute(statement)
        return list(result.scalars().all())

    async def get_by_key(self, module_key: str) -> SysModule | None:
        """按 `module_key` 查询单条记录（作用域过滤；不存在返回 None）。

        Args:
            module_key: 行登记标识。

        Returns:
            SysModule | None: 记录；不存在返回 None。
        """
        statement = self._select().where(self._column("module_key") == module_key)
        return (await self._session.execute(statement)).scalar_one_or_none()
