"""认证与身份服务 repositories 层：租户外部 IdP 配置仓储（`sys_identity_provider`）。"""

from __future__ import annotations

from sqlalchemy import ColumnElement, func, select

from bms_core.core.concurrent import ConcurrentStableList, ConcurrentStableSet
from bms_core.repositories.base_db_repository import BaseDbRepository
from bms_core.schemas.pagination import BasePageQuery
from bms_identity.models.identity_provider import SysIdentityProvider


class IdentityProviderRepository(BaseDbRepository[SysIdentityProvider]):
    """外部 IdP 配置仓储（`sys_identity_provider`）：入口清单 / 按标识取行 / 管理面筛选分页。"""

    model = SysIdentityProvider
    sortable_fields = ConcurrentStableSet({"id", "name", "sort", "status", "type", "created_at"})

    async def list_enabled(self) -> ConcurrentStableList[SysIdentityProvider]:
        """取启用中的 IdP 行（按 `sort` 升序、主键兜底；入口清单主路径）。

        Returns:
            ConcurrentStableList[SysIdentityProvider]: 启用中的 IdP 行。
        """
        statement = (
            self._select()
            .where(self._column("status") == "enabled")
            .order_by(self._column("sort").asc(), self._column("id").asc())
        )
        result = await self._session.execute(statement)
        return ConcurrentStableList(result.scalars().all())

    async def get_by_key(self, idp_key: str) -> SysIdentityProvider | None:
        """按租户内标识取行（authorize / callback 定位配置）。

        Args:
            idp_key: 租户内稳定标识（路由参数）。

        Returns:
            SysIdentityProvider | None: IdP 行；不存在返回 None。
        """
        statement = self._select().where(self._column("idp_key") == idp_key)
        return (await self._session.execute(statement)).scalar_one_or_none()

    async def list_filtered(
        self,
        query: BasePageQuery,
        *,
        status: str | None = None,
        type: str | None = None,
        name: str | None = None,
    ) -> ConcurrentStableList[SysIdentityProvider]:
        """管理面分页查询（状态 / 协议 / 名称筛选 + 统一排序）。

        Args:
            query: 页码分页请求（含排序参数）。
            status: 状态过滤（可选）。
            type: 协议类型过滤（可选）。
            name: 名称模糊过滤（可选）。

        Returns:
            ConcurrentStableList[SysIdentityProvider]: 当前页 IdP 行。
        """
        statement = self._apply_sort(
            self._select().where(*self._filter_conditions(status=status, type=type, name=name)),
            self._resolve_sort(query),
        )
        statement = statement.limit(query.size).offset((query.page - 1) * query.size)
        return ConcurrentStableList((await self._session.execute(statement)).scalars().all())

    async def count_filtered(
        self,
        *,
        status: str | None = None,
        type: str | None = None,
        name: str | None = None,
    ) -> int:
        """管理面总数（与 `list_filtered` 同筛选口径）。

        Args:
            status: 状态过滤（可选）。
            type: 协议类型过滤（可选）。
            name: 名称模糊过滤（可选）。

        Returns:
            int: 命中的 IdP 条数。
        """
        statement = (
            select(func.count())
            .select_from(SysIdentityProvider)
            .where(*self._scope_where(), *self._filter_conditions(status=status, type=type, name=name))
        )
        return int((await self._session.execute(statement)).scalar_one())

    def _filter_conditions(
        self,
        *,
        status: str | None,
        type: str | None,
        name: str | None,
    ) -> ConcurrentStableList[ColumnElement[bool]]:
        """构造筛选条件（状态 / 协议精确 + 名称模糊）。

        Args:
            status: 状态过滤（可选）。
            type: 协议类型过滤（可选）。
            name: 名称模糊过滤（可选）。

        Returns:
            ConcurrentStableList[ColumnElement[bool]]: 筛选条件列表。
        """
        conditions: ConcurrentStableList[ColumnElement[bool]] = ConcurrentStableList()
        if status:
            conditions.add(self._column("status") == status)
        if type:
            conditions.add(self._column("type") == type)
        if name:
            conditions.add(self._column("name").like(f"%{name}%"))
        return conditions
