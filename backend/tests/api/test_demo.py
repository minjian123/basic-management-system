"""demo 示例模块接口测试：全量 CRUD 冒烟。"""

import pytest
from httpx import AsyncClient

API = "/api/v1/demos"


@pytest.mark.kiwi_id(3)
async def test_create_demo_returns_created(client: AsyncClient) -> None:
    """创建 demo 返回自增 ID 与名称。"""
    resp = await client.post(API, json={"name": "示例 A"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["id"] == 1
    assert body["data"]["name"] == "示例 A"


@pytest.mark.kiwi_id(4)
async def test_list_demos_returns_items(client: AsyncClient) -> None:
    """列表初始为空，创建后包含该项。"""
    assert (await client.get(API)).json()["data"] == []
    await client.post(API, json={"name": "示例 B"})
    body = (await client.get(API)).json()
    assert [item["name"] for item in body["data"]] == ["示例 B"]


@pytest.mark.kiwi_id(5)
async def test_get_demo_by_id(client: AsyncClient) -> None:
    """按 ID 查询返回创建时一致的记录。"""
    created = (await client.post(API, json={"name": "示例 C"})).json()["data"]
    resp = await client.get(f"{API}/{created['id']}")
    assert resp.status_code == 200
    assert resp.json()["data"] == created


@pytest.mark.kiwi_id(6)
async def test_update_demo_name(client: AsyncClient) -> None:
    """更新名称后再查一致。"""
    created = (await client.post(API, json={"name": "旧名"})).json()["data"]
    resp = await client.put(f"{API}/{created['id']}", json={"name": "新名"})
    assert resp.status_code == 200
    assert resp.json()["data"]["name"] == "新名"
    again = (await client.get(f"{API}/{created['id']}")).json()["data"]
    assert again["name"] == "新名"


@pytest.mark.kiwi_id(7)
async def test_delete_demo(client: AsyncClient) -> None:
    """删除后查询返回 404。"""
    created = (await client.post(API, json={"name": "待删除"})).json()["data"]
    assert (await client.delete(f"{API}/{created['id']}")).status_code == 200
    assert (await client.get(f"{API}/{created['id']}")).status_code == 404


@pytest.mark.kiwi_id(8)
async def test_get_missing_demo_returns_404(client: AsyncClient) -> None:
    """不存在的 ID 返回 404（仅断言状态码，body 结构随 02-3 统一）。"""
    resp = await client.get(f"{API}/9999")
    assert resp.status_code == 404


@pytest.mark.kiwi_id(9)
async def test_update_missing_demo_returns_404(client: AsyncClient) -> None:
    """更新不存在的 ID 返回 404（失败分支）。"""
    resp = await client.put(f"{API}/9999", json={"name": "不存在"})
    assert resp.status_code == 404


@pytest.mark.kiwi_id(10)
async def test_delete_missing_demo_returns_404(client: AsyncClient) -> None:
    """删除不存在的 ID 返回 404（失败分支）。"""
    resp = await client.delete(f"{API}/9999")
    assert resp.status_code == 404
