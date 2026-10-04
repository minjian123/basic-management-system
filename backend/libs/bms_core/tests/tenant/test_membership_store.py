"""关系数据源（契约 / 注册表 / 远端实现）与租户自助真实实现测试（11_01）。

覆盖：注册表与装配（空名 / 未登记 / 自动选源）、远端实现的读写与失败分支、
`DbTenantSelfService` 的读路径自愈 / 越权校验 / 无主体回落 / 品牌与工厂。
"""

import json
from types import SimpleNamespace
from typing import cast

import pytest
from fastapi import FastAPI

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.config import Settings
from bms_core.core.exceptions import (
    ConfigError,
    MultipleActiveTenantsError,
    ServiceUnavailableError,
    TenantAccessDeniedError,
    TenantNotFoundError,
)
from bms_core.db.registry import EngineRegistry
from bms_core.db.tenant import TenantContext
from bms_core.servicecall.base import BaseServiceClient, ServiceRequest, ServiceResponse
from bms_core.tenant.base import TENANT_MEMBERSHIP_SELF_HEAL_SOURCE, TenantBrand
from bms_core.tenant.db import DbTenantSelfService, DbTenantSelfServiceFactory
from bms_core.tenant.membership import (
    LOCAL_TENANT_MEMBERSHIP_STORE,
    REMOTE_TENANT_MEMBERSHIP_STORE,
    TENANT_MEMBERSHIP_INTERNAL_PATH,
    TenantMembershipListResponse,
    TenantMembershipTarget,
    build_tenant_membership_store,
    register_tenant_membership_store,
    registered_tenant_membership_stores,
)
from bms_core.tenant.membership_remote import RemoteTenantMembershipStore, register_remote_tenant_membership_store

DEMO_ID = 1001
ACME_ID = 2002
_CODE_IDS: ConcurrentStableDict[str, int] = ConcurrentStableDict({"demo": DEMO_ID, "acme": ACME_ID})
"""替身租户编码 → 主键映射。"""

_ID_CODES: ConcurrentStableDict[int, str] = ConcurrentStableDict({DEMO_ID: "demo", ACME_ID: "acme"})
"""替身租户主键 → 编码映射。"""

_TEST_STORE = "test-local"
"""本用例专用的数据源登记名（不占用 `local` 名位，避免跨模块污染）。"""


def _settings(service: str) -> Settings:
    """构造仅含 `app.service` 的配置替身。

    Args:
        service: 服务标识。

    Returns:
        Settings: 配置替身。
    """
    return cast("Settings", SimpleNamespace(app=SimpleNamespace(service=service)))


class _FakeClient(BaseServiceClient):
    """服务客户端替身：按预设响应返回，记录调用请求。"""

    def __init__(self, response: ServiceResponse) -> None:
        """初始化。

        Args:
            response: 恒定返回的响应。
        """
        self.response = response
        self.requests: ConcurrentStableList[ServiceRequest] = ConcurrentStableList()

    async def call(self, request: ServiceRequest) -> ServiceResponse:
        """记录请求并返回预设响应。

        Args:
            request: 调用请求。

        Returns:
            ServiceResponse: 预设响应。
        """
        self.requests.add(request)
        return self.response


def _response(text: str, *, status: int = 200) -> ServiceResponse:
    """构造响应（JSON 文本体）。

    Args:
        text: JSON 文本。
        status: 状态码。

    Returns:
        ServiceResponse: 调用响应。
    """
    return ServiceResponse(status_code=status, content=text.encode())


def _targets_payload(*codes: str) -> str:
    """构造内部端点响应 JSON 文本。

    Args:
        *codes: 目标租户编码（`demo` / `acme`）。

    Returns:
        str: 统一响应 JSON 文本。
    """
    mapping = _CODE_IDS
    targets = [
        {
            "tenant_id": mapping[code],
            "code": code,
            "name": code,
            "domain": None,
            "source": "sso_jit",
            "status": "active",
        }
        for code in codes
    ]
    return json.dumps({"data": {"targets": targets}})


@pytest.mark.parametrize("method", ["list", "ensure", "revoke", "revoke_all"])
async def test_remote_store_calls_internal_endpoint(method: str) -> None:
    """远端实现：读写经内部端点（路径 / 方法 / 租户作用域）。"""
    client = _FakeClient(_response(_targets_payload("demo")))
    store = RemoteTenantMembershipStore(client=client)

    if method == "list":
        targets = await store.list_targets(tenant_id=DEMO_ID, user_id=7)
        assert [item.code for item in targets] == ["demo"]
        assert client.requests[0].method == "GET"
        assert client.requests[0].query is not None
        assert "include_disabled" not in client.requests[0].query
        await store.list_targets(tenant_id=DEMO_ID, user_id=7, include_disabled=True)
        assert client.requests[1].query is not None
        assert client.requests[1].query["include_disabled"] == "true"
    elif method == "ensure":
        target = await store.ensure(tenant_id=DEMO_ID, user_id=7, target_tenant_id=DEMO_ID, source="sso_jit")
        assert target.tenant_id == DEMO_ID
        assert client.requests[0].method == "POST"
        assert client.requests[0].json_body is not None
        assert client.requests[0].json_body["owner_tenant_id"] == DEMO_ID
    elif method == "revoke":
        await store.revoke(tenant_id=DEMO_ID, user_id=7, target_tenant_id=DEMO_ID)
        assert client.requests[0].method == "DELETE"
        assert client.requests[0].query is not None
        assert client.requests[0].query["target_tenant_id"] == str(DEMO_ID)
    else:
        await store.revoke_all(tenant_id=DEMO_ID, user_id=7)
        assert client.requests[0].method == "DELETE"
        assert client.requests[0].query is not None
        assert "target_tenant_id" not in client.requests[0].query

    assert client.requests[0].path == TENANT_MEMBERSHIP_INTERNAL_PATH
    assert client.requests[0].tenant_id == str(DEMO_ID)


async def test_remote_store_failure_branches() -> None:
    """远端实现：非 2xx / 缺 data / 缺 targets / 条目非法 / 目标缺失均归一为服务不可用。"""
    failed = RemoteTenantMembershipStore(client=_FakeClient(_response("{}", status=503)))
    with pytest.raises(ServiceUnavailableError):
        await failed.list_targets(tenant_id=DEMO_ID, user_id=7)

    no_data = RemoteTenantMembershipStore(client=_FakeClient(_response("{}")))
    with pytest.raises(ServiceUnavailableError):
        await no_data.list_targets(tenant_id=DEMO_ID, user_id=7)

    no_targets = RemoteTenantMembershipStore(client=_FakeClient(_response('{"data": {}}')))
    with pytest.raises(ServiceUnavailableError):
        await no_targets.list_targets(tenant_id=DEMO_ID, user_id=7)

    bad_item = RemoteTenantMembershipStore(client=_FakeClient(_response('{"data": {"targets": ["x"]}}')))
    with pytest.raises(ServiceUnavailableError):
        await bad_item.list_targets(tenant_id=DEMO_ID, user_id=7)

    bad_field = RemoteTenantMembershipStore(client=_FakeClient(_response('{"data": {"targets": [{"code": "demo"}]}}')))
    with pytest.raises(ServiceUnavailableError):
        await bad_field.list_targets(tenant_id=DEMO_ID, user_id=7)

    missing_target = RemoteTenantMembershipStore(client=_FakeClient(_response(_targets_payload("acme"))))
    with pytest.raises(ServiceUnavailableError):
        await missing_target.ensure(tenant_id=DEMO_ID, user_id=7, target_tenant_id=DEMO_ID, source="sso_jit")

    empty_body = RemoteTenantMembershipStore(client=_FakeClient(ServiceResponse(status_code=200)))
    with pytest.raises(ServiceUnavailableError):
        await empty_body.list_targets(tenant_id=DEMO_ID, user_id=7)


def test_registry_registration_and_auto_selection() -> None:
    """注册表：空名拒登；未登记快速失败；空名自动选源（本用例不占用 `local` 名位）。"""
    with pytest.raises(ConfigError):
        register_tenant_membership_store("", _test_factory)

    register_tenant_membership_store(_TEST_STORE, _test_factory)
    register_remote_tenant_membership_store()
    known = registered_tenant_membership_stores()
    assert _TEST_STORE in known
    assert REMOTE_TENANT_MEMBERSHIP_STORE in known

    explicit = build_tenant_membership_store(
        _TEST_STORE,
        settings=_settings("org"),
        registry=cast("EngineRegistry", object()),
        session_factory=None,
        service_client=None,
    )
    assert isinstance(explicit, _FakeStore) and explicit.name == _TEST_STORE

    remote = build_tenant_membership_store(
        "",
        settings=_settings("org"),
        registry=cast("EngineRegistry", object()),
        session_factory=None,
        service_client=_FakeClient(_response(_targets_payload())),
    )
    assert isinstance(remote, RemoteTenantMembershipStore)

    with pytest.raises(ConfigError):
        build_tenant_membership_store(
            "no-such-store",
            settings=_settings("tenant"),
            registry=cast("EngineRegistry", object()),
            session_factory=None,
            service_client=None,
        )


def test_remote_store_requires_service_client() -> None:
    """远端实现工厂：缺少 `service_client` 装配时拒启。"""
    with pytest.raises(ConfigError):
        build_tenant_membership_store(
            REMOTE_TENANT_MEMBERSHIP_STORE,
            settings=_settings("org"),
            registry=cast("EngineRegistry", object()),
            session_factory=None,
            service_client=None,
        )

    store = build_tenant_membership_store(
        REMOTE_TENANT_MEMBERSHIP_STORE,
        settings=_settings("org"),
        registry=cast("EngineRegistry", object()),
        session_factory=None,
        service_client=_FakeClient(_response(_targets_payload())),
    )
    assert isinstance(store, RemoteTenantMembershipStore)
    assert LOCAL_TENANT_MEMBERSHIP_STORE == "local"


def _test_factory(**_kwargs: object) -> _FakeStore:
    """构造数据源替身（注册表用例；**不占用** `local` 名位，避免污染服务侧登记）。

    Args:
        **_kwargs: 装配产物（忽略）。

    Returns:
        _FakeStore: 替身数据源。
    """
    return _FakeStore(name=_TEST_STORE)


class _FakeStore:
    """关系数据源替身：内存目标集合（结构上满足 `TenantMembershipStore` 契约）。"""

    def __init__(self, *, name: str = "fake") -> None:
        """初始化。

        Args:
            name: 实现名（断言用）。
        """
        self.name = name
        self.rows: ConcurrentStableList[TenantMembershipTarget] = ConcurrentStableList()
        self.ensured: ConcurrentStableList[tuple[int, int, int, str]] = ConcurrentStableList()

    async def list_targets(
        self, *, tenant_id: int, user_id: int, include_disabled: bool = False
    ) -> ConcurrentStableList[TenantMembershipTarget]:
        """取目标集合（按状态过滤）。

        Args:
            tenant_id: 归属租户主键。
            user_id: 用户主键。
            include_disabled: 是否含 `disabled` 行。

        Returns:
            ConcurrentStableList[TenantMembershipTarget]: 目标集合。
        """
        return ConcurrentStableList(item for item in self.rows if include_disabled or item.status == "active")

    async def ensure(
        self, *, tenant_id: int, user_id: int, target_tenant_id: int, source: str
    ) -> TenantMembershipTarget:
        """建 / 复活关系（记录调用）。

        Args:
            tenant_id: 归属租户主键。
            user_id: 用户主键。
            target_tenant_id: 目标租户主键。
            source: 写入来源。

        Returns:
            TenantMembershipTarget: 目标条目。
        """
        self.ensured.add((tenant_id, user_id, target_tenant_id, source))
        code = _ID_CODES.get(target_tenant_id, f"t{target_tenant_id}")
        target = TenantMembershipTarget(tenant_id=target_tenant_id, code=code, name="租户")
        self.rows.add(target)
        return target

    async def revoke(self, *, tenant_id: int, user_id: int, target_tenant_id: int) -> None:
        """回收单个目标租户关系（替身空实现）。

        Args:
            tenant_id: 归属租户主键。
            user_id: 用户主键。
            target_tenant_id: 目标租户主键。
        """

    async def revoke_all(self, *, tenant_id: int, user_id: int) -> None:
        """回收全部目标租户关系（替身空实现）。

        Args:
            tenant_id: 归属租户主键。
            user_id: 用户主键。
        """


class _FakeTenants:
    """租户源替身：按编码 / 主键返回固定租户上下文（结构上满足 `TenantLookup`）。"""

    async def by_code(self, code: str) -> TenantContext:
        """按编码取租户上下文。

        Args:
            code: 租户编码。

        Returns:
            TenantContext: 租户上下文。

        Raises:
            TenantNotFoundError: 未知租户（404 / 80001）。
        """
        if code in ("demo", "acme"):
            tenant_id = DEMO_ID if code == "demo" else ACME_ID
            name = "演示租户" if code == "demo" else "示例租户"
            return TenantContext(code=code, db_key=f"tenant_{code}", name=name, tenant_id=tenant_id)
        raise TenantNotFoundError(f"未知租户：{code}")

    async def by_domain(self, domain: str) -> TenantContext:
        """按域名取租户上下文（替身不支持）。

        Args:
            domain: 子域名。

        Raises:
            TenantNotFoundError: 恒未命中（404 / 80001）。
        """
        raise TenantNotFoundError(f"未知租户域名：{domain}")

    async def by_id(self, tenant_id: str) -> TenantContext:
        """按主键取租户上下文。

        Args:
            tenant_id: 租户主键字符串。

        Returns:
            TenantContext: 租户上下文。

        Raises:
            TenantNotFoundError: 未知租户（404 / 80001）。
        """
        if tenant_id == str(DEMO_ID):
            return TenantContext(code="demo", db_key="tenant_demo", name="演示租户", tenant_id=DEMO_ID)
        raise TenantNotFoundError(f"未知租户主键：{tenant_id}")

    async def single_active(self) -> TenantContext | None:
        """唯一启用租户解析（本替身含演示 / 示例两个租户 → 恒多启用）。"""
        raise MultipleActiveTenantsError("测试替身：多个启用租户")


def _service(store: _FakeStore) -> DbTenantSelfService:
    """构造真实自助实现（替身依赖）。

    Args:
        store: 关系数据源替身。

    Returns:
        DbTenantSelfService: 真实实现。
    """
    return DbTenantSelfService(membership=store, tenants=_FakeTenants())


async def test_db_self_service_my_tenants_self_heals() -> None:
    """真实实现：无自有行即幂等补建（来源 `self_heal`）；有多租户行时 `multi_tenant=true`。"""
    store = _FakeStore()
    service = _service(store)

    overview = await service.my_tenants(current_code="demo", tenant_id=DEMO_ID, user_id=7)
    assert overview.current_code == "demo"
    assert overview.multi_tenant is False
    assert [item.code for item in overview.tenants] == ["demo"]
    assert list(store.ensured) == [(DEMO_ID, 7, DEMO_ID, TENANT_MEMBERSHIP_SELF_HEAL_SOURCE)]

    store.ensured.clear()
    await service.my_tenants(current_code="demo", tenant_id=DEMO_ID, user_id=7)
    assert list(store.ensured) == []  # 已有自有行：不重复补建

    store.rows.clear()
    store.rows.add(TenantMembershipTarget(tenant_id=ACME_ID, code="acme", name="示例租户"))
    overview = await service.my_tenants(current_code="demo", tenant_id=DEMO_ID, user_id=7)
    assert overview.multi_tenant is True
    assert sorted(str(item.code) for item in overview.tenants) == ["acme", "demo"]


async def test_db_self_service_self_heal_respects_revoke() -> None:
    """真实实现：自有行已存在（`disabled`）时不补建（回收优先）。"""
    store = _FakeStore()
    store.rows.add(TenantMembershipTarget(tenant_id=DEMO_ID, code="demo", name="演示租户", status="disabled"))
    service = _service(store)

    overview = await service.my_tenants(current_code="demo", tenant_id=DEMO_ID, user_id=7)
    assert list(store.ensured) == []
    assert overview.tenants == []
    assert overview.multi_tenant is False


async def test_db_self_service_fallback_and_switch() -> None:
    """真实实现：无主体回落（按编码解析 / 空概览）；switch 命中、越权、缺主体与未知租户。"""
    store = _FakeStore()
    service = _service(store)

    fallback = await service.my_tenants(current_code="demo")
    assert [item.code for item in fallback.tenants] == ["demo"]
    assert fallback.multi_tenant is False
    assert list(store.ensured) == []  # 无主体不落库

    empty = await service.my_tenants()
    assert empty.tenants == [] and empty.current_code is None

    store.rows.add(TenantMembershipTarget(tenant_id=DEMO_ID, code="demo", name="演示租户"))
    hit = await service.switch("demo", tenant_id=DEMO_ID, user_id=7)
    assert hit.tenant_code == "demo"
    assert hit.db_key == "tenant_demo"
    assert hit.applied is True
    assert hit.reissue_token is True
    assert hit.token is None

    with pytest.raises(TenantAccessDeniedError):
        await service.switch("acme", tenant_id=DEMO_ID, user_id=7)

    with pytest.raises(TenantAccessDeniedError):
        await service.switch("demo")

    with pytest.raises(TenantNotFoundError):
        await service.switch("nope", tenant_id=DEMO_ID, user_id=7)


async def test_db_self_service_brand_and_factory() -> None:
    """真实实现：品牌维持平台默认；工厂从应用 state 取依赖；响应契约字段口径。"""
    store = _FakeStore()
    service = _service(store)
    brand = await service.brand(code="demo")
    assert isinstance(brand, TenantBrand)
    assert brand.name == "演示租户"

    response = TenantMembershipListResponse(
        targets=ConcurrentStableList([TenantMembershipTarget(tenant_id=DEMO_ID, code="demo", name="演示租户")])
    )
    assert response.targets[0].tenant_id == DEMO_ID

    app = cast(
        "FastAPI",
        SimpleNamespace(state=SimpleNamespace(tenant_membership=store, tenant_source=_FakeTenants())),
    )
    factory = DbTenantSelfServiceFactory(app)
    assert factory.plugin_key == "tenant_self_service"
    assert isinstance(factory.create(None), DbTenantSelfService)
