"""跨服务事务管理器服务启动冒烟（脚手架生成）。"""

from httpx import ASGITransport, AsyncClient

from bms_txn import SERVICE_NAME
from bms_txn.main import ApplicationFactory


async def test_service_boots_and_exposes_probes() -> None:
    """应用可构造；`/healthz` 返回存活状态与服务身份；`/readyz` 就绪（最小服务无依赖检查）。"""
    app = ApplicationFactory().create(None)
    assert "BMS" in app.title
    assert "跨服务事务管理器" in app.title
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client,
    ):
        healthz = await client.get("/healthz")
        readyz = await client.get("/readyz")
    assert healthz.status_code == 200
    assert healthz.json()["service"] == SERVICE_NAME
    assert readyz.status_code == 200
    assert readyz.json()["checks"] == {}
