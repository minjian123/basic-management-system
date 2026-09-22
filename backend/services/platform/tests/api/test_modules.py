"""模块注册只读接口测试（Kiwi 28 / 2163 / 2164）：清单分页 / 筛选 / 明细 / 404 / 字段护栏 / 启动校验 / 路由只读。"""

from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from bms_core.application import service_lifespan as lifespan
from bms_core.core.config import get_settings
from bms_core.core.exceptions import CatalogError
from bms_core.schemas.module import ModuleResponse
from bms_platform import CONTRACT_VERSION
from bms_platform.main import ApplicationFactory

_EXPECTED_KEYS = [
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


@pytest.mark.kiwi_id(28)
async def test_list_modules_contract() -> None:
    """GET /api/v1/modules 分页结构（16 行）；status / group 筛选；POST/PUT/DELETE 405。"""
    app = ApplicationFactory().create(None)
    async with lifespan(app), AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/v1/modules")
        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 0
        data = body["data"]
        assert (data["total"], data["page"], data["size"]) == (16, 1, 20)
        assert [item["module_key"] for item in data["list"]] == _EXPECTED_KEYS

        filtered = await client.get("/api/v1/modules", params={"status": "planned"})
        assert [item["module_key"] for item in filtered.json()["data"]["list"]] == [
            "wf",
            "pur",
            "pay",
            "sale",
            "wh",
            "sup",
            "cw",
        ]

        foundation = await client.get("/api/v1/modules", params={"group": "foundation"})
        assert [item["module_key"] for item in foundation.json()["data"]["list"]] == ["sys", "identity", "tenant"]

        products = await client.get("/api/v1/modules", params={"group": "product", "status": "planned"})
        assert products.json()["data"]["total"] == 6

        created = await client.post("/api/v1/modules", json={"module_key": "pur"})
        assert created.status_code == 405
        updated = await client.put("/api/v1/modules", json={"module_key": "pur"})
        assert updated.status_code == 405
        removed = await client.delete("/api/v1/modules")
        assert removed.status_code == 405


@pytest.mark.kiwi_id(2164)
async def test_list_modules_pagination_and_sort(client: AsyncClient) -> None:
    """分页生效（size / 末页）；排序白名单（命中排序、非法字段忽略回落 id 升序）；页码限深 10001。"""
    first = await client.get("/api/v1/modules", params={"page": 1, "size": 5})
    assert len(first.json()["data"]["list"]) == 5
    assert first.json()["data"]["total"] == 16

    last = await client.get("/api/v1/modules", params={"page": 4, "size": 5})
    assert [item["module_key"] for item in last.json()["data"]["list"]] == ["cw"]

    sorted_by_id = await client.get("/api/v1/modules", params={"order_by": "id", "order": "desc"})
    assert sorted_by_id.json()["data"]["list"][0]["module_key"] == "cw"

    ignored = await client.get("/api/v1/modules", params={"order_by": "module_key"})
    assert ignored.json()["data"]["list"][0]["module_key"] == "sys"

    too_deep = await client.get("/api/v1/modules", params={"page": 101})
    assert too_deep.status_code == 200
    assert too_deep.json()["code"] == 10001


@pytest.mark.kiwi_id(2164)
async def test_get_module_detail_and_not_found(client: AsyncClient) -> None:
    """明细：service_key 命中 / module_key 回退 / 未登记 404 + 10002 + 统一响应体。"""
    by_service = await client.get("/api/v1/modules/platform")
    assert by_service.status_code == 200
    detail = by_service.json()["data"]
    assert detail["module_key"] == "sys"
    assert detail["service_key"] == "platform"
    assert detail["name"] == "平台地基与配置服务"
    assert detail["contract_version"] == "0.1.0"

    fallback = await client.get("/api/v1/modules/pur")
    assert fallback.status_code == 200
    product = fallback.json()["data"]
    assert product["module_key"] == "pur"
    assert product["service_key"] is None
    assert product["product_key"] == "biz"

    missing = await client.get("/api/v1/modules/ghost")
    assert missing.status_code == 404
    body = missing.json()
    assert body["code"] == 10002
    assert body["data"] is None
    assert "服务未登记" in body["message"]


@pytest.mark.kiwi_id(2164)
async def test_modules_response_fields_whitelist(client: AsyncClient) -> None:
    """响应字段集严格等于 `ModuleResponse`（不含密钥 / 敏感项）。"""
    expected = set(ModuleResponse.model_fields)
    listed = await client.get("/api/v1/modules")
    assert set(listed.json()["data"]["list"][0]) == expected
    detail = await client.get("/api/v1/modules/platform")
    assert set(detail.json()["data"]) == expected
    assert not expected & {"options", "secret", "password", "token", "config"}


@pytest.mark.kiwi_id(2164)
async def test_list_modules_empty_catalog(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """未播种空库：清单空数组 + total=0；明细 404（与启动空目录容错口径一致）。"""
    monkeypatch.setenv("BMS_DATABASE__PLATFORM__URL", f"sqlite+aiosqlite:///{tmp_path / 'empty.db'}")
    get_settings.cache_clear()
    app = ApplicationFactory().create(None)
    async with lifespan(app), AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        listed = await client.get("/api/v1/modules")
        assert listed.json()["data"] == {"list": [], "total": 0, "page": 1, "size": 20}

        missing = await client.get("/api/v1/modules/pur")
        assert missing.status_code == 404
        assert missing.json()["code"] == 10002


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
    """只读边界：服务目录路由（含 03_03 明细路由）仅 GET（以 OpenAPI 契约为准）。"""
    app = ApplicationFactory().create(None)
    operations: set[str] = set()
    for path, item in app.openapi()["paths"].items():
        if path.startswith("/api/v1/modules"):
            operations |= set(item)
    assert operations == {"get"}
