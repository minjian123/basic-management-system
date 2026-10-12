"""租户源装配点用例（`bms_core/db/tenant_source.py`）：登记校验、未登记快速失败与按名装配。"""

from __future__ import annotations

from typing import cast

import pytest

from bms_core.cache.base import CacheRegion
from bms_core.core.config import Settings
from bms_core.core.exceptions import ConfigError
from bms_core.db.registry import EngineRegistry
from bms_core.db.session import SessionFactory
from bms_core.db.tenant import TenantLookup
from bms_core.db.tenant_source import build_tenant_lookup, register_tenant_lookup, registered_tenant_sources


def _stub_factory(
    *,
    settings: Settings,
    registry: EngineRegistry,
    cache: CacheRegion | None,
    session_factory: SessionFactory | None,
) -> TenantLookup:
    """租户源工厂替身（回占位实现）。

    Args:
        settings: 应用配置（忽略）。
        registry: 引擎注册表（忽略）。
        cache: 缓存域（忽略）。
        session_factory: 会话工厂（忽略）。

    Returns:
        TenantLookup: 占位实现。
    """
    del settings, registry, cache, session_factory
    return cast("TenantLookup", object())


def test_tenant_lookup_registry_paths() -> None:
    """空实现名即拒；未登记实现名快速失败；已登记实现按工厂装配。"""
    with pytest.raises(ConfigError):
        register_tenant_lookup("", _stub_factory)

    with pytest.raises(ConfigError):
        build_tenant_lookup(
            "ghost",
            settings=Settings(),
            registry=cast("EngineRegistry", object()),
            cache=None,
            session_factory=None,
        )

    register_tenant_lookup("unit_lookup_stub", _stub_factory)
    assert "unit_lookup_stub" in registered_tenant_sources()
    built = build_tenant_lookup(
        "unit_lookup_stub",
        settings=Settings(),
        registry=cast("EngineRegistry", object()),
        cache=None,
        session_factory=None,
    )
    assert built is not None
