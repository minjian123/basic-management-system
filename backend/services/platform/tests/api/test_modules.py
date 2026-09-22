"""模块注册只读接口测试（Kiwi 28 / 2163）：清单 / 筛选 / 无写接口 / 启动校验 / 路由只读护栏。"""

import pytest
from httpx import ASGITransport, AsyncClient

from bms_core.application import service_lifespan as lifespan
from bms_core.core.exceptions import CatalogError
from bms_platform import CONTRACT_VERSION
from bms_platform.main import ApplicationFactory


@pytest.mark.kiwi_id(28)
async def test_list_modules_contract() -> None:
    """GET /api/v1/modules 返回服务目录 16 行；?status 筛选；POST/PUT/DELETE 405。"""
    app = ApplicationFactory().create(None)
    async with lifespan(app), AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/v1/modules")
        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 0
        assert [item["module_key"] for item in body["data"]] == [
            "sys",
            "identity",
            "tenant",
            "org",
            "file",
            "notification",
            "search",
            "ai",
            "rpt",
            "wf",
            "pur",
            "pay",
            "sale",
            "wh",
            "sup",
            "cw",
        ]

        filtered = await client.get("/api/v1/modules", params={"status": "planned"})
        assert [item["module_key"] for item in filtered.json()["data"]] == [
            "wf",
            "pur",
            "pay",
            "sale",
            "wh",
            "sup",
            "cw",
        ]

        created = await client.post("/api/v1/modules", json={"module_key": "pur"})
        assert created.status_code == 405
        updated = await client.put("/api/v1/modules", json={"module_key": "pur"})
        assert updated.status_code == 405
        removed = await client.delete("/api/v1/modules")
        assert removed.status_code == 405


@pytest.mark.kiwi_id(28)
async def test_startup_validation_aborts_on_conflict(monkeypatch: pytest.MonkeyPatch) -> None:
    """启动校验：冲突时中止启动（统一异常 `CatalogError`）。"""
    app = ApplicationFactory().create(None)
    monkeypatch.setattr(app.state.module_registry, "validate", lambda: ["table_prefix 重复：pur_"])
    with pytest.raises(CatalogError, match="服务目录校验失败"):
        async with lifespan(app):
            pass


@pytest.mark.kiwi_id(2163)
async def test_startup_validation_passes_for_platform_seed() -> None:
    """启动校验：服务目录清单 + 接库校验通过；身份携带服务自报契约版本。"""
    app = ApplicationFactory().create(None)
    assert app.state.service_identity.contract_version == CONTRACT_VERSION
    async with lifespan(app):
        assert app.state.module_registry.validate() == []


@pytest.mark.kiwi_id(2163)
async def test_modules_routes_get_only() -> None:
    """只读边界：服务目录路由（含后续 03_03 明细路由）仅 GET（以 OpenAPI 契约为准）。"""
    app = ApplicationFactory().create(None)
    operations: set[str] = set()
    for path, item in app.openapi()["paths"].items():
        if path.startswith("/api/v1/modules"):
            operations |= set(item)
    assert operations == {"get"}
