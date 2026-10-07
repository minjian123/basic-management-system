"""产品事件契约登记扩展点测试（Kiwi 2250）：空清单 / 注入 / 幂等 / 事件域校验。"""

import pytest

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableSet
from bms_core.events.contracts import (
    EventContract,
    EventContractRegistry,
    EventFieldSpec,
    EventSubscription,
    validate_event_registry,
)
from bms_core.events.product_events import (
    PRODUCT_EVENT_CONTRACTS,
    PRODUCT_EVENT_SUBSCRIPTIONS,
    register_product_event_contracts,
)
from bms_core.services.module_registry import known_event_domains

pytestmark = pytest.mark.kiwi_id(2250)

_CONTRACT = EventContract(
    event_type="pur.order.created",
    description="采购订单创建",
    fields=ConcurrentStableDict({"order_id": EventFieldSpec(type="string", required=True)}),
)


def test_default_product_contracts_empty() -> None:
    """bms 侧产品契约为空清单；空清单登记为无操作（快照零漂移前提）。"""
    assert PRODUCT_EVENT_CONTRACTS == ()
    assert PRODUCT_EVENT_SUBSCRIPTIONS == ()
    registry = EventContractRegistry()
    register_product_event_contracts(registry=registry)
    assert registry.contracts() == ()
    assert registry.subscriptions() == ()


def test_register_contracts_and_subscriptions() -> None:
    """产品契约与订阅经登记入口注入注册表，并通过事件域校验（产品事件域须已登记）。"""
    registry = EventContractRegistry()
    subscription = EventSubscription(consumer="mdm.inbox", event_type="pur.order.created", supported_majors=(1,))
    register_product_event_contracts((_CONTRACT,), subscriptions=(subscription,), registry=registry)
    assert registry.contracts() == (_CONTRACT,)
    assert registry.subscriptions() == (subscription,)
    assert validate_event_registry(registry, domains=known_event_domains()) == ()


def test_registration_is_idempotent() -> None:
    """同值重复登记无操作（装配与快照 CLI 可重复调用）。"""
    registry = EventContractRegistry()
    register_product_event_contracts((_CONTRACT,), registry=registry)
    register_product_event_contracts((_CONTRACT,), registry=registry)
    assert registry.contracts() == (_CONTRACT,)


def test_unregistered_event_domain_rejected() -> None:
    """事件域未登记即校验拒绝（域来源为服务目录 `SERVICE_CATALOG.event_domain`）。"""
    registry = EventContractRegistry()
    register_product_event_contracts((_CONTRACT,), registry=registry)
    errors = validate_event_registry(registry, domains=ConcurrentStableSet(["sys"]))
    assert any("事件域未登记：pur" in error for error in errors)
