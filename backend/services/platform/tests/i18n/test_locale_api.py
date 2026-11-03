"""语言清单管理接口测试（Kiwi 2404）：分页 / 启用清单 / 新增 / 修改 / 删除与保护分支。

鉴权口径：默认 `NullPermissionChecker` 恒放行（`assign_system_admin` 置内置系统管理员命中豁免层级）；
真实 403 越权分支由安全专项补齐，本文件不用假用例凑数。

共享库叠加：跑共享租户库；用例自建语言统一用 IETF 私有标签 `zz-QQ`，用例前后硬删该语言与其文案，
种子行（`zh-CN` / `en-US`）只在「切换默认语言」用例里被改，并由重置逻辑恢复。
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, cast

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import Table, select, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.i18n.seed import seed_i18n_in_session
from bms_core.models.platform.i18n import SysI18nLocale, SysI18nMessage
from bms_core.testing.schema import ensure_tables
from tests_support.locks import file_lock
from tests_support.permission_admin import assign_system_admin

pytestmark = [pytest.mark.kiwi_id(2404)]

_TEST_LOCALE = "zz-QQ"
"""用例自建语言（IETF 私有标签；用例前后清理）。"""

_TABLES: ConcurrentStableList[Table] = ConcurrentStableList(
    (cast("Table", SysI18nLocale.__table__), cast("Table", SysI18nMessage.__table__))
)


async def _cleanup(db: AsyncSession) -> None:
    """清理用例自建语言与其文案，并把种子行复位到平台默认态。

    Args:
        db: 租户库会话。
    """
    for row in (await db.execute(select(SysI18nMessage).where(SysI18nMessage.locale == _TEST_LOCALE))).scalars().all():
        await db.delete(row)
    for row in (await db.execute(select(SysI18nLocale).where(SysI18nLocale.code == _TEST_LOCALE))).scalars().all():
        await db.delete(row)
    await db.execute(
        update(SysI18nLocale)
        .where(SysI18nLocale.code.in_(("zh-CN", "en-US")))
        .values(status="enabled", is_default=False, is_overridden=False, name="简体中文", rtl=False)
    )
    await db.execute(
        update(SysI18nLocale).where(SysI18nLocale.code == "zh-CN").values(name="简体中文", is_default=True)
    )
    await db.execute(
        update(SysI18nLocale).where(SysI18nLocale.code == "en-US").values(name="English", is_default=False)
    )
    await db.commit()


@pytest_asyncio.fixture(autouse=True)
async def i18n_state(tenant_db: str, shared_tenant_engine: AsyncEngine, client: AsyncClient) -> AsyncIterator[None]:
    """串行持有 i18n 全局锁：建表 → 补种 → 清场 → 用例 → 清场。

    Args:
        tenant_db: 共享租户库连接串（夹具副作用：注入 `BMS_DATABASE__TENANTS__URL` 供权限夹具使用）。
        shared_tenant_engine: 共享租户库引擎（基座夹具）。

    Yields:
        None: 用例运行期。
    """
    del tenant_db
    with file_lock("i18n-locale-message"):
        await ensure_tables(shared_tenant_engine, _TABLES)
        factory: async_sessionmaker[AsyncSession] = async_sessionmaker(shared_tenant_engine, expire_on_commit=False)
        async with factory() as db:
            await seed_i18n_in_session(db)
            await _cleanup(db)
            await assign_system_admin()
            await client.put("/api/v1/i18n/cache/invalidate")
            yield
            await _cleanup(db)


def _locale_payload(code: object = _TEST_LOCALE, **extra: object) -> Any:
    """构造新增语言请求。

    Args:
        code: 语言标识。
        **extra: 额外字段。

    Returns:
        Any: 请求体。
    """
    return dict({"code": str(code), "name": "测试语言", **extra})


async def _create(client: AsyncClient, **extra: object) -> Any:
    """新增语言（成功路径简写）。

    Args:
        client: 测试客户端。
        **extra: 请求字段（`code` 缺省为测试语言）。

    Returns:
        Any: 响应 data。
    """
    resp = await client.post("/api/v1/i18n/locales", json=_locale_payload(**extra))
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


async def test_list_and_enabled(client: AsyncClient) -> None:
    """分页结构与启用清单：只返回启用行，新增后立即可见。"""
    page = (await client.get("/api/v1/i18n/locales", params={"keyword": "zh-CN"})).json()["data"]
    assert page["total"] == 1
    assert page["list"][0]["code"] == "zh-CN"
    assert page["list"][0]["is_default"] is True

    created = await _create(client, rtl=True, sort=30)
    assert created["code"] == _TEST_LOCALE
    assert created["rtl"] is True

    enabled = (await client.get("/api/v1/i18n/locales/enabled")).json()["data"]["items"]
    codes = [item["code"] for item in enabled]
    assert _TEST_LOCALE in codes
    tested = next(item for item in enabled if item["code"] == _TEST_LOCALE)
    assert tested["rtl"] is True
    assert tested["is_default"] is False

    absent = (await client.get("/api/v1/i18n/locales", params={"keyword": "no-such-locale"})).json()["data"]
    assert absent["total"] == 0
    assert absent["list"] == []


async def test_create_rejects_duplicate_and_invalid(client: AsyncClient) -> None:
    """新增：重复标识 44001（大小写不敏感）、格式非法 44003、状态非法 44003、名称空 44003。"""
    await _create(client)

    duplicate = await client.post("/api/v1/i18n/locales", json=_locale_payload(code="ZZ-qq"))
    assert duplicate.status_code == 409
    assert duplicate.json()["code"] == 44001

    invalid_code = await client.post("/api/v1/i18n/locales", json=_locale_payload(code="??"))
    assert invalid_code.status_code == 400
    assert invalid_code.json()["code"] == 44003

    invalid_name = await client.post("/api/v1/i18n/locales", json=_locale_payload(code="zz-AA", name="   "))
    # 空白名称在 pydantic 层被拦（strip 后不足 1 字符）→ 统一参数错误 10001（业务失败统一 200）
    assert invalid_name.status_code == 200, invalid_name.text
    assert invalid_name.json()["code"] == 10001

    invalid_status = await client.post("/api/v1/i18n/locales", json=_locale_payload(code="zz-AA", status="unknown"))
    assert invalid_status.status_code == 400
    assert invalid_status.json()["code"] == 44003


async def test_update_conflict_and_version(client: AsyncClient) -> None:
    """修改：成功改名 / RTL，乐观锁冲突 10004，语言不存在 44007。"""
    created = await _create(client)
    resp = await client.put(
        f"/api/v1/i18n/locales/{_TEST_LOCALE}",
        json={"name": "测试语言改名", "rtl": True, "version": created["version"]},
    )
    assert resp.status_code == 200, resp.text
    updated = resp.json()["data"]
    assert updated["name"] == "测试语言改名"
    assert updated["rtl"] is True
    assert updated["is_overridden"] is True

    conflict = await client.put(
        f"/api/v1/i18n/locales/{_TEST_LOCALE}", json={"name": "再次改名", "version": created["version"]}
    )
    assert conflict.status_code == 409
    assert conflict.json()["code"] == 10004

    missing = await client.put("/api/v1/i18n/locales/xx-XX", json={"name": "x", "version": 1})
    assert missing.status_code == 404
    assert missing.json()["code"] == 44007

    empty_name = await client.put(
        f"/api/v1/i18n/locales/{_TEST_LOCALE}", json={"name": " ", "version": updated["version"]}
    )
    assert empty_name.status_code == 200, empty_name.text
    assert empty_name.json()["code"] == 10001


async def test_default_locale_protection(client: AsyncClient, shared_tenant_engine: AsyncEngine) -> None:
    """默认语言：不可停用 44005、不可取消标记 44006、可切换；至少保留一种启用 44004。"""
    zh = (await client.get("/api/v1/i18n/locales", params={"keyword": "zh-CN"})).json()["data"]["list"][0]
    disable_default = await client.put(
        "/api/v1/i18n/locales/zh-CN", json={"status": "disabled", "version": zh["version"]}
    )
    assert disable_default.status_code == 403
    assert disable_default.json()["code"] == 44005

    unset_default = await client.put("/api/v1/i18n/locales/zh-CN", json={"is_default": False, "version": zh["version"]})
    assert unset_default.status_code == 409
    assert unset_default.json()["code"] == 44006

    created = await _create(client, is_default=True)
    assert created["is_default"] is True
    zh_after = (await client.get("/api/v1/i18n/locales", params={"keyword": "zh-CN"})).json()["data"]["list"][0]
    assert zh_after["is_default"] is False

    # 把默认切回 zh-CN（否则新建语言作为默认语言不可停用，44005 会先拦下）
    switch_back = await client.put(
        "/api/v1/i18n/locales/zh-CN", json={"is_default": True, "version": zh_after["version"]}
    )
    assert switch_back.status_code == 200, switch_back.text
    assert switch_back.json()["data"]["is_default"] is True

    disabled_new = await client.put(
        f"/api/v1/i18n/locales/{_TEST_LOCALE}", json={"status": "disabled", "version": created["version"]}
    )
    assert disabled_new.status_code == 200, disabled_new.text
    en = (await client.get("/api/v1/i18n/locales", params={"keyword": "en-US"})).json()["data"]["list"][0]

    # 「至少保留一种启用语言」（44004）是兜底防御：默认语言不可停用，故需构造「无默认语言」的脏状态
    factory: async_sessionmaker[AsyncSession] = async_sessionmaker(shared_tenant_engine, expire_on_commit=False)
    async with factory() as db:
        await db.execute(
            update(SysI18nLocale).where(SysI18nLocale.code == "zh-CN").values(status="disabled", is_default=False)
        )
        await db.commit()
    last_one = await client.put("/api/v1/i18n/locales/en-US", json={"status": "disabled", "version": en["version"]})
    assert last_one.status_code == 409
    assert last_one.json()["code"] == 44004
    async with factory() as db:
        await db.execute(
            update(SysI18nLocale).where(SysI18nLocale.code == "zh-CN").values(status="enabled", is_default=True)
        )
        await db.commit()


async def test_delete_protection_and_success(client: AsyncClient, shared_tenant_engine: AsyncEngine) -> None:
    """删除：默认语言 44005、有语言包数据 44002、不存在 44007、无文案可删成功。"""
    default_delete = await client.delete("/api/v1/i18n/locales/zh-CN")
    assert default_delete.status_code == 403
    assert default_delete.json()["code"] == 44005

    await _create(client)
    factory: async_sessionmaker[AsyncSession] = async_sessionmaker(shared_tenant_engine, expire_on_commit=False)
    async with factory() as db:
        db.add(SysI18nMessage(msg_key="zztest.confirm", name="zztest.confirm", locale=_TEST_LOCALE, value="确认"))
        await db.commit()

    has_messages = await client.delete(f"/api/v1/i18n/locales/{_TEST_LOCALE}")
    assert has_messages.status_code == 409
    assert has_messages.json()["code"] == 44002

    async with factory() as db:
        for row in (
            (await db.execute(select(SysI18nMessage).where(SysI18nMessage.locale == _TEST_LOCALE))).scalars().all()
        ):
            await db.delete(row)
        await db.commit()

    deleted = await client.delete(f"/api/v1/i18n/locales/{_TEST_LOCALE}")
    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["data"]["deleted"] is True

    missing = await client.delete(f"/api/v1/i18n/locales/{_TEST_LOCALE}")
    assert missing.status_code == 404
    assert missing.json()["code"] == 44007

    rows = await _select_codes(shared_tenant_engine)
    assert _TEST_LOCALE not in rows


async def _select_codes(engine: AsyncEngine) -> list[str]:  # bare-collections:allow（测试断言辅助）
    """取当前未删语言标识（断言删除生效）。

    Args:
        engine: 共享租户库引擎。

    Returns:
        list[str]: 语言标识清单。
    """
    factory: async_sessionmaker[AsyncSession] = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db:
        rows = (await db.execute(select(SysI18nLocale.code).where(SysI18nLocale.deleted_at.is_(None)))).scalars().all()
        return [str(code) for code in rows]
