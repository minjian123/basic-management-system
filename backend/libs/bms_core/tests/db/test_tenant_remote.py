"""远程租户源测试（Kiwi 2176）：契约回源 / 缓存与版本键 / 失败分支 / 降级口径。"""

import json

import pytest

from bms_core.cache.memory import MemoryCacheRegion
from bms_core.core.exceptions import ServiceUnavailableError, TenantNotFoundError, TenantSuspendedError
from bms_core.db.tenant_registry import snapshot_cache_key
from bms_core.db.tenant_remote import TENANT_REGISTRY_PATH, RemoteTenantSource, register_remote_tenant_source
from bms_core.db.tenant_source import registered_tenant_sources
from bms_core.servicecall.base import BaseServiceClient, ServiceRequest, ServiceResponse


class _StubClient(BaseServiceClient):
    """服务客户端替身：按预设响应 / 异常返回，并记录调用。"""

    plugin_name: str = "stub"

    def __init__(self, responses: list[ServiceResponse | Exception]) -> None:
        """初始化预设响应序列。"""
        super().__init__()
        self.responses = responses
        self.calls: list[ServiceRequest] = []

    async def call(self, request: ServiceRequest) -> ServiceResponse:
        """返回预设响应（异常项直接抛出）。"""
        self.calls.append(request)
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def _ok(payload: dict[str, object], status_code: int = 200) -> ServiceResponse:
    """构造统一响应包裹的成功响应。"""
    body = json.dumps({"code": 0, "message": "ok", "data": payload}).encode("utf-8")
    return ServiceResponse(status_code=status_code, content=body)


def _client(*items: ServiceResponse | Exception) -> _StubClient:
    """构造带预设响应的客户端替身。"""
    return _StubClient(responses=list(items))


def _payload(code: str = "demo", *, status: str = "active") -> dict[str, object]:
    """构造租户注册载荷。"""
    return {
        "code": code,
        "name": f"{code} 租户",
        "domain": f"{code}.bms.example.com",
        "status": status,
        "expire_at": None,
        "tenant_id": 7,
    }


@pytest.mark.kiwi_id(2176)
async def test_remote_source_fetches_and_maps_context() -> None:
    """契约回源：按 code 取注册并映射上下文（路径 / 查询参数与库键口径一致）。"""
    client = _client(_ok(_payload()))
    source = RemoteTenantSource(client=client)
    context = await source.by_code("demo")
    assert context.tenant_code == "demo"
    assert context.db_key == "tenant_demo"
    assert context.name == "demo 租户"
    assert context.tenant_id == 7
    assert context.domain == "demo.bms.example.com"
    assert context.status == "active"
    assert client.calls[0].path == TENANT_REGISTRY_PATH
    assert client.calls[0].service == "tenant"
    assert dict(client.calls[0].query or {}) == {"code": "demo"}


@pytest.mark.kiwi_id(2176)
async def test_remote_source_failure_branches() -> None:
    """失败分支：未知 404 / 停用 403（先强制回收引擎）/ 响应非法 / 契约不可达（无兜底即抛）。"""
    released: list[str] = []

    async def _release(code: str) -> None:
        released.append(code)

    source = RemoteTenantSource(
        client=_client(ServiceResponse(status_code=404), ServiceResponse(status_code=403)),
        release=_release,
    )
    with pytest.raises(TenantNotFoundError):
        await source.by_code("ghost")
    with pytest.raises(TenantSuspendedError):
        await source.by_code("sosp")

    source = RemoteTenantSource(client=_client(_ok(_payload("sosp", status="suspended"))), release=_release)
    with pytest.raises(TenantSuspendedError):
        await source.by_code("sosp")
    assert released == ["sosp"]

    source = RemoteTenantSource(client=_client(ServiceResponse(status_code=200, content=b"{}")))
    with pytest.raises(ServiceUnavailableError):
        await source.by_code("demo")

    source = RemoteTenantSource(client=_client(ServiceUnavailableError("契约不可达")))
    with pytest.raises(ServiceUnavailableError):
        await source.by_code("demo")


@pytest.mark.kiwi_id(2176)
async def test_remote_source_cache_and_version_invalidation() -> None:
    """缓存与版本键：命中不重复回源；版本递增后缓存陈旧重载；`invalidate` 删除单键。"""
    cache = MemoryCacheRegion(domain="tenant")
    client = _client(_ok(_payload()), _ok(_payload()))
    source = RemoteTenantSource(client=client, cache=cache, cache_ttl=60)

    await source.by_code("demo")
    await source.by_code("demo")
    assert len(client.calls) == 1

    cache.bump_version()
    await source.by_code("demo")
    assert len(client.calls) == 2

    assert cache.get(snapshot_cache_key("code", "demo")) is not None
    await source.invalidate("demo", domain="demo.bms.example.com")
    assert cache.get(snapshot_cache_key("code", "demo")) is None
    assert cache.get(snapshot_cache_key("domain", "demo.bms.example.com")) is None


@pytest.mark.kiwi_id(2176)
async def test_remote_source_fallback_only_when_allowed() -> None:
    """降级口径：允许兜底时按请求值构造上下文且不落缓存；不允许时直接抛错。"""
    cache = MemoryCacheRegion(domain="tenant")
    client = _client(ServiceUnavailableError("kill"), _ok(_payload("acme")))
    source = RemoteTenantSource(client=client, cache=cache, allow_fallback=True)

    context = await source.by_code("acme")
    assert context.tenant_code == "acme" and context.db_key == "tenant_acme"
    assert cache.get(snapshot_cache_key("code", "acme")) is None

    context = await source.by_code("acme")
    assert context.name == "acme 租户"


@pytest.mark.kiwi_id(2176)
async def test_remote_source_fallback_rejects_non_code_values() -> None:
    """兜底收口（06_04）：契约不可达且来源值不可作租户编码（域名 / 非法编码）按未命中 4xx，不构造非法库名。"""
    client = _client(ServiceUnavailableError("kill"), ServiceUnavailableError("kill"))
    source = RemoteTenantSource(client=client, allow_fallback=True)

    with pytest.raises(TenantNotFoundError):
        await source.by_domain("demo.bms.example.com")
    with pytest.raises(TenantNotFoundError):
        await source.by_code("127.0.0.1")


@pytest.mark.kiwi_id(2176)
async def test_remote_source_by_domain_and_registration_idempotent() -> None:
    """按域名取上下文（query 为 domain）；`register_remote_tenant_source` 幂等可重复调用。"""
    register_remote_tenant_source()
    register_remote_tenant_source()
    assert "remote" in registered_tenant_sources()

    client = _client(_ok(_payload()))
    source = RemoteTenantSource(client=client)
    context = await source.by_domain("demo.bms.example.com")
    assert context.tenant_code == "demo"
    assert dict(client.calls[0].query or {}) == {"domain": "demo.bms.example.com"}
