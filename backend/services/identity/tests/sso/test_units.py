"""SSO 覆盖补口（Kiwi 2197）：私有分支直调（配置解析 / 派生回退 / 空值边界）。"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import cast

import pytest

from bms_core.core.concurrent import ConcurrentStableDict
from bms_core.core.config import Settings
from bms_core.core.exceptions import ConfigError, SsoCallbackError, TenantNotFoundError
from bms_core.db.tenant import TenantLookup
from bms_core.idp.state.memory import MemoryIdpStateStore
from bms_core.lock.null import NullDistributedLock
from bms_core.outbox.null import NullOutboxStore
from bms_core.ratelimit.memory import MemoryRateLimiter
from bms_identity.api.sso import _resolve_sso_tenant  # pyright: ignore[reportPrivateUsage]
from bms_identity.services.org_client import OrgCredentialClient
from bms_identity.services.provider_registry import (
    ProviderRegistry,
    _normalize_updated_at,  # pyright: ignore[reportPrivateUsage]
    _parse_config,  # pyright: ignore[reportPrivateUsage]
    _resolve_redirect_uri,  # pyright: ignore[reportPrivateUsage]
)
from bms_identity.services.sso import (  # pyright: ignore[reportPrivateUsage]
    SsoService,
    _build_service_url,  # pyright: ignore[reportPrivateUsage]
    _flow_from_payload,  # pyright: ignore[reportPrivateUsage]
)


@pytest.mark.kiwi_id(2199)
def test_build_service_url_edge() -> None:
    """CAS service 构造边界：空回调地址回退空串；含查询串以 `&` 追加；state 转义。"""
    assert _build_service_url("", "s") == ""
    assert _build_service_url("http://cb.test/cb?x=1", "s") == "http://cb.test/cb?x=1&state=s"
    assert _build_service_url("http://cb.test/cb", "a b") == "http://cb.test/cb?state=a%20b"


@pytest.mark.kiwi_id(2197)
def test_provider_registry_helper_branches() -> None:
    """配置解析 / 回调派生 / 更新时间规范化的边界分支。"""
    with pytest.raises(ConfigError):
        _parse_config("{not-json", "keycloak")
    with pytest.raises(ConfigError):
        _parse_config("[1,2]", "keycloak")
    assert _parse_config(None, "keycloak") == {}
    assert _resolve_redirect_uri(ConcurrentStableDict(), "keycloak", "") == ""
    assert (
        _resolve_redirect_uri(ConcurrentStableDict(), "keycloak", "http://cb.test")
        == "http://cb.test/api/v1/auth/sso/keycloak/callback"
    )
    assert _normalize_updated_at(None) == ""
    moment = datetime(2026, 1, 1, tzinfo=UTC)
    assert _normalize_updated_at(moment) == moment.isoformat()
    assert _normalize_updated_at("2026-01-01T00:00:00") == "2026-01-01T00:00:00"
    ProviderRegistry().clear()


@pytest.mark.kiwi_id(2197)
async def test_sso_service_rate_limit_skip_without_ip() -> None:
    """IP 缺失时 authorize / callback 限流直接跳过（内部网络口径）。"""
    service = SsoService(
        state_store=MemoryIdpStateStore(),
        rate_limiter=MemoryRateLimiter(),
        org_client=cast("OrgCredentialClient", object()),
        provider_registry=ProviderRegistry(),
        sso_settings=Settings().sso,
        lock=NullDistributedLock(),
        outbox_store=NullOutboxStore(),
    )
    await service._enforce_authorize_rate_limit("demo", "keycloak", None)  # pyright: ignore[reportPrivateUsage]
    await service._enforce_callback_rate_limit(None)  # pyright: ignore[reportPrivateUsage]


@pytest.mark.kiwi_id(2197)
def test_flow_payload_invalid_structure() -> None:
    """流程载荷结构非法（非对象 / 缺键）统一 20052。"""
    with pytest.raises(SsoCallbackError):
        _flow_from_payload([1, 2])
    with pytest.raises(SsoCallbackError):
        _flow_from_payload({"tenant": "demo"})


@pytest.mark.kiwi_id(2197)
async def test_resolve_sso_tenant_requires_any_source() -> None:
    """无租户参数且无上下文时 80001（端点内防御分支）。"""
    with pytest.raises(TenantNotFoundError):
        await _resolve_sso_tenant(None, None, cast("TenantLookup", object()))
