"""邮件 / 短信接口测试共用替身。"""

# pyright: reportPrivateUsage=false, reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false
from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import cast

from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.db.session import get_uow
from bms_core.notification.preference import NotificationPreference, get_notification_preference_store
from bms_core.optionset.base import BaseOptionSetRegistry, get_option_set_registry
from bms_core.permission.base import BasePermissionChecker, get_permission_checker
from bms_notification.domains.notification.api.support import get_job_submitter, get_recipient_resolver
from bms_notification.domains.notification.services.recipient import RecipientInfo


@asynccontextmanager
async def _null_tx() -> AsyncGenerator[None]:
    yield


class Uow:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @property
    def session(self) -> AsyncSession:
        return self._session

    def begin(self) -> object:
        return _null_tx()


class Checker:
    def __init__(self, *, allow: bool = True) -> None:
        self.allow = allow

    async def aprepare(self, *, request: object) -> None:
        del request

    def check(self, code: str) -> bool:
        return self.allow


class Jobs:
    def __init__(self, *, fail: bool = False) -> None:
        self.calls: ConcurrentStableList[tuple[str, ConcurrentStableDict[str, object]]] = ConcurrentStableList()
        self.fail = fail

    async def submit(
        self,
        session: object,
        *,
        job_type: str,
        payload: ConcurrentStableDict[str, object],
        tenant_id: int | None,
    ) -> int:
        del session, tenant_id
        if self.fail:
            raise RuntimeError("job down")
        self.calls.add((job_type, payload))
        return len(self.calls)


class Resolver:
    async def resolve(self, user_id: int) -> RecipientInfo:
        del user_id
        return RecipientInfo(email="a@b.c", phone="13800000000", locale="zh-CN")


class Preference:
    async def load(self, user_id: int) -> NotificationPreference:
        del user_id
        return NotificationPreference()


class Registry:
    def get(self, key: str) -> object | None:
        del key
        return None

    def validate(self, value: str, *, option_set_key: str) -> ConcurrentStableList[str]:
        del value, option_set_key
        return ConcurrentStableList()


def install(app: FastAPI, session: AsyncSession, *, jobs: Jobs | None = None, allow: bool = True) -> Jobs:
    """覆盖工作单元 / 权限 / 作业 / 收件人 / 偏好 / 选项集。"""
    resolved_jobs = jobs or Jobs()
    app.dependency_overrides[get_uow] = lambda: Uow(session)
    app.dependency_overrides[get_permission_checker] = lambda: cast("BasePermissionChecker", Checker(allow=allow))
    app.dependency_overrides[get_job_submitter] = lambda: resolved_jobs
    app.dependency_overrides[get_recipient_resolver] = lambda: Resolver()
    app.dependency_overrides[get_notification_preference_store] = lambda: Preference()
    app.dependency_overrides[get_option_set_registry] = lambda: cast("BaseOptionSetRegistry", Registry())
    return resolved_jobs
