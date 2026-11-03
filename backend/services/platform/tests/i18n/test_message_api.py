"""语言包维护接口测试（Kiwi 2404）：维护列表 / 差异三段批量保存 / 幂等 / 删除边界 / 缓存失效。

共享库叠加：只读写本用例自建 key（`zztest.*`），用例前后硬删；种子行只读。
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, cast

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import Table, select
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
    """删除本用例自建文案并补齐种子。

    Args:
        db: 租户库会话。
    """
    for row in (
        (await db.execute(select(SysI18nMessage).where(SysI18nMessage.msg_key.like("zztest.%")))).scalars().all()
    ):
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


def _add(ns: Any, suffix: str, value: str = "测试文案", locale: str = "zh-CN") -> Any:  # pyright: ignore[reportAny]
    """构造新增行。

    Args:
        ns: 用例命名空间。
        suffix: key 后缀。
        value: 文案。
        locale: 语言。

    Returns:
        Any: 新增行。
    """
    return {"msg_key": f"zztest.{ns.prefix}.{suffix}", "locale": locale, "value": value}


async def _save(client: AsyncClient, payload: Any, **headers: str) -> Any:
    """批量保存（成功路径简写）。

    Args:
        client: 测试客户端。
        payload: 请求体。
        **headers: 额外请求头（幂等键）。

    Returns:
        Any: 响应 data。
    """
    resp = await client.put("/api/v1/i18n/messages", json=payload, headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["code"] == 0, body
    return body["data"]


async def test_save_adds_then_upsert(client: AsyncClient, ns: Any) -> None:  # pyright: ignore[reportAny]
    """新增 → 同 (key, locale) 再次提交转为更新；列表可筛选到。"""
    result = await _save(client, {"adds": [_add(ns, "confirm")]})
    assert result["created"] == 1
    assert result["updated"] == 0
    assert result["version"] >= 1

    again = await _save(client, {"adds": [_add(ns, "confirm", "确认（改）")]})
    assert again["created"] == 0
    assert again["updated"] == 1

    page = (
        await client.get("/api/v1/i18n/messages/manage", params={"keyword": f"zztest.{ns.prefix}", "locale": "zh-CN"})
    ).json()["data"]
    assert page["total"] == 1
    item = page["list"][0]
    assert item["value"] == "确认（改）"
    assert item["module"] == "zztest"
    assert item["is_overridden"] is True


async def test_save_updates_optimistic_lock(client: AsyncClient, ns: Any) -> None:  # pyright: ignore[reportAny]
    """修改：成功；版本冲突 10004；行不存在 44008。"""
    await _save(client, {"adds": [_add(ns, "confirm")]})
    page = (await client.get("/api/v1/i18n/messages/manage", params={"keyword": f"zztest.{ns.prefix}"})).json()["data"]
    item = page["list"][0]

    updated = await _save(client, {"updates": [{"id": item["id"], "value": "新文案", "version": item["version"]}]})
    assert updated["updated"] == 1

    conflict = await client.put(
        "/api/v1/i18n/messages",
        json={"updates": [{"id": item["id"], "value": "再次修改", "version": item["version"]}]},
    )
    assert conflict.status_code == 409
    assert conflict.json()["code"] == 10004

    missing = await client.put(
        "/api/v1/i18n/messages", json={"updates": [{"id": 999999999999, "value": "x", "version": 1}]}
    )
    assert missing.status_code == 404
    assert missing.json()["code"] == 44008


async def test_save_deletes_only_overridden(client: AsyncClient, ns: Any) -> None:  # pyright: ignore[reportAny]
    """删除：租户自建行可删；平台默认行拒绝 44008。"""
    await _save(client, {"adds": [_add(ns, "confirm")]})
    page = (await client.get("/api/v1/i18n/messages/manage", params={"keyword": f"zztest.{ns.prefix}"})).json()["data"]
    item = page["list"][0]

    deleted = await _save(client, {"deletes": [item["id"]]})
    assert deleted["deleted"] == 1

    seed_page = (
        await client.get("/api/v1/i18n/messages/manage", params={"keyword": "common.confirm", "locale": "zh-CN"})
    ).json()["data"]
    seed_item = seed_page["list"][0]
    assert seed_item["is_overridden"] is False
    protected = await client.put("/api/v1/i18n/messages", json={"deletes": [seed_item["id"]]})
    assert protected.status_code == 404
    assert protected.json()["code"] == 44008


async def test_save_validation_branches(client: AsyncClient, ns: Any) -> None:  # pyright: ignore[reportAny]
    """校验：key 非法 / 语言未登记 / 值超长均 44003。"""
    bad_key = await client.put(
        "/api/v1/i18n/messages", json={"adds": [{"msg_key": "Bad Key", "locale": "zh-CN", "value": "x"}]}
    )
    assert bad_key.json()["code"] == 44003

    bad_locale = await client.put(
        "/api/v1/i18n/messages", json={"adds": [{"msg_key": "zztest.x.y", "locale": "xx-XX", "value": "x"}]}
    )
    assert bad_locale.json()["code"] == 44003

    too_long = await client.put(
        "/api/v1/i18n/messages",
        json={"adds": [{"msg_key": "zztest.x.y", "locale": "zh-CN", "value": "x" * 4001}]},
    )
    assert too_long.json()["code"] in (10001, 44003)


async def test_save_idempotency(client: AsyncClient, ns: Any) -> None:  # pyright: ignore[reportAny]
    """幂等：同 Idempotency-Key 重复提交返回首次结果且不重复写。"""
    payload: Any = {"adds": [_add(ns, "confirm")]}
    first = await _save(client, payload, **{"Idempotency-Key": f"{ns.prefix}-idem"})
    second = await _save(client, payload, **{"Idempotency-Key": f"{ns.prefix}-idem"})
    assert first["created"] == 1
    # 测试环境幂等存储为 null 占位：重复提交按「同 (key, locale) 已存在」处理，绝不重复建行；
    # 真实幂等（Redis）下的「重放返回首次结果」由集成用例覆盖（部署窗口）。
    assert second["created"] == 0
    assert second["deleted"] == 0

    page = (await client.get("/api/v1/i18n/messages/manage", params={"keyword": f"zztest.{ns.prefix}"})).json()["data"]
    assert page["total"] == 1


async def test_missing_only_filter(client: AsyncClient, ns: Any) -> None:  # pyright: ignore[reportAny]
    """只看缺失：空文案命中，有文案不命中。"""
    await _save(client, {"adds": [_add(ns, "empty", ""), _add(ns, "filled", "有值")]})
    missing = (
        await client.get(
            "/api/v1/i18n/messages/manage",
            params={"keyword": f"zztest.{ns.prefix}", "missing_only": True},
        )
    ).json()["data"]
    assert missing["total"] == 1
    assert missing["list"][0]["value"] == ""


async def test_cache_invalidate(client: AsyncClient) -> None:
    """缓存主动失效：返回非零版本且未降级。"""
    resp = await client.put("/api/v1/i18n/cache/invalidate")
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["version"] >= 1
    assert data["degraded"] is False
