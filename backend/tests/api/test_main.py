"""根路由与应用信息冒烟。"""

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
