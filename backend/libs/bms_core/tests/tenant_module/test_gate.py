"""租户模块门禁能力域测试（任务 `04_01`；Kiwi 2325）。

覆盖：门禁契约（占位 / 远端）、状态判定（基础模块 / 产品模块三态 / 非法租户）、回源失败 fail-open、
缓存命中与开关后删除、`require_permission` 后置门禁（82008）与平台/无租户上下文放行。
"""

from typing import cast

import pytest

from bms_core.cache.base import CacheRegion
from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.exceptions import PluginError, TenantModuleDisabledError
from bms_core.servicecall.base import BaseServiceClient
from bms_core.services.module_registry import (
    TENANT_BASE_MODULE_KEYS,
    TENANT_OPTIONAL_MODULE_KEYS,
    ModuleRecord,
    is_optional_module,
    module_for_business,
    register_service_records,
    reset_service_records,
    tenant_base_module_keys,
)
from bms_core.tenant_module.base import (
    TENANT_MODULE_STATE_ABSENT,
    TENANT_MODULE_STATE_DISABLED,
    TENANT_MODULE_STATE_ENABLED,
    BaseTenantModuleGate,
)
from bms_core.tenant_module.null import NullTenantModuleGate
from bms_core.tenant_module.remote import (
    REMOTE_TENANT_MODULE_GATE,
    RemoteTenantModuleGate,
    build_remote_gate,
    tenant_module_cache_key,
)

pytestmark = pytest.mark.kiwi_id(2325)


class _StubClient:
    """服务间客户端替身：记录调用并返回固定响应。"""

    def __init__(self, payload: object = None, *, status: int = 200, error: Exception | None = None) -> None:
        self.payload = payload
        self.status = status
        self.error = error
        self.calls: ConcurrentStableList[object] = ConcurrentStableList()

    async def call(self, request: object) -> object:
        self.calls.append(request)
        if self.error is not None:
            raise self.error
        return _StubResponse(self.status, self.payload)


class _StubResponse:
    """服务间响应替身。"""

    def __init__(self, status_code: int, payload: object) -> None:
        self.status_code = status_code
        self._payload = payload

    def payload(self) -> object:
        return self._payload


class _MemoryCache:
    """缓存域替身（最小接口）。"""

    def __init__(self) -> None:
        self.data: ConcurrentStableDict[str, object] = ConcurrentStableDict()

    def get(self, key: str) -> object | None:
        return self.data.get(key)

    def set(self, key: str, value: object, ttl: int | None = None) -> None:
        self.data[key] = value

    def delete(self, key: str) -> None:
        self.data.pop(key, None)

    def build_key(self, business_key: str, *, tenant: str | None = None) -> str:
        return f"bms:{tenant or 'global'}:generic:{business_key}"

    def get_global_version(self) -> int:
        return 0


def _gate(client: object, cache: _MemoryCache | None = None, ttl: int = 5) -> RemoteTenantModuleGate:
    return RemoteTenantModuleGate(client=client, cache=cache, ttl=ttl)  # type: ignore[arg-type]


def test_module_registry_single_source() -> None:
    """模块清单单一来源：基础 / 可勾选互斥、业务段映射只对产品模块、判定函数一致。"""
    assert not set(TENANT_BASE_MODULE_KEYS) & set(TENANT_OPTIONAL_MODULE_KEYS)
    assert "mdm" not in TENANT_BASE_MODULE_KEYS
    assert module_for_business("pur") == "pur"
    assert module_for_business("user") is None
    assert is_optional_module("pur") is True
    assert is_optional_module("sys") is False


def _product_service(module_key: str, *, tenant_base: bool) -> ModuleRecord:
    """构造产品服务行（只填装载判定所需字段）。

    Args:
        module_key: 模块标识。
        tenant_base: 恒开通声明。

    Returns:
        ModuleRecord: 产品分组服务行。
    """
    return ModuleRecord(
        module_key=module_key,
        service_key=module_key,
        name=f"{module_key} 演示服务",
        table_prefix=f"{module_key}_",
        event_domain=module_key,
        service_group="product",
        product_key="demo",
        tenant_base=tenant_base,
    )


def test_tenant_base_module_keys_follow_loaded_manifest() -> None:
    """恒开通集合：纯平台环境不含产品模块；装载 `tenant_base` 声明后并入（插入序、同键去重）。"""
    try:
        reset_service_records()
        assert list(tenant_base_module_keys()) == list(TENANT_BASE_MODULE_KEYS)

        register_service_records(
            (
                _product_service("mdm", tenant_base=True),
                _product_service("pur", tenant_base=False),
                # 与平台常量同键：并入时去重（同键不重复追加）
                ModuleRecord(
                    module_key="sys",
                    service_key="platform",
                    name="平台地基与配置服务",
                    table_prefix="sys_",
                    event_domain="sys",
                    service_group="foundation",
                    tenant_base=True,
                ),
            )
        )
        keys = list(tenant_base_module_keys())
        assert keys.count("mdm") == 1
        assert keys.count("sys") == 1
        assert "pur" not in keys
        assert keys[-1] == "mdm"
        assert keys[: len(TENANT_BASE_MODULE_KEYS)] == list(TENANT_BASE_MODULE_KEYS)
    finally:
        reset_service_records()


async def test_null_gate_allows_everything() -> None:
    """占位门禁恒定已开通；`ensure` 不拦截。"""
    gate = NullTenantModuleGate()
    assert await gate.state(tenant_id=1, tenant_code="demo", module_key="pur") == TENANT_MODULE_STATE_ENABLED
    assert await gate.state(tenant_id=1, tenant_code="demo", module_key="sys") == TENANT_MODULE_STATE_ENABLED
    await gate.ensure(tenant_id=1, tenant_code="demo", module_key="pur")


def test_get_tenant_module_gate_resolves_null() -> None:
    """依赖注入提供者：provider 为空 → 占位实现。"""
    from types import SimpleNamespace

    from fastapi import FastAPI

    from bms_core.core.config import Settings
    from bms_core.tenant_module.base import get_tenant_module_gate

    settings = Settings()
    settings.tenant_module.provider = ""
    app = FastAPI()
    app.state.settings = settings
    request = SimpleNamespace(app=app)
    assert isinstance(get_tenant_module_gate(request), NullTenantModuleGate)  # type: ignore[arg-type]


async def test_base_gate_ensure_skips_base_and_missing_tenant() -> None:
    """基础模块 / 无租户上下文：直接放行，不回源。"""
    client = _StubClient()
    gate = _gate(client)
    await gate.ensure(tenant_id=1, tenant_code="demo", module_key="sys")
    await gate.ensure(tenant_id=None, tenant_code=None, module_key="pur")
    assert client.calls == []


async def test_remote_gate_states_and_cache() -> None:
    """产品模块三态（enabled/disabled/absent）、缓存命中（不重复回源）。"""
    payload = {"code": 0, "data": {"enabled": ["pur"], "disabled": ["pay"], "version": 1}}
    client = _StubClient(payload)
    cache = _MemoryCache()
    gate = _gate(client, cache)
    assert await gate.state(tenant_id=7, tenant_code="demo", module_key="pur") == TENANT_MODULE_STATE_ENABLED
    assert await gate.state(tenant_id=7, tenant_code="demo", module_key="sys") == TENANT_MODULE_STATE_ENABLED
    assert await gate.state(tenant_id=7, tenant_code="demo", module_key="pay") == TENANT_MODULE_STATE_DISABLED
    assert await gate.state(tenant_id=7, tenant_code="demo", module_key="sup") == TENANT_MODULE_STATE_ABSENT
    assert len(client.calls) == 1
    assert tenant_module_cache_key(7, cast("CacheRegion", cache)) in cache.data


async def test_remote_gate_cache_ttl_zero_refetches() -> None:
    """TTL=0：不缓存，每次回源。"""
    payload = {"code": 0, "data": {"enabled": [], "disabled": ["pay"], "version": 1}}
    client = _StubClient(payload)
    gate = _gate(client, _MemoryCache(), ttl=0)
    await gate.state(tenant_id=7, tenant_code="demo", module_key="pay")
    await gate.state(tenant_id=7, tenant_code="demo", module_key="pay")
    assert len(client.calls) == 2


async def test_remote_gate_unreachable_fail_open() -> None:
    """回源异常 / 非 2xx / 非法载荷：fail-open 视为已开通。"""
    failed = _gate(_StubClient(error=RuntimeError("boom")))
    assert await failed.state(tenant_id=1, tenant_code="demo", module_key="pur") == TENANT_MODULE_STATE_ENABLED

    http_error = _gate(_StubClient({"code": 0, "data": {}}, status=500))
    assert await http_error.state(tenant_id=1, tenant_code="demo", module_key="pur") == TENANT_MODULE_STATE_ENABLED

    bad_body = _gate(_StubClient({"code": 82005}))
    assert await bad_body.state(tenant_id=1, tenant_code="demo", module_key="pur") == TENANT_MODULE_STATE_ENABLED

    bad_data = _gate(_StubClient({"code": 0, "data": []}))
    assert await bad_data.state(tenant_id=1, tenant_code="demo", module_key="pur") == TENANT_MODULE_STATE_ENABLED

    bad_lists = _gate(_StubClient({"code": 0, "data": {"enabled": "pur", "disabled": []}}))
    assert await bad_lists.state(tenant_id=1, tenant_code="demo", module_key="pur") == TENANT_MODULE_STATE_ENABLED

    not_json = _gate(_StubClient(None))
    assert await not_json.state(tenant_id=1, tenant_code="demo", module_key="pur") == TENANT_MODULE_STATE_ENABLED


async def test_remote_gate_invalid_tenant_and_disabled_ensure() -> None:
    """非法租户主键按未开通；停用模块 `ensure` 抛 82008。"""
    payload = {"code": 0, "data": {"enabled": [], "disabled": ["pay"], "version": 1}}
    gate = _gate(_StubClient(payload))
    assert await gate.state(tenant_id=0, tenant_code=None, module_key="pur") == TENANT_MODULE_STATE_ABSENT
    with pytest.raises(TenantModuleDisabledError):
        await gate.ensure(tenant_id=9, tenant_code="demo", module_key="pay")


def test_build_remote_gate_uses_settings() -> None:
    """工厂构造：实现名与 TTL 取自配置。"""
    from bms_core.core.config import Settings

    gate = build_remote_gate(Settings(), cast("BaseServiceClient", _StubClient()), None)
    assert isinstance(gate, RemoteTenantModuleGate)
    assert REMOTE_TENANT_MODULE_GATE == "remote"


def test_gate_contract_metadata() -> None:
    """插件契约元数据（能力域登记口径）。"""
    assert BaseTenantModuleGate.plugin_key == "tenant_module"
    assert BaseTenantModuleGate.contract_version


def test_remote_gate_unknown_provider_rejected() -> None:
    """`resolve_plugin` 对未登记实现名抛 PluginError（经 `get_tenant_module_gate` 路径）。"""
    from bms_core.core.plugin import resolve_plugin

    with pytest.raises(PluginError):
        resolve_plugin("tenant_module", "unknown", expected_version=BaseTenantModuleGate.contract_version)


async def test_require_permission_module_gate_blocks_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    """`require_permission` 后置门禁：产品模块停用 → 82008；基础模块 / 无租户放行。"""
    from fastapi import FastAPI
    from starlette.requests import Request

    from bms_core.core import context
    from bms_core.permission import base as permission_base

    class _Checker:
        async def aprepare(self, *, request: object) -> None:
            del request

        def require(self, code: str) -> None:
            del code

    gate = NullTenantModuleGate()

    async def _disabled_state(**_: object) -> str:
        return TENANT_MODULE_STATE_DISABLED

    monkeypatch.setattr(gate, "state", _disabled_state)

    def _checker_for(request: object) -> _Checker:
        del request
        return _Checker()

    def _gate_for(request: object) -> BaseTenantModuleGate:
        del request
        return gate

    monkeypatch.setattr(permission_base, "get_permission_checker", _checker_for)
    monkeypatch.setattr(permission_base, "get_tenant_module_gate", _gate_for)
    request = Request({"type": "http", "app": FastAPI(), "headers": []})
    dependency = permission_base.require_permission("pur:query")

    token = context.current_tenant_id.set("9")
    try:
        with pytest.raises(TenantModuleDisabledError):
            await dependency(request)
    finally:
        context.current_tenant_id.reset(token)

    def _no_module(code: str) -> str | None:
        del code
        return None

    monkeypatch.setattr(permission_base, "module_for_business", _no_module)
    token = context.current_tenant_id.set("9")
    try:
        await dependency(request)
    finally:
        context.current_tenant_id.reset(token)

    token = context.current_tenant_id.set(None)
    try:
        await dependency(request)
    finally:
        context.current_tenant_id.reset(token)


async def test_require_permission_skips_without_or_invalid_tenant(monkeypatch: pytest.MonkeyPatch) -> None:
    """无租户上下文 / 非法租户值：模块门禁跳过（不误拦平台与内部调用）。"""
    from fastapi import FastAPI
    from starlette.requests import Request

    from bms_core.core import context
    from bms_core.permission import base as permission_base

    class _Checker:
        async def aprepare(self, *, request: object) -> None:
            del request

        def require(self, code: str) -> None:
            del code

    def _boom(*args: object, **kwargs: object) -> object:
        del args, kwargs
        raise AssertionError("门禁不应被调用")

    def _checker_for(request: object) -> _Checker:
        del request
        return _Checker()

    monkeypatch.setattr(permission_base, "get_permission_checker", _checker_for)
    monkeypatch.setattr(permission_base, "get_tenant_module_gate", _boom)
    request = Request({"type": "http", "app": FastAPI(), "headers": []})
    dependency = permission_base.require_permission("pur:query")

    token = context.current_tenant_id.set(None)
    try:
        await dependency(request)
    finally:
        context.current_tenant_id.reset(token)

    token = context.current_tenant_id.set("abc")
    try:
        await dependency(request)
    finally:
        context.current_tenant_id.reset(token)


def test_resolve_cache_region_falls_back_to_none() -> None:
    """缓存实现解析失败：按不缓存降级（门禁每次回源）。"""
    from fastapi import FastAPI

    from bms_core.core.assembly import _resolve_cache_region  # pyright: ignore[reportPrivateUsage]
    from bms_core.core.config import Settings

    settings = Settings()
    settings.cache.provider = "missing-cache-provider"
    app = FastAPI()
    app.state.settings = settings
    assert _resolve_cache_region(app) is None
