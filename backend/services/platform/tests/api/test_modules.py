"""模块注册只读接口测试（Kiwi 28 / 2163 / 2164）：清单分页 / 筛选 / 明细 / 404 / 字段护栏 / 启动校验 / 路由只读。"""

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from bms_core.application import service_lifespan as lifespan
from bms_core.core.concurrent import ConcurrentStableList, ConcurrentStableSet
from bms_core.core.exceptions import AuthError, CatalogError
from bms_core.oauth.token import TOKEN_AUDIENCE_SERVICE
from bms_core.oauth.verify import VerifiedToken, get_token_verifier
from bms_core.schemas.module import ModuleResponse
from bms_core.services.module_registry import SERVICE_CATALOG
from bms_core.testing.namespace import Namespace
from bms_platform import CONTRACT_VERSION
from bms_platform.main import ApplicationFactory
from tests_support.auth import auth_headers


def _expected_keys() -> ConcurrentStableList[str]:
    """静态声明清单的模块键（`SERVICE_CATALOG` 常量，不随库 / 进程状态变化）。

    共享库叠加下，运行时目录视图会含别的 worker 经注册通道登记的测试模块，**不能**当「期望全量」；
    接口契约只承诺「静态声明的模块全部在册、保持声明顺序」，故期望值取包内常量。

    Returns:
        ConcurrentStableList[str]: 期望的 `module_key` 顺序。
    """
    return ConcurrentStableList(module.module_key for module in SERVICE_CATALOG)


@pytest.mark.kiwi_id(28)
async def test_list_modules_contract() -> None:
    """GET /api/v1/modules 分页结构（种子清单为前缀）；status / group 筛选；POST/PUT/DELETE 405。"""
    app = ApplicationFactory().create(None)
    async with lifespan(app), AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        client.headers.update(auth_headers())
        resp = await client.get("/api/v1/modules")
        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 0
        data = body["data"]
        expected = [key for key in _expected_keys()]
        assert (data["page"], data["size"]) == (1, 20)
        assert len(data["list"]) == min(20, data["total"])
        assert data["total"] >= 1  # 同上：并发复位期间总数不作下限判据
        # 共享库叠加：别的 worker 可能刚经注册通道登记测试模块（且平台 conftest 每例复位重播种会
        # 让种子行拿到更大主键），插入序不再代表声明序——一律改集合口径（《测试规范》§4）。
        full = await client.get("/api/v1/modules", params={"size": 200})
        listed = [item["module_key"] for item in full.json()["data"]["list"]]
        assert len(listed) == len(set(listed))
        assert set(expected) <= set(listed)

        filtered = await client.get("/api/v1/modules", params={"status": "planned"})
        planned_rows = filtered.json()["data"]["list"]
        assert all(item["status"] == "planned" for item in planned_rows)
        planned_known = [record.module_key for record in SERVICE_CATALOG if record.status == "planned"]
        assert set(planned_known) <= {item["module_key"] for item in planned_rows}

        foundation = await client.get("/api/v1/modules", params={"group": "foundation"})
        foundation_rows = foundation.json()["data"]["list"]
        foundation_known = [record.module_key for record in SERVICE_CATALOG if record.service_group == "foundation"]
        assert all(item["service_group"] == "foundation" for item in foundation_rows)
        assert set(foundation_known) <= {item["module_key"] for item in foundation_rows}
        # 恒开通标记：**声明清单内的平台模块**恒 true（派生自基座常量，不落库）；测试登记的
        # 模块默认 group=foundation 且 tenant_base=False，不能一并断言（否则并行登记即误报）。
        assert all(item["tenant_base"] is True for item in foundation_rows if item["module_key"] in foundation_known)

        products = await client.get("/api/v1/modules", params={"group": "product", "status": "planned"})
        product_known = [
            record.module_key
            for record in SERVICE_CATALOG
            if record.service_group == "product" and record.status == "planned"
        ]
        product_rows = products.json()["data"]["list"]
        assert set(product_known) <= {item["module_key"] for item in product_rows}

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
    first_data = first.json()["data"]
    total = first_data["total"]
    assert len(first_data["list"]) == 5
    assert total >= len(expected)  # 共享库叠加：总数只判下限
    page_keys = [item["module_key"] for item in first_data["list"]]
    assert len(page_keys) == len(set(page_keys))

    last_page = -(-total // 5)  # 末页页码（向上取整）
    last = await client.get("/api/v1/modules", params={"page": last_page, "size": 5})
    last_data = last.json()["data"]
    # 末页条数按**该次响应自己的总数**推算（两次请求之间可能有并发登记）
    assert len(last_data["list"]) == min(5, last_data["total"] - (last_page - 1) * 5)

    full = await client.get("/api/v1/modules", params={"size": 200})
    keys = [item["module_key"] for item in full.json()["data"]["list"]]
    assert set(expected) <= set(keys)  # 声明清单全部在册（叠加场景不比顺序）

    sorted_by_id = await client.get("/api/v1/modules", params={"order_by": "id", "order": "desc", "size": 1})
    assert sorted_by_id.json()["data"]["list"][0]["module_key"] == keys[-1]

    ignored = await client.get("/api/v1/modules", params={"order_by": "module_key", "size": 1})
    assert ignored.json()["data"]["list"][0]["module_key"] == keys[0]

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
async def test_modules_tenant_base_flag_derived(client: AsyncClient) -> None:
    """目录出口派生恒开通标记：平台模块 true、未声明的产品模块 false（逐行下发，不落库）。"""
    planned = await client.get("/api/v1/modules", params={"group": "product", "status": "planned"})
    planned_rows = planned.json()["data"]["list"]
    assert {"pur", "pay", "sale", "wh", "sup", "cw"} <= {item["module_key"] for item in planned_rows}
    assert all(item["tenant_base"] is False for item in planned_rows)
    detail = await client.get("/api/v1/modules/sys")
    assert detail.json()["data"]["tenant_base"] is True


@pytest.mark.kiwi_id(2164)
def test_module_response_tenant_base_from_loaded_manifest() -> None:
    """已装载 `tenant_base = true` 的服务行：目录响应标记为 true（派生自装载视图，不读库）。"""
    from types import SimpleNamespace

    from bms_core.services.module_registry import ModuleRecord, register_service_records, reset_service_records
    from bms_platform.domains.platform_registry.api.modules import (
        _module_response,  # pyright: ignore[reportPrivateUsage]
    )

    record = ModuleRecord(
        module_key="demo",
        service_key="demo",
        name="演示服务",
        table_prefix="demo_",
        event_domain="demo",
        service_group="product",
        product_key="demo",
        tenant_base=True,
    )
    try:
        register_service_records((record,))
        assert _module_response(record).tenant_base is True
        plain = ModuleRecord(
            module_key="extra",
            name="其它服务",
            table_prefix="extra_",
            event_domain="extra",
            service_group="product",
            product_key="demo",
        )
        assert _module_response(plain).tenant_base is False
        # 库行不带该属性（`sys_module` 无此列）：缺省 false，按装载视图派生为 true
        row = SimpleNamespace(**{**record.__dict__, "tenant_base": False})
        assert _module_response(row).tenant_base is True
    finally:
        reset_service_records()


@pytest.mark.kiwi_id(2164)
async def test_list_modules_empty_catalog(client: AsyncClient, ns: Namespace) -> None:
    """按本用例唯一服务键过滤：分页 `total=0`（键由命名空间生成，库内无同键行）。"""
    missing_key = ns.code("no-such-service")
    response = await client.get("/api/v1/modules", params={"service_key": missing_key})
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["total"] == 0  # premise: own-data 过滤键带本用例命名空间前缀，他人不可能同键
    assert data["list"] == []  # premise: own-data 同上，空列表只说明该唯一键无行


@pytest.mark.kiwi_id(2164)
async def test_modules_snapshot_full_catalog(client: AsyncClient) -> None:
    """快照：全量清单（不分页），字段与明细同口径；种子清单位于最前。

    共享库叠加：别的 worker 可能刚登记测试模块（追加在末尾），故只断言种子清单为前缀，
    不写死「快照条数 == 登记清单条数」（《测试规范》§4 禁止整表口径）。
    """
    snapshot = await client.get("/api/v1/modules/snapshot")
    assert snapshot.status_code == 200
    data = snapshot.json()["data"]
    expected = [key for key in _expected_keys()]
    assert [item["module_key"] for item in data][: len(expected)] == expected
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
def _dual_verifier(service_app: FastAPI, monkeypatch: pytest.MonkeyPatch) -> None:  # pyright: ignore[reportUnusedFunction]
    """以替身顶替统一校验器（按受众返回服务 / 用户身份，避免真实外呼依赖）。

    必须用 `monkeypatch.setitem` 而不是直接写 `dependency_overrides[...]`：装配常驻后该字典是
    进程级共享状态，用例结束不卸载会让**后续文件**的所有请求都走替身校验器（只认字面量令牌），
    实测 `test_modules_snapshot` 5 条形如「真实令牌 → 401」。`monkeypatch` 退出自动还原。
    """
    monkeypatch.setitem(service_app.dependency_overrides, get_token_verifier, _DualVerifier)


@pytest.mark.kiwi_id(2302)
async def test_snapshot_readable_with_service_identity(_dual_verifier: None, client: AsyncClient) -> None:
    """双模鉴权（缺陷 #111）：服务身份直连快照 200 + 全量清单；用户令牌仍 200；无凭证 401。"""
    service = await client.get("/api/v1/modules/snapshot", headers={"Authorization": "Bearer identity"})
    assert service.status_code == 200
    expected = [key for key in _expected_keys()]
    keys = [item["module_key"] for item in service.json()["data"]]
    assert set(expected) <= set(keys)

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
