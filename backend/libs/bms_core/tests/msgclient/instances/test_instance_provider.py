"""04-6 用例之二（Kiwi 2444）：来源实现、配置优先级、映射表、TTL 与配置校验。"""

from __future__ import annotations

from collections.abc import Iterable

import pytest
from msgclient_support.rpc_retry import FakeClock

from bms_core.core.concurrent import (
    ConcurrentStableDict,
    ConcurrentStableFrozenList,
    ConcurrentStableList,
)
from bms_core.core.config import Settings
from bms_core.core.exceptions import ConfigError
from bms_core.core.service_endpoints import normalize_service_instances
from bms_core.msgclient.adapter import instances as adapter_instances
from bms_core.msgclient.adapter.instances import (
    MSG_ENDPOINT_KEY,
    ServiceCatalogInstanceProvider,
    msg_instance_addresses,
)
from bms_core.msgclient.instances import InstanceUnavailable, StaticInstanceProvider
from bms_core.servicecall.base import SERVICE_CLIENT_OPTION_BASE_URL

pytestmark = pytest.mark.kiwi_id(2444)

A = "http://a:8000"
"""实例 A。"""

B = "http://b:8000"
"""实例 B。"""


def _settings() -> Settings:
    """构造干净配置（清空端点覆盖与多实例，避免受本机配置影响）。

    Returns:
        Settings: 配置对象。
    """
    settings = Settings()
    settings.service_client.endpoints.clear()
    settings.service_client.instances.clear()
    return settings


def _set_instances(settings: Settings, key: str, values: Iterable[str]) -> None:
    """写入多实例配置（`ConcurrentStableList` 是配置字段的契约类型）。"""
    settings.service_client.instances[key] = ConcurrentStableList(values)


def _raw(
    mapping: ConcurrentStableDict[str, ConcurrentStableList[str]],
) -> ConcurrentStableDict[str, ConcurrentStableList[str]]:
    """把测试里的地址表标成配置字段的契约类型。"""
    return mapping


# ---------------------------------------------------------------------------
# 1. 配置优先级
# ---------------------------------------------------------------------------


def test_instances_win_over_endpoints_and_template() -> None:
    """多实例列表优先于端点覆盖与基址模板。"""
    settings = _settings()
    _set_instances(settings, "msg", [A, B])
    settings.service_client.endpoints["msg"] = "http://endpoint:8000"
    provider = ServiceCatalogInstanceProvider(settings=settings, clock=FakeClock())

    snapshot = provider.resolve("platform")
    assert snapshot.pool_key == MSG_ENDPOINT_KEY
    assert tuple(snapshot.addresses) == (A, B)
    assert snapshot.revision == 1


def test_endpoints_fall_back_when_instances_absent() -> None:
    """未配多实例时用端点覆盖。"""
    settings = _settings()
    settings.service_client.endpoints["msg"] = "http://endpoint:8000/"
    provider = ServiceCatalogInstanceProvider(settings=settings, clock=FakeClock())

    assert tuple(provider.resolve("platform").addresses) == ("http://endpoint:8000",)


def test_template_falls_back_when_no_override() -> None:
    """未配多实例 / 端点时按模板派生（`{service}` 取 `msg`）。"""
    settings = _settings()
    provider = ServiceCatalogInstanceProvider(settings=settings, clock=FakeClock())
    assert tuple(provider.resolve("platform").addresses) == ("http://msg:8000",)


def test_template_without_placeholder_rejects() -> None:
    """模板缺 `{service}` 占位 → `ConfigError`（装配期拒启）。"""
    settings = _settings()
    settings.service_client.options.set(SERVICE_CLIENT_OPTION_BASE_URL, "http://msg:8000")
    with pytest.raises(ConfigError, match="base_url_template"):
        msg_instance_addresses(settings)


# ---------------------------------------------------------------------------
# 2. 映射表
# ---------------------------------------------------------------------------


def test_mapping_exact_then_wildcard_then_default() -> None:
    """映射表：精确匹配 → `*` 通配 → 缺省来源键。"""
    settings = _settings()
    _set_instances(settings, "pool-a", ["http://a1:8000"])
    _set_instances(settings, "pool-b", ["http://b1:8000"])
    _set_instances(settings, "msg", ["http://msg:8000"])
    provider = ServiceCatalogInstanceProvider(
        settings=settings,
        mapping=ConcurrentStableDict({"platform": "pool-a", "*": "pool-b"}),
        clock=FakeClock(),
    )

    assert tuple(provider.resolve("platform").addresses) == ("http://a1:8000",)
    assert tuple(provider.resolve("other").addresses) == ("http://b1:8000",)


def test_default_source_key_is_msg() -> None:
    """不传映射表时所有逻辑服务都落到 `msg` 池。"""
    settings = _settings()
    _set_instances(settings, "msg", [A])
    provider = ServiceCatalogInstanceProvider(settings=settings, clock=FakeClock())
    assert provider.resolve("platform").pool_key == "msg"


# ---------------------------------------------------------------------------
# 3. TTL 与 revision
# ---------------------------------------------------------------------------


def test_snapshot_is_cached_within_ttl_and_refreshed_after() -> None:
    """TTL 内返回缓存；到期重解析；地址变化 revision +1。"""
    settings = _settings()
    _set_instances(settings, "msg", [A])
    clock = FakeClock()
    provider = ServiceCatalogInstanceProvider(settings=settings, clock=clock, ttl_ms=30_000)

    first = provider.resolve("platform")
    assert tuple(first.addresses) == (A,)
    assert first.revision == 1

    _set_instances(settings, "msg", [B])
    clock.advance(29_999)
    cached = provider.resolve("platform")
    assert tuple(cached.addresses) == (A,)
    assert cached.revision == 1

    clock.advance(1)
    refreshed = provider.resolve("platform")
    assert tuple(refreshed.addresses) == (B,)
    assert refreshed.revision == 2


def test_ttl_refresh_with_unchanged_addresses_keeps_revision() -> None:
    """快照到期重解析但地址未变：revision 不递增（避免选择器无谓清理状态）。"""
    settings = _settings()
    _set_instances(settings, "msg", [A])
    clock = FakeClock()
    provider = ServiceCatalogInstanceProvider(settings=settings, clock=clock, ttl_ms=30_000)

    first = provider.resolve("platform")
    assert first.revision == 1

    clock.advance(30_000)
    again = provider.resolve("platform")
    assert tuple(again.addresses) == (A,)
    assert again.revision == 1
    assert again.fetched_at_ms == clock.now_ms()


def test_ttl_zero_disables_cache() -> None:
    """`ttl_ms=0` 每次重解析（用例与排障用）。"""
    settings = _settings()
    _set_instances(settings, "msg", [A])
    provider = ServiceCatalogInstanceProvider(settings=settings, clock=FakeClock(), ttl_ms=0)
    assert tuple(provider.resolve("platform").addresses) == (A,)
    _set_instances(settings, "msg", [B])
    assert tuple(provider.resolve("platform").addresses) == (B,)


# ---------------------------------------------------------------------------
# 4. 校验与静态来源
# ---------------------------------------------------------------------------


def test_instances_empty_list_rejects() -> None:
    """显式空列表视为配置错误（不回落端点 / 模板）。"""
    with pytest.raises(ConfigError, match="地址列表不得为空"):
        normalize_service_instances(_raw(ConcurrentStableDict({"msg": ConcurrentStableList()})))


def test_instances_empty_service_key_rejects() -> None:
    """服务键为空拒启。"""
    with pytest.raises(ConfigError, match="服务键不得为空"):
        normalize_service_instances(_raw(ConcurrentStableDict({" ": ConcurrentStableList(["http://a:8000"])})))


def test_instances_non_http_rejects() -> None:
    """非 http(s) 地址拒启。"""
    with pytest.raises(ConfigError, match="http"):
        normalize_service_instances(_raw(ConcurrentStableDict({"msg": ConcurrentStableList(["msg:8000"])})))


def test_instances_are_trimmed_and_deduped() -> None:
    """地址去尾斜线、按插入序去重。"""
    normalized = normalize_service_instances(
        _raw(ConcurrentStableDict({" msg ": ConcurrentStableList(["http://a/", "http://a", "http://b/"])}))
    )
    assert tuple(normalized["msg"]) == ("http://a", "http://b")


def test_static_provider_trimmed_and_deduped() -> None:
    """静态来源同样去尾斜线、去重；空列表拒建。"""
    snapshot = StaticInstanceProvider(["http://a/", "http://a", "http://b"]).resolve("demo")
    assert tuple(snapshot.addresses) == ("http://a", "http://b")
    with pytest.raises(ValueError, match="至少需要一个实例地址"):
        StaticInstanceProvider([])


def test_msg_instance_addresses_priority() -> None:
    """`msg_instance_addresses` 与 provider 同一优先级。"""
    settings = _settings()
    _set_instances(settings, "msg", [A, B])
    settings.service_client.endpoints["msg"] = "http://endpoint:8000"
    assert tuple(msg_instance_addresses(settings)) == (A, B)


def test_provider_empty_addresses_is_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    """来源解析为空：`InstanceUnavailable`（防御分支，配置校验通常已拦截）。"""
    settings = _settings()
    provider = ServiceCatalogInstanceProvider(settings=settings, clock=FakeClock())

    def _empty(*_: object) -> ConcurrentStableFrozenList[str]:
        return ConcurrentStableFrozenList()

    monkeypatch.setattr(adapter_instances, "_addresses_of", _empty)
    with pytest.raises(InstanceUnavailable, match="实例来源为空"):
        provider.resolve("platform")
