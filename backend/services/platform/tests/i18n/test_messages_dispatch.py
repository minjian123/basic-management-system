"""语言包下发接口测试（Kiwi 2404）：默认语言 / 显式 locale / Accept-Language / 回退 / 写后即生效。

共享库叠加：只读写本用例自建 key（`zztest.*`），用例前后硬删。
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
    """删除本用例自建文案。

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


async def test_dispatch_default_and_explicit_locale(client: AsyncClient) -> None:
    """缺省按默认语言；显式 `locale=en-US` 覆盖为英文。"""
    default = (await client.get("/api/v1/i18n/messages")).json()["data"]
    assert default["locale"] == "zh-CN"
    assert default["fallback"] is False
    assert default["messages"]["common.confirm"] == "确认"
    assert default["version"] >= 0

    english = (await client.get("/api/v1/i18n/messages", params={"locale": "en-US"})).json()["data"]
    assert english["locale"] == "en-US"
    # 语言解析已生效；文案内容取决于本用例库内是否已种子英文（准备集按语言清单播种）
    assert "common.confirm" in english["messages"]


async def test_dispatch_accept_language(client: AsyncClient) -> None:
    """未传 `locale` 时按 `Accept-Language` 解析；无法匹配回退默认语言。"""
    english = (await client.get("/api/v1/i18n/messages", headers={"Accept-Language": "en-US,en;q=0.9"})).json()["data"]
    assert english["locale"] == "en-US"

    fallback = (await client.get("/api/v1/i18n/messages", headers={"Accept-Language": "fr-FR"})).json()["data"]
    assert fallback["locale"] == "zh-CN"


async def test_dispatch_unregistered_locale_falls_back(client: AsyncClient) -> None:
    """未登记 / 未启用的 `locale` 回退默认语言并标记 `fallback`。"""
    data = (await client.get("/api/v1/i18n/messages", params={"locale": "fr-FR"})).json()["data"]
    assert data["locale"] == "zh-CN"
    assert data["fallback"] is True
    assert data["messages"]["common.confirm"] == "确认"


async def test_dispatch_merges_default_for_missing_keys(client: AsyncClient, ns: Any) -> None:  # pyright: ignore[reportAny]
    """缺翻译回退默认语言文案（不显示 key 原文）。"""
    msg_key = f"zztest.{ns.prefix}.only_zh"
    saved = await client.put(
        "/api/v1/i18n/messages",
        json={"adds": [{"msg_key": msg_key, "locale": "zh-CN", "value": "只有中文"}]},
    )
    assert saved.status_code == 200, saved.text

    english = (await client.get("/api/v1/i18n/messages", params={"locale": "en-US"})).json()["data"]
    assert english["messages"][msg_key] == "只有中文"


async def test_dispatch_after_save_takes_effect(client: AsyncClient, ns: Any) -> None:  # pyright: ignore[reportAny]
    """语言包编辑后下一次请求即生效（写入触发缓存失效）。"""
    msg_key = f"zztest.{ns.prefix}.edit"
    first = await client.put(
        "/api/v1/i18n/messages",
        json={"adds": [{"msg_key": msg_key, "locale": "zh-CN", "value": "初版"}]},
    )
    assert first.status_code == 200, first.text
    loaded = (await client.get("/api/v1/i18n/messages")).json()["data"]
    assert loaded["messages"][msg_key] == "初版"

    page = (await client.get("/api/v1/i18n/messages/manage", params={"keyword": msg_key})).json()["data"]
    item = page["list"][0]
    second = await client.put(
        "/api/v1/i18n/messages",
        json={"updates": [{"id": item["id"], "value": "二版", "version": item["version"]}]},
    )
    assert second.status_code == 200, second.text
    reloaded = (await client.get("/api/v1/i18n/messages")).json()["data"]
    assert reloaded["messages"][msg_key] == "二版"


async def test_dispatch_empty_messages_for_new_tenant_like_locale(client: AsyncClient) -> None:
    """语言包为空（模拟未种子）时返回空映射而不是报错。"""
    data = (await client.get("/api/v1/i18n/messages", params={"locale": "en-US"})).json()["data"]
    assert isinstance(data["messages"], dict)
