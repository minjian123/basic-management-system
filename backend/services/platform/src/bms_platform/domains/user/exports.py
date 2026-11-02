"""用户域导出定义（04_02）：`users` 列表导出列集 / 脱敏字段 / 同源取数。

- 列集与用户列表接口一致（登录账号 / 姓名 / 状态），另加联系方式（手机号 / 邮箱，默认脱敏）与最近登录；
- 取数复用 `UserRepository.list_export_chunk` 与 `count_filtered`（同一 `_filter_conditions` / `_apply_sort`），
  保证「导出条数 = 列表总数」；
- 脱敏字段由本定义声明，编排层统一走 `mask_rows` + `data:plain` 判定；时间按 UTC 格式化（时区归 05_02）。
"""

from __future__ import annotations

from bms_core.core.concurrent import (
    ConcurrentStableDict,
    ConcurrentStableFrozenList,
    ConcurrentStableList,
)
from bms_core.db.session import DbSession
from bms_core.models.platform.user import SysUser
from bms_core.transfer.base import ColumnSpec
from bms_core.transfer.export_definition import BaseExportDefinition, ExportQuery, format_export_time
from bms_platform.domains.user.repositories.user import UserRepository

__all__ = ["USERS_EXPORT_COLUMNS", "UsersExportDefinition"]

USERS_EXPORT_COLUMNS: ConcurrentStableFrozenList[ColumnSpec] = ConcurrentStableFrozenList(
    (
        ColumnSpec(key="username", title="登录账号"),
        ColumnSpec(key="name", title="姓名"),
        ColumnSpec(key="phone", title="手机号"),
        ColumnSpec(key="email", title="邮箱"),
        ColumnSpec(key="status", title="状态"),
        ColumnSpec(key="last_login_at", title="最近登录"),
    )
)
"""用户导出列集（固定列序）。"""

_STATUS_LABELS: ConcurrentStableDict[str, str] = ConcurrentStableDict({"enabled": "启用", "disabled": "停用"})
"""账号状态中文标签。"""


class UsersExportDefinition(BaseExportDefinition):
    """用户列表导出定义（`users`）。"""

    biz = "users"
    title = "用户"
    masked_fields: ConcurrentStableDict[str, str] = ConcurrentStableDict({"phone": "phone", "email": "email"})

    @property
    def columns(self) -> ConcurrentStableFrozenList[ColumnSpec]:
        """导出列集。

        Returns:
            ConcurrentStableFrozenList[ColumnSpec]: 列定义。
        """
        return USERS_EXPORT_COLUMNS

    async def count(self, session: DbSession, query: ExportQuery) -> int:
        """按筛选条件统计用户数（与列表同源）。

        Args:
            session: 当前会话。
            query: 导出查询。

        Returns:
            int: 条数。
        """
        return await UserRepository(session).count_filtered(
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
        rows = await UserRepository(session).list_export_chunk(
            keyword=query.keyword,
            status=query.status,
            ids=_ids_of(query),
            order_by=query.order_by,
            order=query.order,
            offset=offset,
            limit=limit,
        )
        return ConcurrentStableList(_to_row(item) for item in rows)


def _to_row(user: SysUser) -> ConcurrentStableDict[str, object]:
    """把用户记录映射为导出行。

    Args:
        user: 用户记录。

    Returns:
        ConcurrentStableDict[str, object]: 列键 → 已格式化值。
    """
    return ConcurrentStableDict(
        {
            "username": user.username,
            "name": user.name,
            "phone": user.phone or "",
            "email": user.email or "",
            "status": _STATUS_LABELS.get(user.status, user.status),
            "last_login_at": format_export_time(user.last_login_at),
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
