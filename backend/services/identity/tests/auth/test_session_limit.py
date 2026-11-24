"""多端会话上限测试（Kiwi 2195）：超限作废最旧、上限可配、未超限不作废。

单库叠加口径（04-6-2）：上限按**用户**统计，用户主键按用例命名空间派生；列表断言带 `user_id`
筛选，不再依赖「整表 total」。
"""

from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from bms_core.security.session import DefaultSessionSecurity
from bms_core.testing.namespace import Namespace

from .session_helpers import API_SESSIONS, TENANT_HEADERS, login, uid, wire_login


@pytest.fixture(autouse=True)
def _restore_max_active(service_app: FastAPI) -> Iterator[None]:
    """每例复位进程级 `max_active` 配置（模块常驻 app 的 settings 是同一对象）。

    `wire_login(max_active=…)` 直接改 `app.state.settings`；装配常驻后同一模块复用同一
    Settings 实例，不复位会让「默认上限 5」用例读到上一例写的 2 / 3。

    Args:
        service_app: 模块级常驻应用（取共享 Settings 实例）。
    """
    original = service_app.state.settings.session.max_active
    yield
    service_app.state.settings.session.max_active = original


def _blacklist_key(session_id: str) -> str:
    """会话黑名单键（与配置 `secret_key=""` 一致）。

    Args:
        session_id: 会话 id。

    Returns:
        str: 黑名单键。
    """
    return DefaultSessionSecurity(secret_key="").blacklist_key(session_id)


@pytest.mark.kiwi_id(2195)
async def test_max_active_revokes_oldest(client: AsyncClient, service_app: FastAPI, ns: Namespace) -> None:
    """上限 2：第 3 次登录作废最旧会话（标记删除 + 黑名单）。"""
    issuer, store, _recorder = await wire_login(service_app, ns=ns, max_active=2)
    for _ in range(3):
        assert (await login(client)).status_code == 200
    oldest, second, newest = issuer.specs[-3].session_id, issuer.specs[-2].session_id, issuer.specs[-1].session_id

    assert await store.load(oldest, tenant="demo") is None
    assert await store.is_blacklisted(_blacklist_key(oldest)) is True
    assert await store.load(second, tenant="demo") is not None
    assert await store.load(newest, tenant="demo") is not None

    listing = await client.get(API_SESSIONS, params={"user_id": uid(ns)}, headers=TENANT_HEADERS)
    assert listing.json()["data"]["total"] == 2


@pytest.mark.kiwi_id(2195)
async def test_max_active_default_five(client: AsyncClient, service_app: FastAPI, ns: Namespace) -> None:
    """默认上限 5：第 6 次登录作废最旧，在线数保持 5。"""
    issuer, store, _recorder = await wire_login(service_app, ns=ns)
    for _ in range(6):
        assert (await login(client)).status_code == 200

    assert await store.load(issuer.specs[-6].session_id, tenant="demo") is None
    assert await store.load(issuer.specs[-1].session_id, tenant="demo") is not None
    listing = await client.get(API_SESSIONS, params={"user_id": uid(ns)}, headers=TENANT_HEADERS)
    assert listing.json()["data"]["total"] == 5


@pytest.mark.kiwi_id(2195)
async def test_below_max_active_keeps_all(client: AsyncClient, service_app: FastAPI, ns: Namespace) -> None:
    """未达上限不作废：上限 3、登录 2 次两会话均保留。"""
    issuer, store, _recorder = await wire_login(service_app, ns=ns, max_active=3)
    for _ in range(2):
        assert (await login(client)).status_code == 200

    assert await store.load(issuer.specs[-2].session_id, tenant="demo") is not None
    assert await store.load(issuer.specs[-1].session_id, tenant="demo") is not None
    listing = await client.get(API_SESSIONS, params={"user_id": uid(ns)}, headers=TENANT_HEADERS)
    assert listing.json()["data"]["total"] == 2
