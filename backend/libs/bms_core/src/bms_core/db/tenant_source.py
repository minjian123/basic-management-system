"""租户源装配点：契约在 `db/tenant.py`，实现按归属落服务（06_03）。

- 共享基座库只保留**契约（`TenantLookup`）与装配点**；实现由服务注册：
  - `remote`：`db/tenant_remote.py`（非租户服务经服务契约取数 + 缓存 + 版本键）；
  - `local`：`bms_tenant/sources/tenant_source.py`（租户服务直读自身平台服务库）。
- 选源：`[tenant].source` 显式指定；空串为**自动**——运行服务即租户服务 → `local`，否则 `remote`。
- `build_tenant_lookup` 是应用装配（`application.py`）的唯一入口；未注册名快速失败。
"""

from typing import Protocol

from bms_core.cache.base import CacheRegion
from bms_core.core.config import Settings
from bms_core.core.exceptions import ConfigError
from bms_core.db.registry import EngineRegistry
from bms_core.db.session import SessionFactory
from bms_core.db.tenant import TenantLookup

__all__ = [
    "DEFAULT_TENANT_SOURCE",
    "TENANT_SERVICE_KEY",
    "TenantLookupFactory",
    "build_tenant_lookup",
    "register_tenant_lookup",
    "registered_tenant_sources",
]

TENANT_SERVICE_KEY = "tenant"
"""租户与配置服务标识（自动选源的判据）。"""

DEFAULT_TENANT_SOURCE = "remote"
"""缺省租户源实现名（非租户服务）。"""


class TenantLookupFactory(Protocol):
    """租户源工厂契约：按应用装配产物构造 `TenantLookup` 实现。"""

    def __call__(
        self,
        *,
        settings: Settings,
        registry: EngineRegistry,
        cache: CacheRegion | None,
        session_factory: SessionFactory | None,
    ) -> TenantLookup:
        """构造租户源实现。

        Args:
            settings: 应用配置。
            registry: 引擎注册表（本地源用；远程源忽略）。
            cache: 缓存 Region（None 表示不缓存）。
            session_factory: 会话工厂（本地源用）。

        Returns:
            TenantLookup: 租户源实现。
        """
        ...


_LOOKUP_FACTORIES: dict[str, TenantLookupFactory] = {}


def register_tenant_lookup(name: str, factory: TenantLookupFactory) -> None:
    """登记租户源实现（幂等：同名重复登记以后登记者为准）。

    Args:
        name: 实现名（如 `local` / `remote`）。
        factory: 工厂。

    Raises:
        ConfigError: 实现名为空。
    """
    if not name:
        raise ConfigError("租户源实现名不得为空")
    _LOOKUP_FACTORIES[name] = factory


def registered_tenant_sources() -> tuple[str, ...]:
    """已登记租户源实现名（保序）。

    Returns:
        tuple[str, ...]: 实现名元组。
    """
    return tuple(_LOOKUP_FACTORIES)


def build_tenant_lookup(
    name: str,
    *,
    settings: Settings,
    registry: EngineRegistry,
    cache: CacheRegion | None,
    session_factory: SessionFactory | None,
) -> TenantLookup:
    """按名构造租户源实现（空名 → 自动选源）。

    Args:
        name: 实现名（`[tenant].source`）；空串表示自动。
        settings: 应用配置。
        registry: 引擎注册表。
        cache: 缓存 Region（None 表示不缓存）。
        session_factory: 会话工厂。

    Returns:
        TenantLookup: 租户源实现。

    Raises:
        ConfigError: 实现名未登记。
    """
    resolved = name or (DEFAULT_TENANT_SOURCE if settings.app.service != TENANT_SERVICE_KEY else "local")
    factory = _LOOKUP_FACTORIES.get(resolved)
    if factory is None:
        known = " / ".join(registered_tenant_sources()) or "（无）"
        raise ConfigError(f"租户源实现未登记：{resolved}（已登记 {known}）")
    return factory(settings=settings, registry=registry, cache=cache, session_factory=session_factory)
