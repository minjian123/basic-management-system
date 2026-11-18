"""帮助分类管理面：增删改 / 拒删 / 级联 / 环 / 深度 / 同名（Kiwi 2529）。"""

from __future__ import annotations

from typing import Any, cast

import pytest
import pytest_asyncio
from httpx import AsyncClient

from bms_core.testing.namespace import Namespace
from tests_support.help import seed_article, tenant_url

from ._support import prepare

pytestmark = pytest.mark.kiwi_id(2529)

_CATEGORIES = "/api/v1/help/manage/categories"


def _body(response: Any) -> Any:
    """取响应体。"""
    return response.json()


@pytest_asyncio.fixture(autouse=True)
async def prepared(tenant_db: str) -> None:
    """准备权限主体与帮助表。

    Args:
        tenant_db: 共享测试租户库连接串。
    """
    assert tenant_db
    await prepare()


async def _create(client: AsyncClient, name: str, **extra: object) -> Any:
    """新建分类并返回响应体。"""
    return _body(await client.post(_CATEGORIES, json={"name": name, **extra}))


def _find(nodes: object, category_id: int) -> Any:
    """在树中按主键找节点。"""
    for node in cast("list[Any]", nodes):
        if int(node["id"]) == category_id:
            return node
        found = _find(node["children"], category_id)
        if found is not None:
            return found
    return None


async def test_create_update_list_category(client: AsyncClient, ns: Namespace) -> None:
    """新建 → 编辑 → 列表（含子树计数）。"""
    root = await _create(client, f"{ns.prefix}_cat_root", sort=10)
    assert root["code"] == 0
    root_id = int(root["data"]["id"])

    child = await _create(client, f"{ns.prefix}_cat_child", parent_id=root_id, sort=20)
    assert child["code"] == 0
    child_id = int(child["data"]["id"])

    updated = _body(
        await client.put(
            f"{_CATEGORIES}/{child_id}",
            json={"name": f"{ns.prefix}_cat_child2", "status": "disabled", "sort": 99},
        )
    )
    assert updated["code"] == 0
    assert updated["data"]["name"] == f"{ns.prefix}_cat_child2"
    assert updated["data"]["status"] == "disabled"
    assert updated["data"]["sort"] == 99

    moved = _body(await client.put(f"{_CATEGORIES}/{root_id}", json={"parent_id": 0, "sort": 11}))
    assert moved["code"] == 0
    assert moved["data"]["sort"] == 11

    tree = _body(await client.get(_CATEGORIES))["data"]
    node = _find(tree["items"], root_id)
    assert node is not None
    assert len(node["children"]) == 1


async def test_delete_requires_empty_or_cascade(client: AsyncClient, ns: Namespace) -> None:
    """默认拒删并给计数；cascade 级联下架文章后删除。"""
    root = await _create(client, f"{ns.prefix}_del_root")
    root_id = int(root["data"]["id"])
    article_id = await seed_article(
        tenant_url(),
        category_id=root_id,
        title=f"{ns.prefix}_del_article",
        status="published",
    )
    await seed_article(
        tenant_url(),
        category_id=root_id,
        title=f"{ns.prefix}_del_offline",
        status="offline",
    )

    rejected = _body(await client.delete(f"{_CATEGORIES}/{root_id}"))
    assert rejected["code"] == 40015
    assert rejected["data"]["article_count"] == 2

    deleted = _body(await client.delete(f"{_CATEGORIES}/{root_id}", params={"cascade": True}))
    assert deleted["code"] == 0
    assert deleted["data"]["offlined_articles"] == 1

    detail = _body(await client.get(f"/api/v1/help/manage/articles/{article_id}"))
    assert detail["code"] == 0
    assert detail["data"]["status"] == "offline"


async def test_delete_rejects_child_categories(client: AsyncClient, ns: Namespace) -> None:
    """存在子分类时默认拒删（child_count 正确）。"""
    root = await _create(client, f"{ns.prefix}_child_root")
    root_id = int(root["data"]["id"])
    await _create(client, f"{ns.prefix}_child_sub", parent_id=root_id)
    rejected = _body(await client.delete(f"{_CATEGORIES}/{root_id}"))
    assert rejected["code"] == 40015
    assert rejected["data"]["child_count"] == 1
    cascaded = _body(await client.delete(f"{_CATEGORIES}/{root_id}", params={"cascade": True}))
    assert cascaded["code"] == 0
    assert cascaded["data"]["deleted_categories"] == 2
    assert cascaded["data"]["offlined_articles"] == 0


async def test_category_validation(client: AsyncClient, ns: Namespace) -> None:
    """同级同名 / 父级不存在 / 成环 / 深度超限（40023 / 40014）。"""
    name = f"{ns.prefix}_dup"
    first = await _create(client, name)
    assert first["code"] == 0
    duplicated = await _create(client, name)
    assert duplicated["code"] == 40023

    missing_parent = await _create(client, f"{ns.prefix}_missing", parent_id=999999)
    assert missing_parent["code"] == 40014

    root = await _create(client, f"{ns.prefix}_cycle_root")
    root_id = int(root["data"]["id"])
    child = await _create(client, f"{ns.prefix}_cycle_child", parent_id=root_id)
    child_id = int(child["data"]["id"])
    cycle = _body(await client.put(f"{_CATEGORIES}/{root_id}", json={"parent_id": child_id}))
    assert cycle["code"] == 40023

    parent_id = 0
    last_id = 0
    for index in range(5):
        node = await _create(client, f"{ns.prefix}_depth_{index}", parent_id=parent_id)
        assert node["code"] == 0
        last_id = int(node["data"]["id"])
        parent_id = last_id
    too_deep = await _create(client, f"{ns.prefix}_depth_5", parent_id=last_id)
    assert too_deep["code"] == 40023


async def test_category_not_found(client: AsyncClient) -> None:
    """编辑 / 删除不存在的分类返回 40014。"""
    assert (await client.put(f"{_CATEGORIES}/999999", json={"name": "x"})).json()["code"] == 40014
    assert (await client.delete(f"{_CATEGORIES}/999999")).json()["code"] == 40014


async def test_category_status_and_self_parent_rejected(client: AsyncClient, ns: Namespace) -> None:
    """分类状态非法 10001；上级指向自身 40023。"""
    bad_status = await _create(client, f"{ns.prefix}_bad_status", status="paused")
    assert bad_status["code"] == 10001
    node = await _create(client, f"{ns.prefix}_self_parent")
    node_id = int(node["data"]["id"])
    assert (await client.put(f"{_CATEGORIES}/{node_id}", json={"status": "paused"})).json()["code"] == 10001
    self_parent = _body(await client.put(f"{_CATEGORIES}/{node_id}", json={"parent_id": node_id}))
    assert self_parent["code"] == 40023
