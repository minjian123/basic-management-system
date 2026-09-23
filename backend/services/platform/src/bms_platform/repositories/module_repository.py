"""模块仓储（平台服务自有，06_02 迁入）：服务目录只读查询（按分组 / 状态 / 服务维度，分页与单条）。

- 归属：读 `sys_module`（`platform` 服务 × 平台服务库 `bms_platform`）；仓储随模型一并迁入平台服务；
- 会话经构造注入（`get_db` / `get_write_db` / `get_uow` 同一请求同会话）；只读、不提交；
- 仅提供读方法，**不提供写接口**（注册运行时只读边界）；写路径仅开发期种子脚本。
"""

from sqlalchemy import ColumnElement, func, select

from bms_core.repositories.base_db_repository import BaseDbRepository
from bms_core.schemas.pagination import BasePageQuery
from bms_platform.models.catalog import SysModule


class ModuleRepository(BaseDbRepository[SysModule]):
    """服务目录仓储（`sys_module` 只读查询）。

    排序白名单限有索引列（当前仅主键 `id`；`sys_module` 其余列为复合唯一约束、无单列索引），
    白名单外排序请求项忽略、回落 `id` 升序。
    """

    model = SysModule
    sortable_fields = frozenset({"id"})

    def _catalog_conditions(
        self,
        *,
        group: str | None = None,
        status: str | None = None,
        service_only: bool = False,
    ) -> list[ColumnElement[bool]]:
        """构造服务目录筛选条件（`list_catalog` / `page_catalog` 同源，防口径漂移）。

        Args:
            group: 归属分组筛选（`foundation` / `capability` / `product`）；None 不过滤。
            status: 状态筛选（`enabled` / `disabled` / `planned`）；None 不过滤。
            service_only: 仅返回服务行（`service_key` 非空）。

        Returns:
            list[ColumnElement[bool]]: 条件表达式列表。
        """
        conditions: list[ColumnElement[bool]] = []
        if group is not None:
            conditions.append(self._column("service_group") == group)
        if status is not None:
            conditions.append(self._column("status") == status)
        if service_only:
            conditions.append(self._column("service_key").is_not(None))
        return conditions

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
        conditions = self._catalog_conditions(group=group, status=status, service_only=service_only)
        statement = self._select().where(*conditions).order_by(self._column("id").asc())
        result = await self._session.execute(statement)
        return list(result.scalars().all())

    async def page_catalog(
        self,
        query: BasePageQuery,
        *,
        group: str | None = None,
        status: str | None = None,
    ) -> tuple[list[SysModule], int]:
        """分页查询服务目录（筛选 + 排序 + 当前页 + 筛选后总数）。

        Args:
            query: 页码分页请求（含排序参数；排序经仓储白名单校验、非法忽略）。
            group: 归属分组筛选（`foundation` / `capability` / `product`）；None 不过滤。
            status: 状态筛选（`enabled` / `disabled` / `planned`）；None 不过滤。

        Returns:
            tuple[list[SysModule], int]: (当前页记录, 筛选后总数)。
        """
        conditions = self._catalog_conditions(group=group, status=status)
        statement = self._apply_sort(self._select().where(*conditions), self._resolve_sort(query))
        statement = statement.limit(query.size).offset((query.page - 1) * query.size)
        rows = list((await self._session.execute(statement)).scalars().all())
        count_statement = select(func.count()).select_from(self.model).where(*self._scope_where(), *conditions)
        total = int((await self._session.execute(count_statement)).scalar_one())
        return rows, total

    async def get_by_key(self, module_key: str) -> SysModule | None:
        """按 `module_key` 查询单条记录（作用域过滤；不存在返回 None）。

        Args:
            module_key: 行登记标识。

        Returns:
            SysModule | None: 记录；不存在返回 None。
        """
        statement = self._select().where(self._column("module_key") == module_key)
        return (await self._session.execute(statement)).scalar_one_or_none()

    async def get_by_service_key(self, service_key: str) -> SysModule | None:
        """按 `service_key` 查询单条记录（服务维度；不存在返回 None）。

        Args:
            service_key: 服务维度标识（微服务工程名）。

        Returns:
            SysModule | None: 记录；不存在返回 None。
        """
        statement = self._select().where(self._column("service_key") == service_key)
        return (await self._session.execute(statement)).scalar_one_or_none()
