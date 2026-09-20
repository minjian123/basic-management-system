"""健康检查真实依赖集成用例（标记 integration；真实 Redis 随 04_02 执行）。"""

import os

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import get_settings
from app.main import ApplicationFactory

pytestmark = pytest.mark.integration


async def test_readyz_with_real_redis(monkeypatch: pytest.MonkeyPatch) -> None:
    """真实 Redis 下完整装配 `/readyz` 全就绪（未配置 BMS_TEST_REDIS_URL 时跳过）。"""
    url = os.environ.get("BMS_TEST_REDIS_URL")
    if not url:
        pytest.skip("未配置 BMS_TEST_REDIS_URL，跳过真实 Redis 集成用例")

    monkeypatch.setenv("BMS_REDIS__URL", url)
    monkeypatch.setenv("BMS_DATABASE__PLATFORM__URL", "sqlite+aiosqlite:///:memory:")
    get_settings.cache_clear()

    app = ApplicationFactory().create(None)
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client,
    ):
        resp = await client.get("/readyz")

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["checks"]["redis"] == {"ok": True, "error": None}
    assert body["checks"]["database"] == {"ok": True, "error": None}
