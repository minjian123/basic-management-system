"""通知中心读契约测试（Kiwi 812）：契约继承 / 数据契约与事件负载 / 占位实现 / 依赖解析 / 占位路由。"""

from collections.abc import Sequence

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_notification_center
from app.core.capability import BaseCapability, BaseNullObject
from app.core.plugin import BasePluggable, resolve_plugin
from app.main import ApplicationFactory, lifespan
from app.notification.base import (
    NOTIFICATION_NEW_EVENT,
    BaseNotificationCenter,
    Notification,
    NotificationPayload,
)
from app.notification.null import NullNotificationCenter
from app.schemas.filters import BaseFilterQuery
from app.schemas.pagination import BasePageQuery, BasePageResponse

API = "/api/v1/notifications"


class _InMemoryNotificationCenter(BaseNotificationCenter):
    """测试用内存通知中心（验证查看即已读与角标口径；真实落库随通知公告阶段）。"""

    def __init__(self) -> None:
        self._items: dict[int, Notification] = {}
        self._seq = 0

    def add(self, title: str) -> Notification:
        """写入一条未读通知。

        Args:
            title: 标题。

        Returns:
            Notification: 落库后的通知（内存）。
        """
        self._seq += 1
        item = Notification(id=self._seq, user_id=1, title=title)
        self._items[self._seq] = item
        return item

    async def list(self, filter: BaseFilterQuery, page: BasePageQuery) -> BasePageResponse[Notification]:
        items = sorted(self._items.values(), key=lambda item: item.id or 0, reverse=True)
        start = (page.page - 1) * page.size
        return BasePageResponse[Notification](
            list=items[start : start + page.size], total=len(items), page=page.page, size=page.size
        )

    async def detail(self, notification_id: int, *, mark_read: bool = True) -> Notification | None:
        item = self._items.get(notification_id)
        if item is None:
            return None
        if mark_read and not item.is_read:
            item = item.model_copy(update={"is_read": True})
            self._items[notification_id] = item
        return item

    async def unread_count(self) -> int:
        return sum(1 for item in self._items.values() if not item.is_read)

    async def mark_read(self, ids: Sequence[int]) -> int:
        for notification_id in ids:
            item = self._items.get(notification_id)
            if item is not None and not item.is_read:
                self._items[notification_id] = item.model_copy(update={"is_read": True})
        return await self.unread_count()

    async def mark_all_read(self) -> int:
        for notification_id, item in list(self._items.items()):
            if not item.is_read:
                self._items[notification_id] = item.model_copy(update={"is_read": True})
        return 0

    async def delete(self, notification_id: int) -> bool:
        return self._items.pop(notification_id, None) is not None


@pytest.mark.kiwi_id(812)
def test_contract_inheritance_and_identity() -> None:
    """契约继承与能力域标识：BasePluggable / BaseCapability / key。"""
    assert issubclass(BaseNotificationCenter, BasePluggable)
    assert issubclass(BaseNotificationCenter, BaseCapability)
    assert BaseNotificationCenter.key == "notification_center"
    assert BaseNotificationCenter.plugin_key == "notification_center"

    assert issubclass(NullNotificationCenter, BaseNullObject)


@pytest.mark.kiwi_id(812)
def test_data_contracts_and_event_payload() -> None:
    """数据契约：Notification 默认值 / NotificationPayload 字段集 / 事件常量。"""
    assert NOTIFICATION_NEW_EVENT == "notification.new"

    assert set(NotificationPayload.model_fields) == {"title", "type", "biz_type", "biz_id", "created_at"}

    notification = Notification(title="审批待办")
    assert notification.id is None
    assert notification.user_id is None
    assert notification.content == ""
    assert notification.type == "system"
    assert notification.biz_type is None
    assert notification.biz_id is None
    assert notification.is_read is False
    assert notification.created_at is None


@pytest.mark.kiwi_id(812)
async def test_null_center_fixed_returns() -> None:
    """占位实现：列表空分页 / 详情 None / 未读 0 / 已读 0 / 删除 False。"""
    center = NullNotificationCenter()
    assert center.placeholder is True
    assert "占位实现" in center.describe()

    page = BasePageQuery(page=2, size=5)
    result = await center.list(BaseFilterQuery(keyword="x"), page)
    assert result.list == []
    assert result.total == 0
    assert result.page == 2
    assert result.size == 5

    assert await center.detail(1) is None
    assert await center.unread_count() == 0
    assert await center.mark_read([1, 2]) == 0
    assert await center.mark_all_read() == 0
    assert await center.delete(1) is False


@pytest.mark.kiwi_id(812)
async def test_dependency_provider_resolves() -> None:
    """依赖解析：应用装配占位通知中心；提供者解析到同一实例。"""
    app = ApplicationFactory().create(None)
    async with lifespan(app):
        center = app.state.notification_center
        assert isinstance(center, NullNotificationCenter)
        assert resolve_plugin("notification_center", None) is center


@pytest.mark.kiwi_id(812)
async def test_placeholder_routes(client: AsyncClient) -> None:
    """占位路由：列表空分页 / 未读 0 / 详情 null / 已读 0 / 删除 false。"""
    listed = await client.get(API)
    assert listed.status_code == 200
    assert listed.json()["data"] == {"list": [], "total": 0, "page": 1, "size": 20}

    filtered = await client.get(
        API, params={"keyword": "x", "filters": '[{"field": "is_read", "operator": "eq", "value": 0}]'}
    )
    assert filtered.status_code == 200
    assert filtered.json()["data"]["total"] == 0

    bad_json = await client.get(API, params={"filters": "not-json"})
    assert bad_json.status_code == 200
    assert bad_json.json()["code"] == 10001

    not_array = await client.get(API, params={"filters": '{"field": "is_read"}'})
    assert not_array.status_code == 200
    assert not_array.json()["code"] == 10001

    unread = await client.get(f"{API}/unread-count")
    assert unread.status_code == 200
    assert unread.json()["data"] == {"count": 0}

    detail = await client.get(f"{API}/1")
    assert detail.status_code == 200
    assert detail.json()["data"] is None

    read = await client.post(f"{API}/read", json={"ids": [1, 2]})
    assert read.status_code == 200
    assert read.json()["data"] == {"count": 0}

    read_all = await client.post(f"{API}/read-all")
    assert read_all.status_code == 200
    assert read_all.json()["data"] == {"count": 0}

    deleted = await client.delete(f"{API}/1")
    assert deleted.status_code == 200
    assert deleted.json()["data"] is False


@pytest.mark.kiwi_id(812)
async def test_routes_with_in_memory_center() -> None:
    """占位路由 + 内存实现：查看即已读与角标校准口径。"""
    app = ApplicationFactory().create(None)
    async with lifespan(app):
        center = _InMemoryNotificationCenter()
        first = center.add("审批待办")
        center.add("系统公告")
        app.dependency_overrides[get_notification_center] = lambda: center
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            assert (await client.get(f"{API}/unread-count")).json()["data"] == {"count": 2}

            listed = await client.get(API, params={"page": 1, "size": 10})
            assert listed.json()["data"]["total"] == 2

            detail = await client.get(f"{API}/{first.id}")
            assert detail.json()["data"]["is_read"] is True
            assert (await client.get(f"{API}/unread-count")).json()["data"] == {"count": 1}

            read = await client.post(f"{API}/read", json={"ids": [first.id]})
            assert read.json()["data"] == {"count": 1}

            read_all = await client.post(f"{API}/read-all")
            assert read_all.json()["data"] == {"count": 0}

            assert (await client.delete(f"{API}/{first.id}")).json()["data"] is True
            assert (await client.get(f"{API}/{first.id}")).json()["data"] is None
