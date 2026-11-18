"""角标：聚合出口 / 待办占位 / 未读转发与降级（Kiwi 2528）。"""

import json

import pytest
import pytest_asyncio
from httpx import AsyncClient

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.exceptions import ServiceUnavailableError
from bms_core.servicecall.base import ServiceRequest, ServiceResponse
from bms_platform.domains.dashboard.repositories.adapters import (
    NOTIFICATION_UNREAD_PATH,
    NotificationBadgeAdapter,
    NullDatasetProbe,
    NullTodoCountProvider,
)

from .helpers import DEFAULT_USER_ID, clear_dashboard_pref, prepare, tenant_url

pytestmark = pytest.mark.kiwi_id(2528)

_BADGES = "/api/v1/dashboard/badges"


class _Client:
    """服务间调用客户端替身。"""

    def __init__(self, *, status: int = 200, payload: object = None, raises: bool = False) -> None:
        """初始化。

        Args:
            status: 响应状态码。
            payload: 响应体。
            raises: 是否抛不可用异常。
        """
        self.status = status
        self.payload = payload
        self.raises = raises
        self.requests: ConcurrentStableList[ServiceRequest] = ConcurrentStableList()

    async def call(self, request: ServiceRequest) -> ServiceResponse:
        """记录请求并返回预设响应。

        Args:
            request: 调用请求。

        Returns:
            ServiceResponse: 预设响应。

        Raises:
            ServiceUnavailableError: `raises=True` 时抛出。
        """
        self.requests.append(request)
        if self.raises:
            raise ServiceUnavailableError("down")
        body = b"" if self.payload is None else json.dumps(self.payload).encode("utf-8")
        return ServiceResponse(status_code=self.status, content=body)


@pytest_asyncio.fixture(autouse=True)
async def prepared(tenant_db: str) -> None:
    """准备集 + 偏好清理。

    Args:
        tenant_db: 共享测试租户库连接串。
    """
    assert tenant_db
    await prepare()
    await clear_dashboard_pref(tenant_url(), DEFAULT_USER_ID)


async def test_badges_endpoint_returns_both_sources(client: AsyncClient) -> None:
    """接口恒 200：待办占位不可用；未读在无通知服务时降级为不可用。"""
    body = (await client.get(_BADGES)).json()
    assert body["code"] == 0
    data = body["data"]
    assert data["todo"] == {"count": 0, "available": False, "reason": "workflow_unavailable"}
    assert data["notification"]["available"] is False
    assert data["notification"]["reason"] == "notification_unavailable"


async def test_notification_adapter_passes_user_and_parses_count() -> None:
    """未读适配器：请求路径与显式用户正确，`count` 透传。"""
    client = _Client(payload={"code": 0, "data": {"count": 7}})
    view = await NotificationBadgeAdapter(client=client).unread_count(42)  # type: ignore[arg-type]
    assert view.count == 7
    assert view.available is True
    request = client.requests[0]
    assert request.path == NOTIFICATION_UNREAD_PATH
    assert request.service == "notification"
    assert request.query is not None and request.query.get("user_id") == "42"


@pytest.mark.parametrize(
    ("status", "payload", "raises"),
    (
        (503, {"code": 0, "data": {"count": 1}}, False),
        (200, {"code": 0, "data": {}}, False),
        (200, {"code": 0, "data": "bad"}, False),
        (200, None, False),
        (200, {"code": 0, "data": {"count": "3"}}, False),
        (200, {"code": 0, "data": {"count": True}}, False),
        (0, None, True),
    ),
)
async def test_notification_adapter_degrades(status: int, payload: object, raises: bool) -> None:
    """非 2xx / 载荷非法 / 不可达 → `available=False`（不抛业务错）。"""
    client = _Client(status=status, payload=payload, raises=raises)
    view = await NotificationBadgeAdapter(client=client).unread_count(1)  # type: ignore[arg-type]
    assert view.available is False
    assert view.count == 0
    assert view.reason == "notification_unavailable"


async def test_null_providers() -> None:
    """占位实现：待办固定不可用、数据集固定「未接入」。"""
    todo = await NullTodoCountProvider().todo_count(1)
    assert todo.available is False and todo.reason == "workflow_unavailable"
    assert await NullDatasetProbe().is_available("ds-1") is None


def test_badge_contract_shape() -> None:
    """角标契约字段（`count` / `available` / `reason`）序列化稳定。"""
    from bms_platform.domains.dashboard.schemas.badge import DashboardBadgeCount

    dumped = DashboardBadgeCount(count=2, available=True).model_dump()
    assert dumped == {"count": 2, "available": True, "reason": None}
