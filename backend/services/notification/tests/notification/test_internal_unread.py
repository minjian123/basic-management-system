"""通知内部未读端点：显式用户取数 / 路由形状 / 入站拒绝登录态（Kiwi 2528）。"""

# pyright: reportPrivateUsage=false, reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false
from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine

from bms_core.db.unit_of_work import DbUnitOfWork
from bms_core.testing.transaction import write_session
from bms_notification.domains.notification.api.notification import internal_router, internal_unread_count
from notification._support import add_notification

pytestmark = pytest.mark.kiwi_id(2528)


async def test_internal_unread_count_for_explicit_user(shared_tenant_engine: AsyncEngine, uid: int) -> None:
    """按显式用户计数（不依赖登录态上下文），不受其他用户未读影响。

    测试库是**真自动提交**（每条语句立即落库、会话退出不回滚），故收件人取自 `uid` 夹具：
    该夹具由 `conftest._clean_notification_rows` 在用例前后按同一组主键清场，断言只看本用例
    造的行，与执行顺序、并行邻居无关。
    """
    async with write_session(shared_tenant_engine) as session:
        add_notification(session, user_id=uid, title="A")
        add_notification(session, user_id=uid, title="B")
        add_notification(session, user_id=uid + 1, title="C")
        await session.flush()
        response = await internal_unread_count(DbUnitOfWork(session), uid)  # pyright: ignore[reportArgumentType]
        assert response.data is not None
        assert response.data.count == 2


def test_internal_router_shape() -> None:
    """内部路由：前缀与路径固定（服务间契约路径不随资源路由变化）。"""
    assert internal_router.prefix == "/notifications/internal"
    paths = {getattr(route, "path", None) for route in internal_router.routes}
    assert "/notifications/internal/unread-count" in paths


async def test_internal_endpoint_rejects_user_token(client: AsyncClient) -> None:
    """登录态用户令牌不能访问内部面（仅服务身份 / 能力授权）。"""
    response = await client.get("/api/v1/notifications/internal/unread-count", params={"user_id": 1})
    assert response.status_code in (401, 403)
    assert response.json()["code"] in (20001, 30001)
