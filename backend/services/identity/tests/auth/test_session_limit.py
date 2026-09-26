"""多端会话上限测试（Kiwi 2195）：超限作废最旧、上限可配、未超限不作废。"""

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from bms_core.security.session import DefaultSessionSecurity

from .session_helpers import API_SESSIONS, TENANT_HEADERS, login, wire_login


def _blacklist_key(session_id: str) -> str:
    """会话黑名单键（与配置 `secret_key=""` 一致）。

    Args:
        session_id: 会话 id。

    Returns:
        str: 黑名单键。
    """
    return DefaultSessionSecurity(secret_key="").blacklist_key(session_id)


@pytest.mark.kiwi_id(2195)
async def test_max_active_revokes_oldest(client: AsyncClient, service_app: FastAPI) -> None:
    """上限 2：第 3 次登录作废最旧会话（标记删除 + 黑名单）。"""
    issuer, store, _recorder = wire_login(service_app, max_active=2)
    for _ in range(3):
        assert (await login(client)).status_code == 200
    oldest, second, newest = issuer.specs[-3].session_id, issuer.specs[-2].session_id, issuer.specs[-1].session_id

    assert await store.load(oldest, tenant="demo") is None
    assert await store.is_blacklisted(_blacklist_key(oldest)) is True
    assert await store.load(second, tenant="demo") is not None
    assert await store.load(newest, tenant="demo") is not None

    listing = await client.get(API_SESSIONS, headers=TENANT_HEADERS)
    assert listing.json()["data"]["total"] == 2


@pytest.mark.kiwi_id(2195)
async def test_max_active_default_five(client: AsyncClient, service_app: FastAPI) -> None:
    """默认上限 5：第 6 次登录作废最旧，在线数保持 5。"""
    issuer, store, _recorder = wire_login(service_app)
    for _ in range(6):
        assert (await login(client)).status_code == 200

    assert await store.load(issuer.specs[-6].session_id, tenant="demo") is None
    assert await store.load(issuer.specs[-1].session_id, tenant="demo") is not None
    listing = await client.get(API_SESSIONS, headers=TENANT_HEADERS)
    assert listing.json()["data"]["total"] == 5


@pytest.mark.kiwi_id(2195)
async def test_below_max_active_keeps_all(client: AsyncClient, service_app: FastAPI) -> None:
    """未达上限不作废：上限 3、登录 2 次两会话均保留。"""
    issuer, store, _recorder = wire_login(service_app, max_active=3)
    for _ in range(2):
        assert (await login(client)).status_code == 200

    assert await store.load(issuer.specs[-2].session_id, tenant="demo") is not None
    assert await store.load(issuer.specs[-1].session_id, tenant="demo") is not None
    listing = await client.get(API_SESSIONS, headers=TENANT_HEADERS)
    assert listing.json()["data"]["total"] == 2
