"""通知中心接口：筛选参数 / 权限码依赖 / 错误码 / 真实中心（Kiwi 2517）。"""

# pyright: reportPrivateUsage=false, reportUnknownLambdaType=false, reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false, reportUnknownParameterType=false, reportDeprecated=false, reportUntypedFunctionDecorator=false, reportCallIssue=false
from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine

from bms_core.api.deps import get_notification_center
from bms_core.testing.transaction import write_session
from bms_notification.domains.notification.center import DatabaseNotificationCenter
from notification._support import add_notification, session_opener
from tests_support.auth import auth_headers

pytestmark = pytest.mark.kiwi_id(2517)

API = "/api/v1/notifications"


async def test_list_and_detail_with_db_center(
    service_app: FastAPI, client: AsyncClient, shared_tenant_engine: AsyncEngine, uid: int
) -> None:
    """列表筛选 / 查看即已读 / 未读数。

    收件人取自 `uid` 夹具（用例前后由 `conftest._clean_notification_rows` 清场）：测试库是
    **真自动提交**，会话退出不回滚，硬编码用户主键会把上一轮的未读行留给下一轮（实测 1→4）。
    """
    client.headers.update(auth_headers(subject=str(uid), session_id=str(uid)))
    async with write_session(shared_tenant_engine) as session:
        first = add_notification(session, user_id=uid, title="审批待办", notification_type="approval")
        add_notification(session, user_id=uid, title="系统提示", is_read=True)
        await session.flush()
        service_app.dependency_overrides[get_notification_center] = lambda: DatabaseNotificationCenter(
            session_opener=lambda: session_opener(session), transactional=False
        )
        listed = await client.get(API, params={"type": "approval"})
        assert listed.json()["data"]["total"] == 1
        read_only = await client.get(API, params={"is_read": "true"})
        assert read_only.json()["data"]["total"] == 1
        assert (await client.get(f"{API}/unread-count")).json()["data"] == {"count": 1}
        detail = await client.get(f"{API}/{first.id}")
        assert detail.json()["data"]["is_read"] is True
        assert (await client.get(f"{API}/unread-count")).json()["data"] == {"count": 0}


async def test_api_errors(
    service_app: FastAPI, client: AsyncClient, shared_tenant_engine: AsyncEngine, uid: int
) -> None:
    """非法筛选 / 不存在 / 批量参数 / 越权删除错误码。"""
    async with write_session(shared_tenant_engine) as session:
        other = add_notification(session, user_id=uid + 1, title="他人")
        await session.flush()
        service_app.dependency_overrides[get_notification_center] = lambda: DatabaseNotificationCenter(
            session_opener=lambda: session_opener(session), transactional=False
        )
        assert (await client.get(API, params={"type": "bad"})).json()["code"] == 10001
        assert (await client.get(f"{API}/99999")).json()["code"] == 70101
        assert (await client.post(f"{API}/read", json={"ids": []})).json()["code"] == 70103
        assert (await client.delete(f"{API}/{other.id}")).json()["code"] == 70106


async def test_filters_json_invalid(service_app: FastAPI, client: AsyncClient) -> None:
    """filters 非 JSON / 非数组参数错误。"""
    service_app.dependency_overrides[get_notification_center] = lambda: DatabaseNotificationCenter(
        session_opener=lambda: _empty_session(),  # pyright: ignore[reportArgumentType]
        transactional=False,  # pyright: ignore[reportArgumentType]
    )
    assert (await client.get(API, params={"filters": "bad"})).json()["code"] == 10001
    assert (await client.get(API, params={"filters": "{}"})).json()["code"] == 10001


def _empty_session() -> object:
    """占位会话开合口（本用例只验证参数解析，不触达中心）。"""
    raise AssertionError("不应触达通知中心")
