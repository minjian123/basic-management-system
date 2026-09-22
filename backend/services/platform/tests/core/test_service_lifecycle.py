"""平台服务生命周期测试：服务身份 / 停机摘流 / 资源释放（Kiwi 1205）。"""

import pytest
from httpx import ASGITransport, AsyncClient

from bms_platform import SERVICE_NAME, __version__
from bms_platform.main import ApplicationFactory


@pytest.mark.kiwi_id(1205)
async def test_app_exposes_identity_across_probes() -> None:
    """平台应用身份就位：`/healthz` 与 `/readyz` 均携带 `service` / `version`。"""
    app = ApplicationFactory().create(None)
    identity = app.state.service_identity
    assert identity.name == SERVICE_NAME
    assert identity.version == __version__

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        healthz = await client.get("/healthz")
        readyz = await client.get("/readyz")

    assert healthz.status_code == 200
    assert healthz.json() == {"status": "ok", "service": SERVICE_NAME, "version": __version__}
    # 启动前（startup_complete=False）：503 空 checks，仍携带身份
    assert readyz.status_code == 503
    body = readyz.json()
    assert body["status"] == "down"
    assert body["checks"] == {}
    assert body["service"] == SERVICE_NAME
    assert body["version"] == __version__


@pytest.mark.kiwi_id(1205)
async def test_start_drain_makes_readyz_503_and_lifespan_releases() -> None:
    """停机摘流：`/readyz` 立即 503；lifespan 退出取消就绪并释放资源。"""
    app = ApplicationFactory().create(None)
    async with app.router.lifespan_context(app):
        runtime = app.state.service_runtime
        assert runtime.draining is False
        runtime.start_drain()
        assert runtime.draining is True

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/readyz")

        assert resp.status_code == 503
        body = resp.json()
        assert body["status"] == "down"
        assert body["checks"] == {}
        assert body["service"] == SERVICE_NAME

    assert app.state.startup_complete is False
