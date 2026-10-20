"""租户模块门禁真实实现：经 tenant 服务内部只读契约取模块状态（任务 `04_01`）。

- 契约：`GET /api/v1/tenant/internal/modules/status?tenant_id=…`，返回 `{enabled, disabled, version}`。
- 缓存：按 `tenant_id` 缓存状态集（TTL `[tenant_module].ttl`，缺省 5 秒）；tenant 服务开关模块后删除
  该缓存键（Redis 域跨实例即删，内存域仅本进程）→ 留 TTL 作为跨实例兜底时效。
- 降级：回源失败 / 响应非法 → `WARNING` + 视为 `enabled`（fail-open，见能力域口径）。
"""

from collections.abc import Mapping
from typing import cast

from bms_core.cache.base import CacheRegion
from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableSet
from bms_core.core.config import Settings
from bms_core.core.logging import get_logger
from bms_core.core.objects import BaseFrameworkObject
from bms_core.servicecall.base import BaseServiceClient, ServiceCallPolicy, ServiceRequest, ServiceResponse
from bms_core.services.module_registry import is_optional_module
from bms_core.tenant_module.base import (
    TENANT_MODULE_STATE_ABSENT,
    TENANT_MODULE_STATE_DISABLED,
    TENANT_MODULE_STATE_ENABLED,
    BaseTenantModuleGate,
)

__all__ = [
    "REMOTE_TENANT_MODULE_GATE",
    "RemoteTenantModuleGate",
    "TenantModuleSnapshot",
    "build_remote_gate",
    "tenant_module_cache_key",
]

_LOGGER = get_logger("bms.tenant_module")

REMOTE_TENANT_MODULE_GATE = "remote"
"""真实门禁实现名。"""

_TENANT_SERVICE = "tenant"
_MODULE_SCOPES: tuple[str, ...] = ("tenant_module",)


def tenant_module_cache_key(tenant_id: int, cache: CacheRegion | None = None) -> str:
    """模块状态缓存键（tenant 服务与各服务门禁共用）。

    Args:
        tenant_id: 租户主键。
        cache: 缓存域（None 时返回未加前缀的裸键）。

    Returns:
        str: 缓存键。
    """
    if cache is None:
        return f"tenant_modules:{tenant_id}"
    return cache.build_key(f"tenant_modules:{tenant_id}", tenant="global")


class TenantModuleSnapshot(BaseFrameworkObject):
    """租户模块状态集（开通清单快照）。"""

    enabled: ConcurrentStableSet[str]
    """已开通且启用的模块标识。"""

    disabled: ConcurrentStableSet[str]
    """已开通但停用的模块标识。"""

    def __init__(self, *, enabled: ConcurrentStableSet[str], disabled: ConcurrentStableSet[str]) -> None:
        """初始化。

        Args:
            enabled: 已开通且启用的模块标识。
            disabled: 已开通但停用的模块标识。
        """
        self.enabled = enabled
        self.disabled = disabled


class RemoteTenantModuleGate(BaseTenantModuleGate, BaseFrameworkObject):
    """远端门禁：tenant 服务内部契约 + 本地缓存（fail-open）。"""

    def __init__(self, *, client: BaseServiceClient, cache: CacheRegion | None = None, ttl: int = 5) -> None:
        """初始化。

        Args:
            client: 服务间调用客户端。
            cache: 缓存域（None 表示不缓存、每次回源）。
            ttl: 状态缓存 TTL（秒；0 表示不缓存）。
        """
        self._client = client
        self._cache = cache
        self._ttl = ttl

    async def state(self, *, tenant_id: int, tenant_code: str | None, module_key: str) -> str:
        """取租户模块状态（基础 / 非产品模块恒 `enabled`）。

        Args:
            tenant_id: 租户主键。
            tenant_code: 租户编码（服务 JWT 租户位）。
            module_key: 模块标识。

        Returns:
            str: `enabled` / `disabled` / `absent`。
        """
        if not is_optional_module(module_key):
            return TENANT_MODULE_STATE_ENABLED
        if tenant_id <= 0:
            return TENANT_MODULE_STATE_ABSENT
        snapshot = await self._snapshot(tenant_id, tenant_code)
        if snapshot is None:
            return TENANT_MODULE_STATE_ENABLED
        if module_key in snapshot.enabled:
            return TENANT_MODULE_STATE_ENABLED
        if module_key in snapshot.disabled:
            return TENANT_MODULE_STATE_DISABLED
        return TENANT_MODULE_STATE_ABSENT

    async def _snapshot(self, tenant_id: int, tenant_code: str | None) -> TenantModuleSnapshot | None:
        """取租户模块状态集（缓存优先；回源失败返回 None）。

        Args:
            tenant_id: 租户主键。
            tenant_code: 租户编码。

        Returns:
            TenantModuleSnapshot | None: 状态集；回源失败为 None。
        """
        cache = self._cache
        cache_key = tenant_module_cache_key(tenant_id, cache)
        if cache is not None and self._ttl > 0:
            cached = cache.get(cache_key)
            if isinstance(cached, Mapping):
                payload = cast("Mapping[str, object]", cached)
                return TenantModuleSnapshot(
                    enabled=ConcurrentStableSet(cast("list[str]", payload.get("enabled", []))),
                    disabled=ConcurrentStableSet(cast("list[str]", payload.get("disabled", []))),
                )
        fetched = await self._fetch(tenant_id, tenant_code)
        if fetched is None:
            return None
        if cache is not None and self._ttl > 0:
            cache.set(
                cache_key,
                {"enabled": sorted(fetched.enabled), "disabled": sorted(fetched.disabled)},
                self._ttl,
            )
        return fetched

    async def _fetch(self, tenant_id: int, tenant_code: str | None) -> TenantModuleSnapshot | None:
        """回源 tenant 服务内部契约（失败 fail-open）。

        Args:
            tenant_id: 租户主键。
            tenant_code: 租户编码。

        Returns:
            TenantModuleSnapshot | None: 状态集；失败为 None。
        """
        try:
            response = await self._client.call(
                ServiceRequest(
                    service=_TENANT_SERVICE,
                    method="GET",
                    path="/api/v1/tenant/internal/modules/status",
                    query=ConcurrentStableDict({"tenant_id": str(tenant_id)}),
                    tenant_id=tenant_code,
                    policy=ServiceCallPolicy(scopes=_MODULE_SCOPES),
                )
            )
        except Exception as exc:  # fail-open：只影响模块拦截层
            _LOGGER.warning("tenant_module_gate_unreachable", tenant_id=tenant_id, error=type(exc).__name__)
            return None
        data = _payload(response, tenant_id)
        if data is None:
            return None
        enabled = data.get("enabled", [])
        disabled = data.get("disabled", [])
        if not isinstance(enabled, list | tuple) or not isinstance(disabled, list | tuple):
            _LOGGER.warning("tenant_module_gate_bad_payload", tenant_id=tenant_id)
            return None
        return TenantModuleSnapshot(
            enabled=ConcurrentStableSet(str(item) for item in cast("list[object]", enabled)),
            disabled=ConcurrentStableSet(str(item) for item in cast("list[object]", disabled)),
        )


def _payload(response: ServiceResponse, tenant_id: int) -> ConcurrentStableDict[str, object] | None:
    """解析内部契约响应（非 2xx / 非对象 / code≠0 记 WARNING 并返回 None）。

    Args:
        response: 服务间调用响应。
        tenant_id: 租户主键（日志用）。

    Returns:
        ConcurrentStableDict[str, object] | None: 响应 `data`；非法为 None。
    """
    if response.status_code != 200:
        _LOGGER.warning("tenant_module_gate_http_error", tenant_id=tenant_id, status=response.status_code)
        return None
    payload = response.payload()
    if not isinstance(payload, dict):
        _LOGGER.warning("tenant_module_gate_bad_response", tenant_id=tenant_id)
        return None
    body = cast("dict[str, object]", payload)
    if body.get("code") != 0:
        _LOGGER.warning("tenant_module_gate_business_error", tenant_id=tenant_id, code=body.get("code"))
        return None
    data = body.get("data")
    if not isinstance(data, dict):
        _LOGGER.warning("tenant_module_gate_bad_data", tenant_id=tenant_id)
        return None
    return ConcurrentStableDict(cast("dict[str, object]", data))


def build_remote_gate(
    settings: Settings, client: BaseServiceClient, cache: CacheRegion | None
) -> RemoteTenantModuleGate:
    """构造远端门禁（装配期调用）。

    Args:
        settings: 应用配置（`[tenant_module]` 分区）。
        client: 服务间调用客户端。
        cache: 缓存域。

    Returns:
        RemoteTenantModuleGate: 远端门禁实例。
    """
    return RemoteTenantModuleGate(client=client, cache=cache, ttl=settings.tenant_module.ttl)
