"""远程租户源：非租户服务经**租户注册只读契约**取数 + 服务侧缓存 + 版本键惰性比对（06_03）。

- 取数：`GET /api/v1/tenant-registry?code=…`（或 `?domain=…`，租户服务提供）；经 `service_client` 调用。
- 缓存：域 `tenant`（平台数据），载荷带**全局版本戳** `bms:global:tenant:version`；版本不符即重载
  （租户开通 / 停用 / 改名后由租户服务 INCR 版本键，即时生效）。
- 失败分支：未知租户 → `TenantNotFoundError`；停用 → 先**强制回收**该租户引擎（回调）再抛
  `TenantSuspendedError`；契约不可达 → `ServiceUnavailableError`（降级口径见详细设计 §5）。
- 三段解析：网关注入的租户编码（可信边缘）由中间件写入请求态，本实现只负责「按编码 / 域名取注册快照」。
"""

from collections.abc import Awaitable, Callable, Mapping
from typing import cast

from bms_core.cache.base import CacheRegion
from bms_core.core.base import BaseObject
from bms_core.core.config import Settings
from bms_core.core.exceptions import ServiceUnavailableError, TenantNotFoundError, TenantSuspendedError
from bms_core.core.logging import get_logger
from bms_core.core.plugin import resolve_plugin
from bms_core.db.registry import EngineRegistry
from bms_core.db.session import SessionFactory
from bms_core.db.tenant import TenantContext
from bms_core.db.tenant_registry import (
    ACTIVE_STATUS,
    TENANT_VERSION_KEY,
    TenantSnapshot,
    snapshot_cache_key,
    to_tenant_context,
)
from bms_core.db.tenant_source import register_tenant_lookup
from bms_core.servicecall.base import BaseServiceClient, ServiceRequest, ServiceResponse

__all__ = ["TENANT_REGISTRY_PATH", "RemoteTenantSource"]

TENANT_REGISTRY_PATH = "/api/v1/tenant-registry"
"""租户注册只读契约路径（租户服务提供）。"""

_TENANT_SERVICE = "tenant"
"""契约提供方服务标识。"""

_UNAUTHORIZED = 403
_NOT_FOUND = 404

_LOGGER = get_logger("bms.tenant_remote")

REMOTE_TENANT_SOURCE = "remote"
"""远程租户源实现名（登记到共享基座装配点）。"""


class RemoteTenantSource(BaseObject):
    """远程租户源：契约取数 + 缓存 + 版本键（实现 `TenantLookup` 契约）。"""

    def __init__(
        self,
        *,
        client: BaseServiceClient,
        service: str = _TENANT_SERVICE,
        cache: CacheRegion | None = None,
        cache_ttl: int = 60,
        release: Callable[[str], Awaitable[None]] | None = None,
        allow_fallback: bool = False,
    ) -> None:
        """初始化。

        Args:
            client: 服务间调用客户端（`service_client` 能力域）。
            service: 契约提供方服务标识。
            cache: 缓存 Region（None 表示不缓存、每次回源）。
            cache_ttl: 缓存 TTL（秒）。
            release: 停用租户的引擎回收回调（None 表示不回收；由应用装配注入）。
            allow_fallback: 契约不可达时是否按请求值构造兜底上下文（**仅开发 / 测试**，
                由装配方按 `[app].env` 与 `[tenant].allow_demo_fallback` 计算，生产为 False）。
        """
        self._client = client
        self._service = service
        self._cache = cache
        self._cache_ttl = cache_ttl
        self._release = release
        self._allow_fallback = allow_fallback

    async def by_code(self, code: str) -> TenantContext:
        """按租户编码取上下文。

        Args:
            code: 租户编码（全小写）。

        Returns:
            TenantContext: 租户上下文。

        Raises:
            TenantNotFoundError: 租户不存在（404 / 80001）。
            TenantSuspendedError: 租户已停用（403 / 80002）。
            ServiceUnavailableError: 契约不可达或响应非法。
        """
        return await self._resolve("code", code)

    async def by_domain(self, domain: str) -> TenantContext:
        """按子域名取上下文。

        Args:
            domain: 子域名（如 `demo.bms.example.com`）。

        Returns:
            TenantContext: 租户上下文。

        Raises:
            TenantNotFoundError: 域名未注册租户（404 / 80001）。
            TenantSuspendedError: 租户已停用（403 / 80002）。
            ServiceUnavailableError: 契约不可达或响应非法。
        """
        return await self._resolve("domain", domain)

    async def invalidate(self, code: str | None = None, *, domain: str | None = None) -> None:
        """失效本地缓存（租户服务写路径亦可经版本键全局失效）。

        Args:
            code: 租户编码。
            domain: 子域名。
        """
        if code:
            self._cache_delete(snapshot_cache_key("code", code))
        if domain:
            self._cache_delete(snapshot_cache_key("domain", domain))

    async def _resolve(self, kind: str, value: str) -> TenantContext:
        """取数编排：缓存（版本比对）→ 契约回源 → 回填 → 状态判定。

        Args:
            kind: `code` / `domain`。
            value: 查询值。

        Returns:
            TenantContext: 租户上下文。

        Raises:
            TenantNotFoundError: 未知租户。
            TenantSuspendedError: 租户已停用（含引擎强制回收）。
            ServiceUnavailableError: 契约不可达或响应非法。
        """
        key = snapshot_cache_key(kind, value)
        snapshot = self._cache_get(key)
        if snapshot is None:
            try:
                snapshot = await self._fetch(kind, value)
            except ServiceUnavailableError as exc:
                if not self._allow_fallback:
                    raise
                _LOGGER.warning("tenant_registry_contract_unavailable", kind=kind, value=value, error=repr(exc))
                snapshot = TenantSnapshot(code=value, name=value)
            else:
                self._cache_set(key, snapshot)
        if snapshot.status != ACTIVE_STATUS:
            if self._release is not None:
                await self._release(snapshot.code)
            raise TenantSuspendedError(f"租户已停用：{snapshot.code}")
        return to_tenant_context(snapshot)

    async def _fetch(self, kind: str, value: str) -> TenantSnapshot:
        """经契约取注册快照（状态码映射为业务异常）。

        Args:
            kind: `code` / `domain`。
            value: 查询值。

        Returns:
            TenantSnapshot: 注册快照。

        Raises:
            TenantNotFoundError: 404。
            TenantSuspendedError: 403（契约侧已按停用拒绝）。
            ServiceUnavailableError: 其余非 2xx 或响应体非法。
        """
        request = ServiceRequest(service=self._service, method="GET", path=TENANT_REGISTRY_PATH, query={kind: value})
        response = await self._client.call(request)
        if response.status_code == _NOT_FOUND:
            raise TenantNotFoundError(f"未知租户：{value}")
        if response.status_code == _UNAUTHORIZED:
            raise TenantSuspendedError(f"租户不可用：{value}")
        if not 200 <= response.status_code < 300:
            raise ServiceUnavailableError(f"租户注册契约调用失败（{response.status_code}）")
        payload = _payload_data(response)
        try:
            return TenantSnapshot.from_payload(payload)
        except KeyError as exc:
            raise ServiceUnavailableError(f"租户注册契约响应非法：{exc}") from exc

    def _cache_get(self, key: str) -> TenantSnapshot | None:
        """读缓存（版本不符视为未命中）。

        Args:
            key: 缓存 key。

        Returns:
            TenantSnapshot | None: 快照；未命中 / 陈旧返回 None。
        """
        cache = self._cache
        if cache is None:
            return None
        raw = cache.get(key)
        if not isinstance(raw, Mapping):
            return None
        payload = cast("Mapping[str, object]", raw)
        version = payload.get("version")
        if not isinstance(version, int) or cache.is_stale(TENANT_VERSION_KEY, version):
            return None
        try:
            return TenantSnapshot.from_payload(payload)
        except KeyError:
            return None

    def _cache_set(self, key: str, snapshot: TenantSnapshot) -> None:
        """写缓存（附当前全局版本戳）。

        Args:
            key: 缓存 key。
            snapshot: 注册快照。
        """
        cache = self._cache
        if cache is None:
            return
        version = cache.get_global_version()
        cache.set(key, snapshot.to_payload(version=version), self._cache_ttl)

    def _cache_delete(self, key: str) -> None:
        """删缓存（幂等）。

        Args:
            key: 缓存 key。
        """
        cache = self._cache
        if cache is not None:
            cache.delete(key)


def register_remote_tenant_source() -> None:
    """登记 `remote` 租户源实现（模块导入即调用；装配点见 `application.py`）。"""

    def _factory(
        *,
        settings: Settings,
        registry: EngineRegistry,
        cache: CacheRegion | None,
        session_factory: SessionFactory | None,
    ) -> RemoteTenantSource:
        """构造远程租户源（服务客户端经插件解析；停用租户回收走引擎注册表）。"""
        del session_factory
        client = cast(
            "BaseServiceClient",
            resolve_plugin(
                "service_client",
                settings.service_client.provider,
                expected_version=BaseServiceClient.contract_version,
            ),
        )
        return RemoteTenantSource(
            client=client,
            cache=cache,
            cache_ttl=settings.tenant.resolve_cache_ttl,
            release=registry.release,
            allow_fallback=settings.app.env in ("dev", "test") and settings.tenant.allow_demo_fallback,
        )

    register_tenant_lookup(REMOTE_TENANT_SOURCE, _factory)


def _payload_data(response: ServiceResponse) -> Mapping[str, object]:
    """取统一响应包裹的 `data` 字段。

    Args:
        response: 契约响应。

    Returns:
        Mapping[str, object]: `data` 字典（缺失或非对象时抛 `ServiceUnavailableError`）。

    Raises:
        ServiceUnavailableError: 响应体非法。
    """
    raw = response.payload()
    body = cast("Mapping[str, object]", raw) if isinstance(raw, Mapping) else None
    data: object = body.get("data") if body is not None else None
    if not isinstance(data, Mapping):
        raise ServiceUnavailableError("租户注册契约响应缺少 data")
    return cast("Mapping[str, object]", data)


register_remote_tenant_source()
