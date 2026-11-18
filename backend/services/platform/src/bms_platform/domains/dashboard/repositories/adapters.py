"""首页工作台域端口适配器（装配面构造；域实现只依赖 Protocol）。

- `RoleQueryAdapter`：委托 `role` 域角色读面（用户直接角色 + 按主键批量摘要）；
- `NotificationBadgeAdapter`：经 `service_client` 调通知服务内部未读端点，失败降级为不可用
  （范式同 `bms_core/config/http.py`：不抛业务错、不阻断整页）；
- `NullTodoCountProvider` / `NullDatasetProbe`：工作流与报表中心落地前的占位实现。
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol, cast

from bms_core.core.concurrent import ConcurrentStableFrozenDict, ConcurrentStableList
from bms_core.core.context import get_current_tenant
from bms_core.core.exceptions import ServiceUnavailableError
from bms_core.core.logging import get_logger
from bms_core.core.objects import BaseFrameworkObject
from bms_core.edge.headers import TENANT_ID_HEADER
from bms_core.servicecall.base import BaseServiceClient, ServiceRequest
from bms_platform.domains.dashboard.dto import BadgeCountView
from bms_platform.domains.dashboard.ports import RoleSummaryView

__all__ = [
    "NOTIFICATION_SERVICE_KEY",
    "NOTIFICATION_UNREAD_PATH",
    "NotificationBadgeAdapter",
    "NullDatasetProbe",
    "NullTodoCountProvider",
    "RoleQueryAdapter",
]

_LOGGER = get_logger("bms.dashboard")

NOTIFICATION_SERVICE_KEY = "notification"
"""通知服务标识（未读数唯一口径的持有方）。"""

NOTIFICATION_UNREAD_PATH = "/api/v1/notifications/internal/unread-count"
"""通知服务内部未读端点（服务身份 + 显式用户）。"""


class _RoleSummaryReader[SummaryT: RoleSummaryView](Protocol):
    """角色按用户取数（`role` 域 `RoleQueryService.list_by_user` 的结构化契约）。"""

    async def list_by_user(self, user_id: int) -> ConcurrentStableList[SummaryT]:
        """按用户取角色摘要。

        Args:
            user_id: 用户主键。

        Returns:
            ConcurrentStableList[SummaryT]: 角色摘要。
        """
        ...


class _RoleSummaryListReader[SummaryT: RoleSummaryView](Protocol):
    """角色按键批量取数（`role` 域 `RoleQueryService.list_by_ids` 的结构化契约）。"""

    async def list_by_ids(self, role_ids: ConcurrentStableList[int]) -> ConcurrentStableList[SummaryT]:
        """按主键批量取角色摘要。

        Args:
            role_ids: 角色主键清单。

        Returns:
            ConcurrentStableList[SummaryT]: 角色摘要。
        """
        ...


class RoleQueryAdapter[SummaryT: RoleSummaryView](BaseFrameworkObject):
    """`RolePort` 适配：委托角色读面（按用户取角色、按主键取摘要）。"""

    def __init__(self, roles: object) -> None:
        """初始化。

        Args:
            roles: 角色读面实现（`RoleQueryService`；按结构化契约注入，避免域间 import）。
        """
        self._roles = roles

    async def roles_of_user(self, user_id: int) -> ConcurrentStableList[tuple[str, int]]:
        """取用户直接分配的角色（`(role_type, role_id)`）。

        Args:
            user_id: 用户主键。

        Returns:
            ConcurrentStableList[tuple[str, int]]: 角色类型与主键（无分配返回空）。
        """
        reader = cast("_RoleSummaryReader[RoleSummaryView]", self._roles)
        summaries = await reader.list_by_user(user_id)
        result: ConcurrentStableList[tuple[str, int]] = ConcurrentStableList()
        for item in summaries:
            result.add((str(item.role_type), int(item.id)))
        return result

    async def roles_by_ids(self, role_ids: ConcurrentStableList[int]) -> ConcurrentStableList[RoleSummaryView]:
        """按主键批量取角色摘要。

        Args:
            role_ids: 角色主键清单。

        Returns:
            ConcurrentStableList[RoleSummaryView]: 角色摘要（不存在的角色不返回）。
        """
        reader = cast("_RoleSummaryListReader[RoleSummaryView]", self._roles)
        return await reader.list_by_ids(role_ids)


class NotificationBadgeAdapter(BaseFrameworkObject):
    """`NotificationBadgePort` 实现：服务间调用通知服务内部未读端点（失败降级）。"""

    def __init__(self, *, client: BaseServiceClient) -> None:
        """初始化。

        Args:
            client: 服务间调用客户端（`service_client` 能力域）。
        """
        self._client = client

    async def unread_count(self, user_id: int) -> BadgeCountView:
        """取当前用户未读通知数。

        Args:
            user_id: 用户主键。

        Returns:
            BadgeCountView: 计数与可用性；不可达 / 非 2xx / 载荷非法时 `available=False`。
        """
        query: ConcurrentStableFrozenDict[str, str] = ConcurrentStableFrozenDict({"user_id": str(user_id)})
        tenant = get_current_tenant()
        headers: ConcurrentStableFrozenDict[str, str] | None = (
            ConcurrentStableFrozenDict({TENANT_ID_HEADER: tenant}) if tenant else None
        )
        request = ServiceRequest(
            service=NOTIFICATION_SERVICE_KEY,
            method="GET",
            path=NOTIFICATION_UNREAD_PATH,
            query=query,
            headers=headers,
        )
        try:
            response = await self._client.call(request)
        except ServiceUnavailableError:
            _LOGGER.warning("未读角标跨服务取数降级", user_id=user_id)
            return BadgeCountView(available=False, reason="notification_unavailable")
        if not 200 <= response.status_code < 300:
            return BadgeCountView(available=False, reason="notification_unavailable")
        payload = response.payload()
        if not isinstance(payload, Mapping):
            return BadgeCountView(available=False, reason="notification_unavailable")
        data = cast("Mapping[str, object]", payload).get("data")
        if not isinstance(data, Mapping):
            return BadgeCountView(available=False, reason="notification_unavailable")
        count = cast("Mapping[str, object]", data).get("count")
        if not isinstance(count, int) or isinstance(count, bool):
            return BadgeCountView(available=False, reason="notification_unavailable")
        return BadgeCountView(count=max(count, 0), available=True)


class NullTodoCountProvider(BaseFrameworkObject):
    """`TodoCountPort` 占位实现：工作流服务未落地，固定不可用（前端隐藏角标）。"""

    async def todo_count(self, user_id: int) -> BadgeCountView:
        """固定返回不可用（占位）。

        Args:
            user_id: 用户主键（占位忽略）。

        Returns:
            BadgeCountView: `available=False` + `reason=workflow_unavailable`。
        """
        del user_id
        return BadgeCountView(available=False, reason="workflow_unavailable")


class NullDatasetProbe(BaseFrameworkObject):
    """`DatasetProbePort` 占位实现：报表中心数据集未落地，固定返回「未接入」。"""

    async def is_available(self, dataset_id: str) -> bool | None:
        """固定返回 `None`（未接入 → 登记期按未校验通过）。

        Args:
            dataset_id: 数据集标识（占位忽略）。

        Returns:
            bool | None: 恒 `None`。
        """
        del dataset_id
        return None
