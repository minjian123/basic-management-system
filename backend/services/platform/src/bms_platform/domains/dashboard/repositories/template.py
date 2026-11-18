"""工作台模板仓储（`sys_dashboard_template`）：平台默认模板与角色模板。"""

from __future__ import annotations

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.models.platform.dashboard import SCOPE_PLATFORM, SysDashboardTemplate
from bms_core.repositories.base_db_repository import BaseDbRepository

__all__ = ["DashboardTemplateRepository"]


class DashboardTemplateRepository(BaseDbRepository[SysDashboardTemplate]):
    """模板仓储（软删除由基座 `_select()` 统一过滤）。"""

    model = SysDashboardTemplate

    async def list_templates(self, *, scope: str | None = None) -> ConcurrentStableList[SysDashboardTemplate]:
        """取模板（平台层级在前，其后按角色主键升序）。

        Args:
            scope: 层级筛选（None 不筛选）。

        Returns:
            ConcurrentStableList[SysDashboardTemplate]: 模板清单。
        """
        statement = self._select()
        if scope is not None:
            statement = statement.where(SysDashboardTemplate.scope == scope)
        statement = statement.order_by(SysDashboardTemplate.scope.desc(), SysDashboardTemplate.role_id)
        return ConcurrentStableList((await self._session.execute(statement)).scalars().all())

    async def get_platform(self) -> SysDashboardTemplate | None:
        """取平台默认模板（仅一份；含停用）。

        Returns:
            SysDashboardTemplate | None: 模板行；未配置为 None。
        """
        statement = self._select().where(SysDashboardTemplate.scope == SCOPE_PLATFORM)
        return (await self._session.execute(statement)).scalars().first()

    async def list_role_templates(self, *, enabled_only: bool = True) -> ConcurrentStableList[SysDashboardTemplate]:
        """取角色模板（默认仅启用）。

        Args:
            enabled_only: 仅取启用模板。

        Returns:
            ConcurrentStableList[SysDashboardTemplate]: 角色模板清单（按角色主键升序）。
        """
        statement = self._select().where(SysDashboardTemplate.scope != SCOPE_PLATFORM)
        if enabled_only:
            statement = statement.where(SysDashboardTemplate.status == "enabled")
        statement = statement.order_by(SysDashboardTemplate.role_id)
        return ConcurrentStableList((await self._session.execute(statement)).scalars().all())

    async def find_by_role(self, role_id: int) -> SysDashboardTemplate | None:
        """按角色取模板（含停用，用于唯一性判定）。

        Args:
            role_id: 角色主键。

        Returns:
            SysDashboardTemplate | None: 模板行。
        """
        statement = (
            self._select()
            .where(SysDashboardTemplate.scope != SCOPE_PLATFORM)
            .where(SysDashboardTemplate.role_id == role_id)
        )
        return (await self._session.execute(statement)).scalars().first()
