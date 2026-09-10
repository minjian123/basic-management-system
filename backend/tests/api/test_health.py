"""健康检查 /healthz 冒烟。"""

import pytest
from httpx import AsyncClient


@pytest.mark.kiwi_id(2)
async def test_healthz_returns_ok(client: AsyncClient) -> None:
    """GET /healthz 返回 {"status":"ok"}。"""
    resp = await client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
