"""用户偏好 SQL 存储：读写 / 重置 / 校验 / 容错（Kiwi 2517）。"""

# pyright: reportPrivateUsage=false, reportUnknownLambdaType=false, reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false, reportUnknownParameterType=false, reportDeprecated=false, reportUntypedFunctionDecorator=false, reportCallIssue=false
from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import cast
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.context import (
    reset_current_user_id,
    reset_tenant_context,
    set_current_user_id,
    set_tenant_context,
)
from bms_core.core.exceptions import PreferenceKeyInvalidError, PreferenceKeyLimitError, PreferenceValueInvalidError
from bms_core.db.registry import EngineRegistry
from bms_core.db.session import DbSession
from bms_core.db.tenant import TenantContext
from bms_core.models.platform.user import SysUserPreference
from bms_core.preference.base import PREF_MAX_KEYS
from bms_core.preference.repository import PreferenceRepository
from bms_core.preference.sql import SqlPreferenceStore

pytestmark = pytest.mark.kiwi_id(2517)


class _Registry:
    """引擎注册表替身（恒返回共享租户库引擎）。"""

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    def is_sync_only(self, db_key: str) -> bool:
        del db_key
        return False

    async def get(self, db_key: str, *, read_only: bool = False) -> AsyncEngine:
        del db_key, read_only
        return self._engine


@asynccontextmanager
async def _store(engine: AsyncEngine) -> AsyncIterator[tuple[SqlPreferenceStore, int]]:
    """构造 store 并清理本用例用户旧数据。

    Args:
        engine: 共享租户库引擎。

    Yields:
        tuple[SqlPreferenceStore, int]: （偏好存储, 本用例用户主键）。
    """
    user_id = uuid4().int % 10**12
    token = set_tenant_context(TenantContext(code="demo", db_key="tenant_demo", name="演示"))
    user_token = set_current_user_id(user_id)
    try:
        yield SqlPreferenceStore(engines=cast("EngineRegistry", _Registry(engine))), user_id
    finally:
        reset_current_user_id(user_token)
        reset_tenant_context(token)


async def test_set_get_reset(shared_tenant_engine: AsyncEngine) -> None:
    """写入 / 读取 / 重置。"""
    async with _store(shared_tenant_engine) as (store, _user_id):
        await store.set("notify.channels", {"inbox": False})
        await store.set("notify.channels", {"inbox": True, "email": False})
        assert await store.get("notify.channels") == {"inbox": True, "email": False}
        assert await store.get("notify.dnd", default="x") == "x"
        assert await store.reset("notify.channels") is True
        assert await store.reset("notify.channels") is False
        assert await store.get("notify.channels") is None


async def test_no_user_context(shared_tenant_engine: AsyncEngine) -> None:
    """无用户上下文：读回落默认、写抛错。"""
    token = set_tenant_context(TenantContext(code="demo", db_key="tenant_demo", name="演示"))
    try:
        store = SqlPreferenceStore(engines=cast("EngineRegistry", _Registry(shared_tenant_engine)))
        assert await store.get("notify.channels", default=1) == 1
        with pytest.raises(RuntimeError):
            await store.set("notify.channels", {"inbox": True})
        with pytest.raises(RuntimeError):
            await store.reset("notify.channels")
    finally:
        reset_tenant_context(token)


async def test_invalid_key_and_value(shared_tenant_engine: AsyncEngine) -> None:
    """非法键 / 超限值拒绝。"""
    async with _store(shared_tenant_engine) as (store, _user_id):
        with pytest.raises(PreferenceKeyInvalidError):
            await store.set("unknown.key", 1)
        with pytest.raises(PreferenceValueInvalidError):
            await store.set("ui.theme", "x" * 70000)


async def test_key_limit(shared_tenant_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch) -> None:
    """键数超限拒绝。"""
    monkeypatch.setattr("bms_core.preference.sql.PREF_MAX_KEYS", 0)
    assert PREF_MAX_KEYS == 200
    async with _store(shared_tenant_engine) as (store, _user_id):
        with pytest.raises(PreferenceKeyLimitError):
            await store.set("ui.theme", {"mode": "dark"})


async def test_bad_json_falls_back(shared_tenant_engine: AsyncEngine) -> None:
    """库内坏 JSON 读取回落默认。"""
    async with _store(shared_tenant_engine) as (store, user_id):
        async with AsyncSession(shared_tenant_engine) as session:
            session.add(SysUserPreference(user_id=user_id, pref_key="ui.theme", pref_value="{bad"))
            await session.commit()
        assert await store.get("ui.theme", default="fallback") == "fallback"


async def test_repository_get_many_and_count(shared_tenant_engine: AsyncEngine) -> None:
    """仓储批量读取（坏 JSON 跳过）与计数。"""
    async with _store(shared_tenant_engine) as (store, user_id):
        await store.set("ui.theme", {"mode": "dark"})
        await store.set("notify.channels", {"inbox": True})
        async with AsyncSession(shared_tenant_engine) as session:
            session.add(SysUserPreference(user_id=user_id, pref_key="notify.dnd", pref_value="{bad"))
            await session.commit()
        async with AsyncSession(shared_tenant_engine) as session:
            repository = PreferenceRepository(cast("DbSession", session))
            values = await repository.get_many(
                user_id, ConcurrentStableList(("ui.theme", "notify.channels", "notify.dnd"))
            )
            assert values == {"ui.theme": {"mode": "dark"}, "notify.channels": {"inbox": True}}
            assert await repository.count_for_user(user_id) == 3
            assert await PreferenceRepository(cast("DbSession", session)).get_many(
                user_id, ConcurrentStableList()
            ) == {}
