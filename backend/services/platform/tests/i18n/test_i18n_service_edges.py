"""国际化服务边界用例（Kiwi 2404）：可选字段组合、无变化保存、空变更集、筛选分支。

补充 `test_locale_api` / `test_message_api` 未覆盖的分支，保证改动模块行 + 分支全覆盖。
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

_TABLES: ConcurrentStableList[Table] = ConcurrentStableList(
    (cast("Table", SysI18nLocale.__table__), cast("Table", SysI18nMessage.__table__))
)


async def _cleanup(db: AsyncSession) -> None:
    """清理用例数据并把种子行复位。

    Args:
        db: 租户库会话。
    """
    for row in (
        (await db.execute(select(SysI18nMessage).where(SysI18nMessage.msg_key.like("zztest.%")))).scalars().all()
    ):
        await db.delete(row)
    for row in (await db.execute(select(SysI18nLocale).where(SysI18nLocale.code.like("zz-%")))).scalars().all():
        await db.delete(row)
    await db.commit()


@pytest_asyncio.fixture(autouse=True)
async def i18n_state(tenant_db: str, shared_tenant_engine: AsyncEngine, client: AsyncClient) -> AsyncIterator[None]:
    """串行持有 i18n 全局锁：建表 → 补种 → 清场 → 用例 → 清场。

    Args:
        tenant_db: 共享租户库连接串（夹具副作用：注入租户库环境变量）。
        shared_tenant_engine: 共享租户库引擎。

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


async def test_update_optional_fields_and_filters(client: AsyncClient) -> None:
    """修改只传名 / 只传排序 / 状态不变；列表按状态筛选、含回收站视图。"""
    created = (await client.post("/api/v1/i18n/locales", json={"code": "zz-AA", "name": "测试", "sort": 5})).json()[
        "data"
    ]

    only_name = await client.put("/api/v1/i18n/locales/zz-AA", json={"name": "改名", "version": created["version"]})
    assert only_name.status_code == 200
    version = only_name.json()["data"]["version"]

    only_sort = await client.put("/api/v1/i18n/locales/zz-AA", json={"sort": 7, "version": version})
    assert only_sort.status_code == 200
    assert only_sort.json()["data"]["sort"] == 7

    disabled = await client.put(
        "/api/v1/i18n/locales/zz-AA", json={"status": "disabled", "version": only_sort.json()["data"]["version"]}
    )
    assert disabled.status_code == 200

    by_status = (await client.get("/api/v1/i18n/locales", params={"status": "disabled", "keyword": "zz-AA"})).json()[
        "data"
    ]
    assert by_status["total"] == 1
    without_deleted = (
        await client.get("/api/v1/i18n/locales", params={"keyword": "zz-AA", "include_deleted": False})
    ).json()["data"]
    assert without_deleted["total"] == 1

    removed = await client.delete("/api/v1/i18n/locales/zz-AA")
    assert removed.status_code == 200, removed.text
    with_deleted = (
        await client.get("/api/v1/i18n/locales", params={"keyword": "zz-AA", "include_deleted": True})
    ).json()["data"]
    assert with_deleted["total"] == 1
    assert with_deleted["list"][0]["deleted_at"] is not None


async def test_create_default_requires_enabled(client: AsyncClient) -> None:
    """新增即为默认语言时必须启用（否则 44003）。"""
    resp = await client.post(
        "/api/v1/i18n/locales",
        json={"code": "zz-BB", "name": "测试", "is_default": True, "status": "disabled"},
    )
    assert resp.json()["code"] == 44003


async def test_update_default_requires_enabled(client: AsyncClient) -> None:
    """把停用语言设为默认 → 44003。"""
    created = (
        await client.post("/api/v1/i18n/locales", json={"code": "zz-CC", "name": "测试", "status": "disabled"})
    ).json()["data"]
    resp = await client.put("/api/v1/i18n/locales/zz-CC", json={"is_default": True, "version": created["version"]})
    assert resp.json()["code"] == 44003


async def test_delete_last_enabled_language(client: AsyncClient, shared_tenant_engine: AsyncEngine) -> None:
    """删除最后一种启用语言 → 44004（构造无默认语言的脏状态）。"""
    await client.post("/api/v1/i18n/locales", json={"code": "zz-DD", "name": "测试"})
    factory: async_sessionmaker[AsyncSession] = async_sessionmaker(shared_tenant_engine, expire_on_commit=False)
    async with factory() as db:
        await db.execute(
            update(SysI18nLocale)
            .where(SysI18nLocale.code.in_(("zh-CN", "en-US")))
            .values(status="disabled", is_default=False)
        )
        await db.commit()
    resp = await client.delete("/api/v1/i18n/locales/zz-DD")
    assert resp.json()["code"] == 44004
    async with factory() as db:
        await db.execute(
            update(SysI18nLocale).where(SysI18nLocale.code == "zh-CN").values(status="enabled", is_default=True)
        )
        await db.commit()


async def test_message_adds_unchanged_keeps_zero_update(client: AsyncClient, ns: Any) -> None:  # pyright: ignore[reportAny]
    """重复提交同值（含备注）不产生更新；带备注新增可落备注。"""
    msg_key = f"zztest.{ns.prefix}.same"
    first = await client.put(
        "/api/v1/i18n/messages",
        json={"adds": [{"msg_key": msg_key, "locale": "zh-CN", "value": "同值", "remark": "说明"}]},
    )
    assert first.status_code == 200, first.text
    second = await client.put(
        "/api/v1/i18n/messages",
        json={"adds": [{"msg_key": msg_key, "locale": "zh-CN", "value": "同值", "remark": "说明"}]},
    )
    data = second.json()["data"]
    assert data["created"] == 0
    assert data["updated"] == 0

    page = (await client.get("/api/v1/i18n/messages/manage", params={"keyword": msg_key})).json()["data"]
    assert page["list"][0]["remark"] == "说明"


async def test_message_updates_same_value_and_empty_changes(client: AsyncClient, ns: Any) -> None:  # pyright: ignore[reportAny]
    """修改为同值仍计更新但不产生审计变更；空变更集正常返回。"""
    msg_key = f"zztest.{ns.prefix}.same2"
    await client.put("/api/v1/i18n/messages", json={"adds": [{"msg_key": msg_key, "locale": "zh-CN", "value": "值"}]})
    page = (await client.get("/api/v1/i18n/messages/manage", params={"keyword": msg_key})).json()["data"]
    item = page["list"][0]

    same = await client.put(
        "/api/v1/i18n/messages",
        json={"updates": [{"id": item["id"], "value": "值", "version": item["version"]}]},
    )
    assert same.json()["data"]["updated"] == 1

    empty = await client.put("/api/v1/i18n/messages", json={"adds": [], "updates": [], "deletes": []})
    assert empty.status_code == 200, empty.text
    assert empty.json()["data"]["created"] == 0

    by_module = (
        await client.get("/api/v1/i18n/messages/manage", params={"module": "zztest", "keyword": ns.prefix})
    ).json()["data"]
    assert by_module["total"] >= 1


def test_domain_public_surface() -> None:
    """域公共出口为空占位（本域无跨域使用方）。"""
    from bms_platform.domains.i18n import public

    assert public.__all__ == []


def test_message_helpers() -> None:
    """服务内部辅助：幂等载荷转 int / 覆盖标记派生。"""
    from bms_platform.domains.i18n.services import message as message_service

    assert message_service._as_int(True) == 1  # pyright: ignore[reportPrivateUsage]
    assert message_service._as_int(3) == 3  # pyright: ignore[reportPrivateUsage]
    assert message_service._as_int("7") == 7  # pyright: ignore[reportPrivateUsage]
    assert message_service._as_int("x") == 0  # pyright: ignore[reportPrivateUsage]
    assert message_service._as_int(None) == 0  # pyright: ignore[reportPrivateUsage]
    assert message_service._overridden("common.confirm", "zh-CN", "确认") is False  # pyright: ignore[reportPrivateUsage]
    assert message_service._overridden("zztest.x.y", "zh-CN", "值") is True  # pyright: ignore[reportPrivateUsage]


async def test_list_without_filters(client: AsyncClient) -> None:
    """不带筛选的列表：语言清单与语言包都能分页返回（覆盖无关键字分支）。"""
    locales = (await client.get("/api/v1/i18n/locales")).json()["data"]
    assert locales["total"] >= 2
    messages = (await client.get("/api/v1/i18n/messages/manage")).json()["data"]
    assert messages["total"] >= 1
