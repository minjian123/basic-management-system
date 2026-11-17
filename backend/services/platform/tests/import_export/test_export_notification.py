"""导出完成站内信：成功入队 / 无 actor 不发 / 入队失败不影响导出（Kiwi 2517）。"""

# pyright: reportPrivateUsage=false, reportUnknownLambdaType=false, reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false, reportUnknownParameterType=false, reportDeprecated=false, reportUntypedFunctionDecorator=false, reportCallIssue=false
from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pytest

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.jobs.base import JobContext
from bms_core.notification.request import NotificationRequest
from bms_platform.domains.import_export.export_jobs import _notify_export_completed
from bms_platform.domains.import_export.services.exports import ExportPayload
from bms_platform.domains.user.repositories.user import UserRepository

pytestmark = pytest.mark.kiwi_id(2517)


class _User:
    def __init__(self, locale: str | None) -> None:
        self.locale = locale


class _Session:
    """作业会话替身（提供事务上下文）。"""

    @asynccontextmanager
    async def begin(self) -> AsyncIterator[object]:
        yield object()


def _ctx() -> JobContext:
    @asynccontextmanager
    async def _open() -> AsyncIterator[_Session]:
        yield _Session()

    return JobContext(
        job_id=9,
        job_type="platform.export.execute",
        service_key="platform",
        db_key="tenant_demo",
        tenant_id=1001,
        open_session=_open,
    )


async def test_export_notification_enqueued(monkeypatch: pytest.MonkeyPatch) -> None:
    """英文用户收到英文标题；请求类型与业务标识正确。"""
    sent: ConcurrentStableList[NotificationRequest] = ConcurrentStableList()

    async def _fake_enqueue(session: object, request: NotificationRequest, *, tenant_id: str | None = None) -> str:
        del session, tenant_id
        sent.add(request)
        return "evt"

    async def _get(self: UserRepository, user_id: int) -> _User:
        del self, user_id
        return _User("en-US")

    monkeypatch.setattr(UserRepository, "get", _get)
    monkeypatch.setattr("bms_platform.domains.import_export.export_jobs.enqueue_notification_request", _fake_enqueue)
    await _notify_export_completed(_ctx(), ExportPayload(biz="users", kind="excel", actor=1001), 12)
    assert len(sent) == 1
    assert sent[0].type == "import"
    assert sent[0].biz_type == "export"
    assert sent[0].biz_id == "9"
    assert sent[0].title.startswith("Export completed")


async def test_export_notification_skips_without_actor(monkeypatch: pytest.MonkeyPatch) -> None:
    """无提交人时不发。"""
    sent: ConcurrentStableList[NotificationRequest] = ConcurrentStableList()

    async def _fake_enqueue(session: object, request: NotificationRequest, *, tenant_id: str | None = None) -> str:
        del session, tenant_id
        sent.add(request)
        return "evt"

    monkeypatch.setattr("bms_platform.domains.import_export.export_jobs.enqueue_notification_request", _fake_enqueue)
    await _notify_export_completed(_ctx(), ExportPayload(biz="users", kind="excel"), 12)
    assert sent == []


async def test_export_notification_failure_is_swallowed(monkeypatch: pytest.MonkeyPatch) -> None:
    """入队失败不影响导出（不抛出）。"""

    async def _fail(session: object, request: NotificationRequest, *, tenant_id: str | None = None) -> str:
        del session, request, tenant_id
        raise RuntimeError("outbox down")

    async def _get(self: UserRepository, user_id: int) -> _User:
        del self, user_id
        return _User(None)

    monkeypatch.setattr(UserRepository, "get", _get)
    monkeypatch.setattr("bms_platform.domains.import_export.export_jobs.enqueue_notification_request", _fail)
    await _notify_export_completed(_ctx(), ExportPayload(biz="users", kind="excel", actor=1001), 12)


def test_export_payload_roundtrip() -> None:
    """导出负载携带提交人（供通知收件人）。"""
    payload = ExportPayload(biz="users", kind="excel", actor=1001)
    assert payload.to_job_payload()["actor"] == 1001
    assert payload.to_job_payload()["biz"] == "users"
