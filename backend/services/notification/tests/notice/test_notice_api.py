"""公告接口（Kiwi 2518）：CRUD / 可见性 / 权限 / 错误码 / 统计 / 内部过期端点。"""

# pyright: reportPrivateUsage=false, reportUnknownLambdaType=false, reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false, reportUnknownParameterType=false, reportDeprecated=false, reportUntypedFunctionDecorator=false, reportCallIssue=false
from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import timedelta
from typing import cast

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from bms_core.audit.tables import is_audited_table
from bms_core.core.exceptions import NoticeAudienceUnavailableError
from bms_core.db.session import get_uow
from bms_core.events.platform_events import register_platform_event_contracts
from bms_core.permission.base import BasePermissionChecker, get_permission_checker
from bms_core.testing.transaction import write_session
from bms_notification.domains.notification.api.notice import (
    _resolve_locale,
    expire_notices,
    get_notice_audience_reader,
)
from bms_notification.domains.notification.notice_constants import NOTICE_STATUS_DRAFT, NOTICE_STATUS_OFFLINE
from bms_notification.domains.notification.schemas.notice import NoticeExpireRequest
from bms_notification.domains.notification.services.notice_audience import NoticeAudienceReader
from notice._support import FakeAudience, FakeOptionSets, add_notice, reset_user, use_user, utc_now

pytestmark = pytest.mark.kiwi_id(2518)

API = "/api/v1/notices"


@asynccontextmanager
async def _null_tx() -> AsyncGenerator[None]:
    """空事务上下文（回滚会话已在事务内）。"""
    yield


class _Uow:
    """工作单元替身：复用回滚会话，事务由用例夹具管理。"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @property
    def session(self) -> AsyncSession:
        return self._session

    def begin(self) -> object:
        return _null_tx()

    async def commit(self) -> None:
        return None

    async def rollback(self) -> None:
        return None


class _Checker:
    """权限检查器替身：可指定是否持有 notice:update。"""

    def __init__(self, *, can_update: bool) -> None:
        self.can_update = can_update

    async def aprepare(self, *, request: object) -> None:
        return None

    def check(self, code: str) -> bool:
        return code != "notice:update" or self.can_update


def _overrides(app: FastAPI, session: AsyncSession, *, can_update: bool = True) -> None:
    """覆盖工作单元 / 权限 / 应读人数。

    Args:
        app: 应用。
        session: 回滚会话。
        can_update: 是否持有 notice:update。
    """
    uow = _Uow(session)
    app.dependency_overrides[get_uow] = lambda: uow
    app.dependency_overrides[get_permission_checker] = lambda: cast(
        "BasePermissionChecker", _Checker(can_update=can_update)
    )
    app.dependency_overrides[get_notice_audience_reader] = lambda: cast("NoticeAudienceReader", FakeAudience(5))


def _payload(
    *, publish: bool = True, is_top: bool = False
) -> dict[str, object]:  # bare-collections:allow — httpx json 参数只接受内置 dict
    """构造新建请求体。

    Args:
        publish: 是否发布。
        is_top: 是否置顶。

    Returns:
        dict[str, object]: 请求体。
    """
    return {
        "i18n": {
            "zh-CN": {"title": "中文标题", "content": "<p>正文</p>"},
            "en-US": {"title": "English", "content": "<p>body</p>"},
        },
        "type": "system",
        "priority": "normal",
        "is_top": is_top,
        "publish": publish,
    }


async def test_crud_and_stats(service_app: FastAPI, client: AsyncClient, shared_tenant_engine: AsyncEngine) -> None:
    """新建 / 列表 / 详情 / 回执 / 统计 / 编辑 / 删除。"""
    async with write_session(shared_tenant_engine) as session:
        _overrides(service_app, session)
        created = await client.post(API, json=_payload(is_top=True))
        assert created.status_code == 200
        body = created.json()["data"]
        assert body["title"] == "中文标题" and body["is_top"] is True
        assert body["i18n"]["en-US"]["title"] == "English"
        notice_id = body["id"]

        listed = await client.get(API)
        assert listed.json()["data"]["total"] == 1
        published = await client.get(f"{API}/published")
        assert published.json()["data"]["total"] == 1

        detail = await client.get(f"{API}/{notice_id}", params={"locale": "en-US"})
        assert detail.json()["data"]["title"] == "English"

        read = await client.post(f"{API}/{notice_id}/read")
        assert read.status_code == 200
        second = await client.post(f"{API}/{notice_id}/read")
        assert second.json()["data"]["read_at"] == read.json()["data"]["read_at"]

        stats = await client.get(f"{API}/{notice_id}/read-stats")
        assert stats.json()["data"] == {"notice_id": notice_id, "audience_count": 5, "read_count": 1, "unread_count": 4}

        updated = await client.put(
            f"{API}/{notice_id}",
            json={"is_top": False, "i18n": {"zh-CN": {"title": "新标题", "content": "<p>新正文</p>"}}},
        )
        assert updated.json()["data"]["title"] == "新标题" and updated.json()["data"]["is_top"] is False

        deleted = await client.delete(f"{API}/{notice_id}")
        assert deleted.json()["data"] == {"deleted": True}
        assert (await client.get(f"{API}/{notice_id}")).json()["code"] == 70201


async def test_visibility_for_non_manager(
    service_app: FastAPI, client: AsyncClient, shared_tenant_engine: AsyncEngine
) -> None:
    """普通用户（无 notice:update）：草稿不可见、列表只剩发布中。"""
    async with write_session(shared_tenant_engine) as session:
        published = add_notice(session, title="发布中")
        draft = add_notice(session, title="草稿", status=NOTICE_STATUS_DRAFT)
        await session.flush()
        _overrides(service_app, session, can_update=False)
        listed = await client.get(API)
        data = listed.json()["data"]
        assert data["total"] == 1 and data["list"][0]["title"] == "发布中"
        assert (await client.get(f"{API}/{draft.id}")).json()["code"] == 70201
        detail = await client.get(f"{API}/{published.id}")
        assert detail.json()["data"]["title"] == "发布中"
        assert detail.json()["data"]["i18n"] is None


async def test_errors(service_app: FastAPI, client: AsyncClient, shared_tenant_engine: AsyncEngine) -> None:
    """非法类型 / 不存在 / 时间冲突 / 已下线状态冲突 / 统计不可用。"""
    now = utc_now()
    async with write_session(shared_tenant_engine) as session:
        offline = add_notice(session, title="下线", status=NOTICE_STATUS_OFFLINE)
        await session.flush()
        _overrides(service_app, session)
        bad_type = await client.post(API, json={**_payload(), "type": "unknown"})
        assert bad_type.json()["code"] == 10001
        bad_status = await client.get(API, params={"status": "bad"})
        assert bad_status.json()["code"] == 10001
        assert (await client.get(f"{API}/999999")).json()["code"] == 70201
        bad_time = await client.post(
            API,
            json={
                "i18n": {"zh-CN": {"title": "x", "content": "<p>x</p>"}},
                "publish_at": now.isoformat(),
                "expire_at": now.isoformat(),
            },
        )
        assert bad_time.json()["code"] == 70203
        conflict = await client.put(f"{API}/{offline.id}", json={"is_top": True})
        assert conflict.json()["code"] == 70204
        assert (await client.post(f"{API}/{offline.id}/read")).json()["code"] == 70202

        service_app.dependency_overrides[get_notice_audience_reader] = lambda: cast(
            "NoticeAudienceReader", FakeAudience(error=NoticeAudienceUnavailableError("down"))
        )
        stats = await client.get(f"{API}/{offline.id}/read-stats")
        assert stats.json()["code"] == 70206


async def test_routes_registered(service_app: FastAPI) -> None:
    """内部过期端点已挂载到 `/api/v1/notices/internal/expire`。"""
    paths = set(service_app.openapi()["paths"])
    assert "/api/v1/notices/internal/expire" in paths
    assert "/api/v1/notices/published" in paths


async def test_notice_audited_after_app_boot(service_app: FastAPI) -> None:
    """通知服务装载期把 sys_notice 注册进字段级审计白名单。"""
    _ = service_app
    assert is_audited_table("sys_notice") is True
    assert is_audited_table("sys_notice_read") is False


def test_resolve_locale_priority() -> None:
    """显式 locale → Accept-Language → 默认常量。"""
    assert _resolve_locale("en-US", "zh-CN,zh;q=0.9") == "en-US"
    assert _resolve_locale(None, "en-US,en;q=0.9") == "en-US"
    assert _resolve_locale("  ", "") == "zh-CN"


def test_audience_reader_dependency() -> None:
    """读取器依赖用传入的服务客户端构造（测试可覆盖）。"""
    client = object()
    reader = get_notice_audience_reader(client)  # pyright: ignore[reportArgumentType]
    assert isinstance(reader, NoticeAudienceReader)


async def test_internal_expire_handler(shared_tenant_engine: AsyncEngine) -> None:
    """内部过期端点处理函数：置下线并返回条数。"""
    async with write_session(shared_tenant_engine) as session:
        tokens = use_user(1)
        try:
            add_notice(session, title="到期", expire_at=utc_now() - timedelta(minutes=1))
            await session.flush()
            register_platform_event_contracts()
            uow = _Uow(session)
            result = await expire_notices(  # pyright: ignore[reportArgumentType]
                uow,  # pyright: ignore[reportArgumentType]
                cast("object", FakeOptionSets()),  # pyright: ignore[reportArgumentType]
                NoticeExpireRequest(limit=10),
            )
            assert getattr(result.data, "expired", None) == 1
        finally:
            reset_user(tokens)
