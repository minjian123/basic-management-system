"""应用工厂冒烟：根路由与应用信息、/healthz 存活。"""

import pytest
from httpx import AsyncClient


@pytest.mark.kiwi_id(1)
async def test_root_returns_app_info(client: AsyncClient) -> None:
    """GET / 返回统一响应结构与应用名/版本。"""
    resp = await client.get("/")
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 0
    assert body["message"] == "ok"
    assert body["data"]["name"] == "BMS 基础管理系统"
    assert body["data"]["version"]


@pytest.mark.kiwi_id(2)
async def test_healthz_returns_ok(client: AsyncClient) -> None:
    """GET /healthz 返回 {"status":"ok"}。"""
    resp = await client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
