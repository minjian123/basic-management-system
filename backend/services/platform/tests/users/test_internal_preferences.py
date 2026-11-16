"""平台内部按用户读取偏好端点（Kiwi 2517）。"""

from __future__ import annotations

from typing import cast

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.context import reset_tenant_context, set_tenant_context
from bms_core.core.exceptions import ParamError
from bms_core.db.session import DbSession
from bms_core.db.tenant import TenantContext
from bms_core.db.unit_of_work import DbUnitOfWork
from bms_core.preference.repository import PreferenceRepository
from bms_core.testing.transaction import rollback_session
from bms_platform.domains.user.api import internal_preferences
from bms_platform.domains.user.repositories.user import UserRepository
from bms_platform.domains.user.schemas.preferences import InternalPreferenceResolveRequest

pytestmark = pytest.mark.kiwi_id(2517)

_TENANT = TenantContext(code="demo", db_key="tenant_demo", name="演示", tenant_id=1001)


class _User:
    def __init__(self, timezone: str | None) -> None:
        self.timezone = timezone


async def test_resolve_values_and_timezone(
    shared_tenant_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """按用户返回偏好值与时区。"""
    async with rollback_session(shared_tenant_engine) as session:
        repository = PreferenceRepository(session)
        await repository.upsert(1001, "notify.channels", '{"inbox":false}')
        await repository.upsert(1001, "notify.dnd", '{"enabled":true,"start":"22:00","end":"08:00"}')
        await session.flush()

        async def _get(self: UserRepository, user_id: int) -> _User:
            del self, user_id
            return _User("Asia/Shanghai")

        monkeypatch.setattr(UserRepository, "get", _get)
        token = set_tenant_context(_TENANT)
        try:
            result = await internal_preferences.resolve_preferences(
                InternalPreferenceResolveRequest(
                    user_id="1001",
                    keys=ConcurrentStableList(("notify.channels", "notify.dnd", "missing")),
                ),
                DbUnitOfWork(cast("DbSession", session)),
            )
        finally:
            reset_tenant_context(token)
        data = result.data
        assert data is not None
        assert data.values["notify.channels"] == {"inbox": False}
        assert data.timezone == "Asia/Shanghai"


async def test_resolve_missing_user_and_bad_id(
    shared_tenant_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """用户不存在返回空值与空时区；非法主键拒绝。"""
    async with rollback_session(shared_tenant_engine) as session:
        async def _none(self: UserRepository, user_id: int) -> None:
            del self, user_id
            return None

        monkeypatch.setattr(UserRepository, "get", _none)
        token = set_tenant_context(_TENANT)
        try:
            result = await internal_preferences.resolve_preferences(
                InternalPreferenceResolveRequest(user_id="2002", keys=ConcurrentStableList()),
                DbUnitOfWork(cast("DbSession", session)),
            )
            assert result.data is not None
            assert result.data.values == {}
            assert result.data.timezone is None
            with pytest.raises(ParamError):
                await internal_preferences.resolve_preferences(
                    InternalPreferenceResolveRequest(user_id="bad", keys=ConcurrentStableList()),
                    DbUnitOfWork(cast("DbSession", session)),
                )
        finally:
            reset_tenant_context(token)
