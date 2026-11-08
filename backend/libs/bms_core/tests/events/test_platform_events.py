"""平台默认事件契约用例（Kiwi 2174）：声明合法 + 注册幂等 + 与已提交快照一致。"""

import json
from pathlib import Path

import pytest

from bms_core.core.concurrent import ConcurrentStableFrozenList, ConcurrentStableList, ConcurrentStableSet
from bms_core.events import platform_events
from bms_core.events.contracts import (
    EVENT_SNAPSHOT_PATH,
    RESERVED_PAYLOAD_KEYS,
    EventContractRegistry,
    EventSubscription,
    check_snapshot_compatibility,
    default_event_contract_registry,
    parse_event_snapshot,
    render_event_snapshot,
    validate_event_registry,
)
from bms_core.events.platform_events import (
    PLATFORM_EVENT_CONTRACTS,
    PLATFORM_EVENT_SUBSCRIPTIONS,
    TENANT_ID_PAYLOAD_KEY,
    register_platform_event_contracts,
)
from bms_core.services.module_registry import known_event_domains

REPO_ROOT = Path(__file__).resolve().parents[5]


@pytest.mark.kiwi_id(2174)
def test_platform_contracts_valid_and_unique() -> None:
    """平台默认契约全部合法（事件域已登记 / 命名合规 / 字段规格合法）且事件类型唯一。"""
    registry = EventContractRegistry()
    register_platform_event_contracts(registry)
    assert validate_event_registry(registry, domains=ConcurrentStableSet(known_event_domains())) == ()
    assert len(PLATFORM_EVENT_CONTRACTS) == 33
    assert len({contract.event_type for contract in PLATFORM_EVENT_CONTRACTS}) == 33
    assert PLATFORM_EVENT_SUBSCRIPTIONS == ()


@pytest.mark.kiwi_id(2174)
def test_platform_registration_idempotent() -> None:
    """同值重复登记无操作（装配期多次调用安全）。"""
    registry = EventContractRegistry()
    register_platform_event_contracts(registry)
    register_platform_event_contracts(registry)
    assert len(registry.contracts()) == len(PLATFORM_EVENT_CONTRACTS)


@pytest.mark.kiwi_id(2174)
def test_platform_subscriptions_registered(monkeypatch: pytest.MonkeyPatch) -> None:
    """订阅声明随平台登记入口一并登记（本期为空集，机制经补丁验证）。"""
    subscription = EventSubscription(
        consumer="indexer", event_type="sys.user.created", supported_majors=ConcurrentStableFrozenList((1,))
    )
    monkeypatch.setattr(platform_events, "PLATFORM_EVENT_SUBSCRIPTIONS", (subscription,))
    registry = EventContractRegistry()
    register_platform_event_contracts(registry)
    assert registry.subscriptions() == (subscription,)


@pytest.mark.kiwi_id(2218)
def test_tenant_events_payload_key_and_version() -> None:
    """租户事件负载键改雪花 id：族 2.2.0、`tenant_id` 必填、无 `tenant_code`；`version` 可选。

    `2.2.0` 只给 `tenant.deleted` 增可选 `purge_at` / `reason`（任务 `04_03` 两步注销），
    其余三条载荷不变；`tenant.purged` 独立 `1.0.0`。
    """
    contracts = {contract.event_type: contract for contract in PLATFORM_EVENT_CONTRACTS}
    for event_type in ("tenant.created", "tenant.suspended", "tenant.activated", "tenant.deleted"):
        contract = contracts[event_type]
        assert contract.version == "2.2.0"
        assert "tenant_id" in contract.fields
        assert "tenant_code" not in contract.fields
        assert contract.fields["tenant_id"].type == "string"
        assert contract.fields["tenant_id"].required is True
        assert contract.fields["version"].type == "integer"
        assert contract.fields["version"].required is False
    deleted = contracts["tenant.deleted"]
    assert deleted.fields["purge_at"].required is False and deleted.fields["reason"].required is False
    for event_type in ("tenant.created", "tenant.suspended", "tenant.activated"):
        assert "purge_at" not in contracts[event_type].fields
    purged = contracts["tenant.purged"]
    assert purged.version == "1.0.0"
    assert purged.fields["tenant_id"].required is True and purged.fields["db_key"].required is True
    assert purged.fields["dropped_services"].required is False and purged.fields["failed_services"].required is False
    assert TENANT_ID_PAYLOAD_KEY == "tenant_id"
    assert "tenant_id" not in RESERVED_PAYLOAD_KEYS


@pytest.mark.kiwi_id(2174)
@pytest.mark.kiwi_id(2218)
def test_committed_snapshot_in_sync() -> None:
    """仓库内 deploy/events/contracts.json 与现行注册表逐字节一致、兼容校验通过。"""
    registry = default_event_contract_registry()
    register_platform_event_contracts(registry)
    path = REPO_ROOT / EVENT_SNAPSHOT_PATH
    assert path.is_file()
    contracts, _ = parse_event_snapshot(json.loads(path.read_text(encoding="utf-8")))
    assert check_snapshot_compatibility(ConcurrentStableList(contracts), registry) == ()
    assert path.read_text(encoding="utf-8") == render_event_snapshot(registry)
