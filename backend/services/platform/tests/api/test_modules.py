"""模块注册只读接口测试（Kiwi 28）：清单 / 筛选 / 无写接口 / 启动校验。"""

import pytest
from httpx import ASGITransport, AsyncClient

from bms_platform.main import ApplicationFactory, lifespan


@pytest.mark.kiwi_id(28)
async def test_list_modules_contract() -> None:
    """GET /api/v1/modules 返回平台域 4 行；?status 筛选；POST 404。"""
    app = ApplicationFactory().create(None)
    async with lifespan(app), AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/v1/modules")
        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 0
        assert [item["module_key"] for item in body["data"]] == ["sys", "wf", "rpt", "ai"]

        filtered = await client.get("/api/v1/modules", params={"status": "planned"})
        assert filtered.json()["data"] == []

        created = await client.post("/api/v1/modules", json={"module_key": "pur"})
        assert created.status_code == 405
        updated = await client.put("/api/v1/modules", json={"module_key": "pur"})
        assert updated.status_code == 405
        removed = await client.delete("/api/v1/modules")
        assert removed.status_code == 405


@pytest.mark.kiwi_id(28)
async def test_startup_validation_aborts_on_conflict(monkeypatch: pytest.MonkeyPatch) -> None:
    """启动校验：冲突时中止启动。"""
    app = ApplicationFactory().create(None)
    monkeypatch.setattr(app.state.module_registry, "validate", lambda: ["table_prefix 重复：pur_"])
    with pytest.raises(RuntimeError, match="模块注册校验失败"):
        async with lifespan(app):
            pass


@pytest.mark.kiwi_id(28)
async def test_startup_validation_passes_for_platform_seed() -> None:
    """启动校验：平台域占位清单恒通过。"""
    app = ApplicationFactory().create(None)
    async with lifespan(app):
        assert app.state.module_registry.validate() == []
