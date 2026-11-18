"""首页工作台域端口（Protocol）：域实现只依赖这些接口，具体实现由装配面注入。

**为什么需要端口**（域边界纪律）：本域要读**角色集与角色有效性**（`role` 域）、**通知未读数**
（通知服务）、**待办数**（工作流未落地）与**数据集可用性**（报表中心未落地），但域实现之间零 import、
跨服务不直连库——读取能力一律经装配面注入的 Protocol，依赖方向恒为「装配 → 域」。
"""

from typing import Protocol

from bms_core.core.concurrent import ConcurrentStableList
from bms_platform.domains.dashboard.dto import BadgeCountView

__all__ = [
    "DatasetProbePort",
    "NotificationBadgePort",
    "RolePort",
    "RoleSummaryView",
    "TodoCountPort",
]


class RoleSummaryView(Protocol):
    """角色摘要只读视图（`role` 域 `RoleSummary` 的结构化契约，避免跨域 import）。"""

    @property
    def id(self) -> int:
        """角色主键。"""
        ...

    @property
    def role_type(self) -> str:
        """角色类型（`platform_admin` / `system` / `security` / `audit` / `custom`）。"""
        ...

    @property
    def status(self) -> str:
        """角色状态（`enabled` / `disabled`）。"""
        ...


class RolePort(Protocol):
    """角色读面（当前用户的直接角色 + 按主键批量取角色摘要）。"""

    async def roles_of_user(self, user_id: int) -> ConcurrentStableList[tuple[str, int]]:
        """取用户直接分配的角色（`(role_type, role_id)` 插入序）。

        Args:
            user_id: 用户主键。

        Returns:
            ConcurrentStableList[tuple[str, int]]: 角色类型与主键（无分配返回空）。
        """
        ...

    async def roles_by_ids(self, role_ids: ConcurrentStableList[int]) -> ConcurrentStableList[RoleSummaryView]:
        """按主键批量取角色摘要（用于角色模板绑定校验）。

        Args:
            role_ids: 角色主键清单。

        Returns:
            ConcurrentStableList[RoleSummaryView]: 角色摘要（不存在的角色不返回）。
        """
        ...


class TodoCountPort(Protocol):
    """待办角标读面（工作流服务落地前的占位实现固定不可用）。"""

    async def todo_count(self, user_id: int) -> BadgeCountView:
        """取当前用户待办数。

        Args:
            user_id: 用户主键。

        Returns:
            BadgeCountView: 计数与可用性。
        """
        ...


class NotificationBadgePort(Protocol):
    """未读角标读面（通知服务为唯一口径，本域只转发）。"""

    async def unread_count(self, user_id: int) -> BadgeCountView:
        """取当前用户未读通知数。

        Args:
            user_id: 用户主键。

        Returns:
            BadgeCountView: 计数与可用性（不可达时 `available=False`）。
        """
        ...


class DatasetProbePort(Protocol):
    """数据集可用性探测（报表中心数据集落地前返回「未接入」）。"""

    async def is_available(self, dataset_id: str) -> bool | None:
        """探测数据集是否可用。

        Args:
            dataset_id: 数据集标识。

        Returns:
            bool | None: True 可用 / False 不存在或停用 / None 未接入（按未校验通过）。
        """
        ...
