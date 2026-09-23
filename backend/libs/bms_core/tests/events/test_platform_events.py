"""平台默认事件契约用例（Kiwi 2174）：声明合法 + 注册幂等 + 与已提交快照一致。"""

import json
from pathlib import Path

import pytest

from bms_core.events import platform_events
from bms_core.events.contracts import (
    EVENT_SNAPSHOT_PATH,
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
    register_platform_event_contracts,
)
from bms_core.services.module_registry import known_event_domains

REPO_ROOT = Path(__file__).resolve().parents[5]


@pytest.mark.kiwi_id(2174)
def test_platform_contracts_valid_and_unique() -> None:
    """平台默认契约全部合法（事件域已登记 / 命名合规 / 字段规格合法）且事件类型唯一。"""
    registry = EventContractRegistry()
    register_platform_event_contracts(registry)
    assert validate_event_registry(registry, domains=known_event_domains()) == ()
    assert len(PLATFORM_EVENT_CONTRACTS) == 23
    assert len({contract.event_type for contract in PLATFORM_EVENT_CONTRACTS}) == 23
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
    subscription = EventSubscription(consumer="indexer", event_type="sys.user.created", supported_majors=(1,))
    monkeypatch.setattr(platform_events, "PLATFORM_EVENT_SUBSCRIPTIONS", (subscription,))
    registry = EventContractRegistry()
    register_platform_event_contracts(registry)
    assert registry.subscriptions() == (subscription,)


@pytest.mark.kiwi_id(2174)
def test_committed_snapshot_in_sync() -> None:
    """仓库内 deploy/events/contracts.json 与现行注册表逐字节一致、兼容校验通过。"""
    registry = default_event_contract_registry()
    register_platform_event_contracts(registry)
    path = REPO_ROOT / EVENT_SNAPSHOT_PATH
    assert path.is_file()
    contracts, _ = parse_event_snapshot(json.loads(path.read_text(encoding="utf-8")))
    assert check_snapshot_compatibility(contracts, registry) == ()
    assert path.read_text(encoding="utf-8") == render_event_snapshot(registry)
