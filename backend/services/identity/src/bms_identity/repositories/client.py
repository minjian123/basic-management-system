"""认证与身份服务 repositories 层：第三方应用客户端仓储（`sys_client`）。"""

from __future__ import annotations

from sqlalchemy import ColumnElement, func, select

from bms_core.repositories.base_db_repository import BaseDbRepository
from bms_core.schemas.pagination import BasePageQuery
from bms_identity.models.client import SysClient


class SysClientRepository(BaseDbRepository[SysClient]):
    """客户端仓储（`sys_client`）：按标识取行 + 筛选分页。"""

    model = SysClient
    sortable_fields = frozenset({"id", "name", "client_id", "created_at"})

    async def get_by_client_id(self, client_id: str) -> SysClient | None:
        """按客户端标识取行（OIDC 授权 / 换码定位客户端）。

        Args:
            client_id: 客户端标识。

        Returns:
            SysClient | None: 客户端行；不存在返回 None。
        """
        statement = self._select().where(self._column("client_id") == client_id)
        return (await self._session.execute(statement)).scalar_one_or_none()

    async def list_filtered(
        self,
        query: BasePageQuery,
        *,
        status: str | None = None,
        name: str | None = None,
    ) -> list[SysClient]:
        """客户端分页查询（状态 / 名称筛选 + 统一排序）。

        Args:
            query: 页码分页请求（含排序参数）。
            status: 状态过滤（可选）。
            name: 名称模糊过滤（可选）。

        Returns:
            list[SysClient]: 当前页客户端。
        """
        statement = self._apply_sort(
            self._select().where(*self._filter_conditions(status=status, name=name)),
            self._resolve_sort(query),
        )
        statement = statement.limit(query.size).offset((query.page - 1) * query.size)
        return list((await self._session.execute(statement)).scalars().all())

    async def count_filtered(self, *, status: str | None = None, name: str | None = None) -> int:
        """客户端总数（与 `list_filtered` 同筛选口径）。

        Args:
            status: 状态过滤（可选）。
            name: 名称模糊过滤（可选）。

        Returns:
            int: 命中的客户端条数。
        """
        statement = (
            select(func.count())
            .select_from(SysClient)
            .where(*self._scope_where(), *self._filter_conditions(status=status, name=name))
        )
        return int((await self._session.execute(statement)).scalar_one())

    def _filter_conditions(self, *, status: str | None, name: str | None) -> list[ColumnElement[bool]]:
        """构造筛选条件（状态精确 + 名称模糊）。

        Args:
            status: 状态过滤（可选）。
            name: 名称模糊过滤（可选）。

        Returns:
            list[ColumnElement[bool]]: 筛选条件列表。
        """
        conditions: list[ColumnElement[bool]] = []
        if status:
            conditions.append(self._column("status") == status)
        if name:
            conditions.append(self._column("name").like(f"%{name}%"))
        return conditions
