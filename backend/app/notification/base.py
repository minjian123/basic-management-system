"""通知中心能力域：读接口契约与事件负载契约（真实取数 / 落库 / 推送随通知公告阶段回补）。

- `NOTIFICATION_NEW_EVENT`：新站内信推送事件名（与 `app.ws.base.REALTIME_EVENTS` 之一同源）。
- `Notification` / `NotificationPayload`：通知对象与 `notification.new` 事件负载数据契约。
- `BaseNotificationCenter`：能力域中间层契约（`key = "notification_center"`）——异步 `list` / `detail`
  （查看即已读）/ `unread_count` / `mark_read` / `mark_all_read` / `delete`。
- `get_notification_center`：依赖注入提供者（应用级单例；公共依赖经 `app/api/deps.py` 统一导出）。

口径：**未读数以服务端为唯一口径**——`mark_read` / `mark_all_read` 返回操作后的未读总数，前端直接以
返回值校准角标，不依赖实时推送增量推算；实时推送（`notification.new` / `approval.todo`）与已读的并发由
**实现侧**按用户加锁 / 串行化裁决，契约层不引入锁或幂等键参数。`detail(..., mark_read=True)` 命中即已读。
真实取数 / 落库、推送触发、渠道偏好过滤与按 locale 渲染均归通知公告阶段上层。
"""

from abc import ABC, abstractmethod
from collections.abc import Sequence
from datetime import datetime
from typing import cast

from fastapi import Request
from pydantic import Field

from app.core.config import Settings
from app.core.plugin import DEFAULT_CONTRACT_VERSION, NULL_PLUGIN_NAME, BasePluggable, resolve_plugin
from app.schemas.base import BaseSchema
from app.schemas.filters import BaseFilterQuery
from app.schemas.pagination import BasePageQuery, BasePageResponse

__all__ = [
    "NOTIFICATION_NEW_EVENT",
    "BaseNotificationCenter",
    "Notification",
    "NotificationPayload",
    "get_notification_center",
]

NOTIFICATION_NEW_EVENT = "notification.new"
"""新站内信推送事件名（与 `REALTIME_EVENTS` 之一同源；负载见 `NotificationPayload`）。"""


class Notification(BaseSchema):
    """通知对象（个人维度；字段对齐 `sys_notification`）。"""

    id: int | None = Field(default=None, description="通知 ID（落库生成）")
    user_id: int | None = Field(default=None, description="收件用户 ID（个人维度）")
    title: str = Field(description="标题")
    content: str = Field(default="", description="正文（已按收件人 locale 渲染）")
    type: str = Field(default="system", description="通知类型（取值随通知公告阶段定）")
    biz_type: str | None = Field(default=None, description="业务类型（如 approval）")
    biz_id: str | None = Field(default=None, description="业务标识（供跳转与去重）")
    is_read: bool = Field(default=False, description="是否已读")
    created_at: datetime | None = Field(default=None, description="创建时间（UTC）")


class NotificationPayload(BaseSchema):
    """`notification.new` 推送事件负载（供前端跳转与插入；不含正文与未读数）。"""

    title: str = Field(description="标题")
    type: str = Field(description="通知类型")
    biz_type: str | None = Field(default=None, description="业务类型（如 approval）")
    biz_id: str | None = Field(default=None, description="业务标识（供跳转与去重）")
    created_at: datetime | None = Field(default=None, description="创建时间（UTC）")


class BaseNotificationCenter(BasePluggable, ABC):
    """通知中心读契约：列表 / 详情（查看即已读）/ 未读计数 / 已读 / 全部已读 / 删除。"""

    key: str = "notification_center"
    plugin_key: str = "notification_center"
    plugin_name: str = NULL_PLUGIN_NAME
    contract_version: str = DEFAULT_CONTRACT_VERSION

    @abstractmethod
    async def list(self, filter: BaseFilterQuery, page: BasePageQuery) -> BasePageResponse[Notification]:
        """列当前用户通知（筛选 + 分页）。

        Args:
            filter: 筛选契约（`keyword` + `filters`，复用 02-4-20）。
            page: 分页契约（`page` / `size` / 排序）。

        Returns:
            BasePageResponse[Notification]: 分页通知（占位空集）。
        """

    @abstractmethod
    async def detail(self, notification_id: int, *, mark_read: bool = True) -> Notification | None:
        """取通知详情（查看即已读）。

        Args:
            notification_id: 通知 ID。
            mark_read: 命中是否标记已读（默认 True，对齐「查看即已读」）。

        Returns:
            Notification | None: 通知；未命中为 None。
        """

    @abstractmethod
    async def unread_count(self) -> int:
        """当前未读总数（服务端唯一口径）。

        Returns:
            int: 未读通知数。
        """

    @abstractmethod
    async def mark_read(self, ids: Sequence[int]) -> int:
        """按 id 批量标记已读。

        Args:
            ids: 通知 ID 序列。

        Returns:
            int: 操作后的未读总数（供前端校准角标）。
        """

    @abstractmethod
    async def mark_all_read(self) -> int:
        """全部标记已读。

        Returns:
            int: 操作后的未读总数（恒 0）。
        """

    @abstractmethod
    async def delete(self, notification_id: int) -> bool:
        """删除单条通知。

        Args:
            notification_id: 通知 ID。

        Returns:
            bool: 是否删除到既有通知。
        """


def get_notification_center(request: Request) -> BaseNotificationCenter:
    """取应用级通知中心（依赖注入提供者）。

    Args:
        request: 请求对象。

    Returns:
        BaseNotificationCenter: 应用装配的通知中心实例。
    """
    settings = cast("Settings", request.app.state.settings)
    return cast(
        "BaseNotificationCenter",
        resolve_plugin(
            "notification_center",
            settings.notification_center.provider,
            expected_version=BaseNotificationCenter.contract_version,
        ),
    )
