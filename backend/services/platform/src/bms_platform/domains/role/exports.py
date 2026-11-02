"""角色域导出定义（04_02）：`roles` 列表导出列集 / 同源取数。

- 列集：角色编码 / 角色名称 / 角色类型 / 状态 / 创建时间；**无敏感列**（验证「无 `data:plain` 也不脱敏」路径）；
- 取数复用 `RoleRepository.list_export_chunk` 与 `count_filtered`（同一 `_filter_conditions` / `_apply_sort`）；
- 时间按 UTC 格式化（时区归 05_02）。
"""

from __future__ import annotations

from bms_core.core.concurrent import (
    ConcurrentStableDict,
    ConcurrentStableFrozenList,
    ConcurrentStableList,
)
from bms_core.db.session import DbSession
from bms_core.models.platform.role import SysRole
from bms_core.transfer.base import ColumnSpec
from bms_core.transfer.export_definition import BaseExportDefinition, ExportQuery, format_export_time
from bms_platform.domains.role.repositories.role import RoleRepository

__all__ = ["ROLES_EXPORT_COLUMNS", "RolesExportDefinition"]

ROLES_EXPORT_COLUMNS: ConcurrentStableFrozenList[ColumnSpec] = ConcurrentStableFrozenList(
    (
        ColumnSpec(key="code", title="角色编码"),
        ColumnSpec(key="name", title="角色名称"),
        ColumnSpec(key="role_type", title="角色类型"),
        ColumnSpec(key="status", title="状态"),
        ColumnSpec(key="created_at", title="创建时间"),
    )
)
"""角色导出列集（固定列序）。"""

_STATUS_LABELS: ConcurrentStableDict[str, str] = ConcurrentStableDict({"enabled": "启用", "disabled": "停用"})
"""角色状态中文标签。"""

_ROLE_TYPE_LABELS: ConcurrentStableDict[str, str] = ConcurrentStableDict(
    {
        "custom": "自定义",
        "system": "内置系统",
        "security": "内置安全",
        "audit": "内置审计",
    }
)
"""角色类型中文标签（内置类型按 `role_type` 判定）。"""


class RolesExportDefinition(BaseExportDefinition):
    """角色列表导出定义（`roles`）。"""

    biz = "roles"
    title = "角色"

    @property
    def columns(self) -> ConcurrentStableFrozenList[ColumnSpec]:
        """导出列集。

        Returns:
            ConcurrentStableFrozenList[ColumnSpec]: 列定义。
        """
        return ROLES_EXPORT_COLUMNS

    async def count(self, session: DbSession, query: ExportQuery) -> int:
        """按筛选条件统计角色数（与列表同源）。

        Args:
            session: 当前会话。
            query: 导出查询。

        Returns:
            int: 条数。
        """
        return await RoleRepository(session).count_filtered(
            keyword=query.keyword,
            status=query.status,
            ids=_ids_of(query),
        )

    async def fetch(
        self,
        session: DbSession,
        query: ExportQuery,
        *,
        offset: int,
        limit: int,
    ) -> ConcurrentStableList[ConcurrentStableDict[str, object]]:
        """按筛选条件分批取数（与 `count` 同源）。

        Args:
            session: 当前会话。
            query: 导出查询。
            offset: 起始偏移。
            limit: 本批上限。

        Returns:
            ConcurrentStableList[ConcurrentStableDict[str, object]]: 行集。
        """
        rows = await RoleRepository(session).list_export_chunk(
            keyword=query.keyword,
            status=query.status,
            ids=_ids_of(query),
            order_by=query.order_by,
            order=query.order,
            offset=offset,
            limit=limit,
        )
        return ConcurrentStableList(_to_row(item) for item in rows)


def _to_row(role: SysRole) -> ConcurrentStableDict[str, object]:
    """把角色记录映射为导出行。

    Args:
        role: 角色记录。

    Returns:
        ConcurrentStableDict[str, object]: 列键 → 已格式化值。
    """
    return ConcurrentStableDict(
        {
            "code": role.code,
            "name": role.name,
            "role_type": _ROLE_TYPE_LABELS.get(role.role_type, role.role_type),
            "status": _STATUS_LABELS.get(role.status, role.status),
            "created_at": format_export_time(role.created_at),
        }
    )


def _ids_of(query: ExportQuery) -> ConcurrentStableList[int] | None:
    """把查询里的选中集合转为仓储参数（空表示不限定）。

    Args:
        query: 导出查询。

    Returns:
        ConcurrentStableList[int] | None: 主键集合或 None。
    """
    return ConcurrentStableList(query.ids) if query.ids else None
