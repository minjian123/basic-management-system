"""模块注册只读接口测试（Kiwi 28 / 2163 / 2164）：清单分页 / 筛选 / 明细 / 404 / 字段护栏 / 启动校验 / 路由只读。"""

from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from bms_core.application import service_lifespan as lifespan
from bms_core.core.concurrent import ConcurrentStableList, ConcurrentStableSet
from bms_core.core.config import get_settings
from bms_core.core.exceptions import AuthError, CatalogError
from bms_core.oauth.token import TOKEN_AUDIENCE_SERVICE
from bms_core.oauth.verify import VerifiedToken, get_token_verifier
from bms_core.schemas.module import ModuleResponse
from bms_core.services.module_registry import service_catalog_view
from bms_platform import CONTRACT_VERSION
from bms_platform.main import ApplicationFactory
from tests_support.auth import auth_headers


def _expected_keys() -> ConcurrentStableList[str]:
    """种子库登记键（与播种同源：平台清单 + 已装载产品清单，插入序）。

    产品登记清单随环境装载（本地工作区装载产品仓自持清单，CI 不装载），故不写死字面清单——
    断言「接口返回与登记清单一致」，两种环境均成立。04_05 起平台 conftest 以**会话级固定清单**
    在用例间复位并幂等重载注入表，使「播种集合 ≡ 目录视图」不随并行 / 执行顺序漂移。

    Returns:
        ConcurrentStableList[str]: 期望的 `module_key` 顺序。
    """
    return ConcurrentStableList(module.module_key for module in service_catalog_view())


@pytest.mark.kiwi_id(28)
async def test_list_modules_contract() -> None:
    """GET /api/v1/modules 分页结构（与登记清单同量）；status / group 筛选；POST/PUT/DELETE 405。"""
    app = ApplicationFactory().create(None)
    async with lifespan(app), AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        client.headers.update(auth_headers())
        resp = await client.get("/api/v1/modules")
        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 0
        data = body["data"]
        expected = [key for key in _expected_keys()]
        assert (data["total"], data["page"], data["size"]) == (len(expected), 1, 20)
        assert [item["module_key"] for item in data["list"]] == expected

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
        assert [item["module_key"] for item in foundation.json()["data"]["list"]] == [
            "sys",
            "identity",
            "tenant",
            "txn",
        ]

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
    expected = [key for key in _expected_keys()]
    first = await client.get("/api/v1/modules", params={"page": 1, "size": 5})
    assert len(first.json()["data"]["list"]) == 5
    assert first.json()["data"]["total"] == len(expected)

    last_page = -(-len(expected) // 5)  # 末页页码（向上取整）
    last = await client.get("/api/v1/modules", params={"page": last_page, "size": 5})
    assert [item["module_key"] for item in last.json()["data"]["list"]] == expected[(last_page - 1) * 5 :]

    sorted_by_id = await client.get("/api/v1/modules", params={"order_by": "id", "order": "desc"})
    assert sorted_by_id.json()["data"]["list"][0]["module_key"] == expected[-1]

    ignored = await client.get("/api/v1/modules", params={"order_by": "module_key"})
    assert ignored.json()["data"]["list"][0]["module_key"] == expected[0]

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
    # 02_03 返工：platform 公开契约因 `sys_form` 多对多升 0.2.0；02_14：字典 ids 子集改名升 0.3.0
    assert detail["contract_version"] == "0.3.0"

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
        client.headers.update(auth_headers())
        listed = await client.get("/api/v1/modules")
        assert listed.json()["data"] == {"list": [], "total": 0, "page": 1, "size": 20}

        missing = await client.get("/api/v1/modules/pur")
        assert missing.status_code == 404
        assert missing.json()["code"] == 10002


@pytest.mark.kiwi_id(2164)
async def test_modules_snapshot_full_catalog(client: AsyncClient) -> None:
    """快照：全量清单（不分页），字段与明细同口径、数量与清单总数一致。"""
    snapshot = await client.get("/api/v1/modules/snapshot")
    assert snapshot.status_code == 200
    data = snapshot.json()["data"]
    assert [item["module_key"] for item in data] == _expected_keys()
    assert set(data[0]) == set(ModuleResponse.model_fields)
    assert data[0]["service_key"] == "platform"


class _DualVerifier:
    """按受众分支的校验器替身（服务身份 / 用户身份；其余令牌拒）。"""

    async def verify(self, token: str, *, audience: str) -> VerifiedToken:
        """按令牌串与受众返回身份声明。

        Args:
            token: 令牌串。
            audience: 期望受众。

        Returns:
            VerifiedToken: 身份声明。

        Raises:
            AuthError: 未知令牌（20001 / 401）。
        """
        if audience == TOKEN_AUDIENCE_SERVICE:
            if token in {"identity", "tenant"}:
                return VerifiedToken(subject=token, service=token, token_type="service")
            if token == "gateway":
                return VerifiedToken(subject="gateway", service="gateway", token_type="service")
            raise AuthError("invalid")
        if token == "user":
            return VerifiedToken(subject="1001", token_id="1001", token_type="access")
        raise AuthError("invalid")


@pytest.fixture
def _dual_verifier(service_app: FastAPI) -> None:  # pyright: ignore[reportUnusedFunction]
    """以替身顶替统一校验器（按受众返回服务 / 用户身份，避免真实外呼依赖）。"""
    service_app.dependency_overrides[get_token_verifier] = _DualVerifier


@pytest.mark.kiwi_id(2302)
async def test_snapshot_readable_with_service_identity(_dual_verifier: None, client: AsyncClient) -> None:
    """双模鉴权（缺陷 #111）：服务身份直连快照 200 + 全量清单；用户令牌仍 200；无凭证 401。"""
    service = await client.get("/api/v1/modules/snapshot", headers={"Authorization": "Bearer identity"})
    assert service.status_code == 200
    assert [item["module_key"] for item in service.json()["data"]] == _expected_keys()

    user = await client.get("/api/v1/modules/snapshot", headers={"Authorization": "Bearer user"})
    assert user.status_code == 200

    anonymous = await client.get("/api/v1/modules/snapshot", headers={"Authorization": ""})
    assert anonymous.status_code == 401


@pytest.mark.kiwi_id(2302)
async def test_snapshot_rejects_gateway_ticket_without_user(_dual_verifier: None, client: AsyncClient) -> None:
    """仅持网关代发 `sub=gateway` 票据（无用户凭证）→ 401（回落登录态路径，不绕过会话校验）。"""
    resp = await client.get("/api/v1/modules/snapshot", headers={"Authorization": "Bearer gateway"})
    assert resp.status_code == 401


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
    operations: ConcurrentStableSet[str] = ConcurrentStableSet()
    for path, item in app.openapi()["paths"].items():
        if path.startswith("/api/v1/modules"):
            operations.update(set(item))
    assert operations == {"get"}
