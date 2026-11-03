"""个人中心偏好接口测试（Kiwi 2405）：存值 / 生效值派生 / 校验分支。

覆盖需求 06-2 的完成标准：切换时区后**存储值按用户输入变化**（存储不改语义）、未设置时按生效语言派生、
非法时区（含固定偏移）与未登记语言被拒；接口登录即可、仅本人。
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import cast

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import Table
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.i18n.seed import seed_i18n_in_session
from bms_core.models.platform.i18n import SysI18nLocale
from bms_core.models.platform.user import SysUser
from bms_core.testing.schema import ensure_tables
from tests_support.auth import TEST_SUBJECT
from tests_support.locks import file_lock

pytestmark = [pytest.mark.kiwi_id(2405)]

_URI = "/api/v1/profile/preferences"
_USER_ID = int(TEST_SUBJECT)
_TABLES: ConcurrentStableList[Table] = ConcurrentStableList(
    (cast("Table", SysUser.__table__), cast("Table", SysI18nLocale.__table__))
)


async def _reset_user(db: AsyncSession) -> None:
    """确保测试用户存在且偏好清空（用例前后各调一次）。

    Args:
        db: 租户库会话。
    """
    row = await db.get(SysUser, _USER_ID)
    if row is None:
        db.add(
            SysUser(
                id=_USER_ID,
                username="profile_probe",
                password_hash="hash",
                name="偏好用例",
                status="enabled",
            )
        )
    else:
        row.locale = None
        row.timezone = None
        row.deleted_at = None
    await db.commit()


@pytest_asyncio.fixture(autouse=True)
async def profile_state(tenant_db: str, shared_tenant_engine: AsyncEngine, client: AsyncClient) -> AsyncIterator[None]:
    """串行持有 i18n 锁：建表 → 补种语言清单 → 复位用户偏好 → 失效清单缓存 → 用例 → 复位。

    Args:
        tenant_db: 共享租户库连接串（夹具副作用：注入 `BMS_DATABASE__TENANTS__URL` 供应用读同一库）。
        shared_tenant_engine: 共享租户库引擎。
        client: 测试客户端（用于主动失效清单缓存，避免并发用例留下陈旧快照）。

    Yields:
        None: 用例运行期。
    """
    del tenant_db
    with file_lock("i18n-locale-message"):
        await ensure_tables(shared_tenant_engine, _TABLES)
        factory: async_sessionmaker[AsyncSession] = async_sessionmaker(shared_tenant_engine, expire_on_commit=False)
        async with factory() as db:
            await seed_i18n_in_session(db)
            await _reset_user(db)
            await client.put("/api/v1/i18n/cache/invalidate")
            yield
            await _reset_user(db)


async def test_get_preferences_defaults(client: AsyncClient) -> None:
    """未设置时：存值为空、生效值为系统默认语言与其时区。"""
    resp = await client.get(_URI)
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["locale"] is None
    assert data["timezone"] is None
    assert data["effective_locale"] == "zh-CN"
    assert data["effective_timezone"] == "Asia/Shanghai"


async def test_put_sets_locale_and_timezone(client: AsyncClient) -> None:
    """设置语言与时区：存值原样保存，生效值同步为所设值。"""
    resp = await client.put(_URI, json={"locale": "en-US", "timezone": "UTC"})
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["locale"] == "en-US"
    assert data["timezone"] == "UTC"
    assert data["effective_locale"] == "en-US"
    assert data["effective_timezone"] == "UTC"

    fetched = (await client.get(_URI)).json()["data"]
    assert (fetched["locale"], fetched["timezone"]) == ("en-US", "UTC")


async def test_put_partial_update_keeps_other_field(client: AsyncClient) -> None:
    """部分更新：只传时区时语言保持不变。"""
    await client.put(_URI, json={"locale": "en-US"})
    resp = await client.put(_URI, json={"timezone": "Asia/Tokyo"})
    data = resp.json()["data"]
    assert data["locale"] == "en-US"
    assert data["timezone"] == "Asia/Tokyo"


async def test_put_null_clears_and_derives(client: AsyncClient) -> None:
    """显式 null 清空：存值回到空，生效值按默认规则派生。"""
    await client.put(_URI, json={"locale": "en-US", "timezone": "UTC"})
    resp = await client.put(_URI, json={"locale": None, "timezone": None})
    data = resp.json()["data"]
    assert data["locale"] is None
    assert data["timezone"] is None
    assert data["effective_locale"] == "zh-CN"
    assert data["effective_timezone"] == "Asia/Shanghai"


async def test_put_locale_normalized_to_canonical_case(client: AsyncClient) -> None:
    """语言大小写不敏感：`EN-us` 归一为清单内标准形态 `en-US`。"""
    resp = await client.put(_URI, json={"locale": "EN-us"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["locale"] == "en-US"


async def test_put_rejects_unknown_locale(client: AsyncClient) -> None:
    """未登记语言被拒（44010）。"""
    resp = await client.put(_URI, json={"locale": "fr-FR"})
    assert resp.status_code == 400
    assert resp.json()["code"] == 44010


async def test_put_rejects_invalid_timezone(client: AsyncClient) -> None:
    """非法时区（不存在 / 固定偏移）被拒（44009）。"""
    for value in ("Mars/Base", "UTC+08:00"):
        resp = await client.put(_URI, json={"timezone": value})
        assert resp.status_code == 400, resp.text
        assert resp.json()["code"] == 44009
    stored = (await client.get(_URI)).json()["data"]
    assert stored["timezone"] is None


async def test_put_without_any_field_rejected(client: AsyncClient) -> None:
    """两个字段都没提供视为无变更（10001）。"""
    resp = await client.put(_URI, json={})
    assert resp.status_code == 200, resp.text
    assert resp.json()["code"] == 10001


async def test_get_when_user_missing(client: AsyncClient, shared_tenant_engine: AsyncEngine) -> None:
    """会话与库不一致（用户已被删）时返回用户不存在，而非 500。"""
    factory: async_sessionmaker[AsyncSession] = async_sessionmaker(shared_tenant_engine, expire_on_commit=False)
    async with factory() as db:
        row = await db.get(SysUser, _USER_ID)
        assert row is not None
        row.soft_delete()
        await db.commit()
    try:
        resp = await client.get(_URI)
        assert resp.status_code == 404, resp.text
    finally:
        async with factory() as db:
            row = await db.get(SysUser, _USER_ID, with_for_update=False)
            assert row is not None
            row.deleted_at = None
            await db.commit()


async def test_put_when_user_missing(client: AsyncClient, shared_tenant_engine: AsyncEngine) -> None:
    """保存时用户已被删（会话与库不一致）→ 用户不存在，不落库。"""
    factory: async_sessionmaker[AsyncSession] = async_sessionmaker(shared_tenant_engine, expire_on_commit=False)
    async with factory() as db:
        row = await db.get(SysUser, _USER_ID)
        assert row is not None
        row.soft_delete()
        await db.commit()
    try:
        resp = await client.put(_URI, json={"locale": "en-US"})
        assert resp.status_code == 404, resp.text
    finally:
        async with factory() as db:
            row = await db.get(SysUser, _USER_ID)
            assert row is not None
            row.deleted_at = None
            await db.commit()
