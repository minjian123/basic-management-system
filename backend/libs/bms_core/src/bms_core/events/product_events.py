"""产品事件契约登记扩展点：产品侧事件契约 / 订阅向平台注册表注入的入口（R4.2）。

- 平台默认事件契约仍在 `bms_core/events/platform_events.py`（23 条），本模块**不代声明**产品契约；
- 产品服务把**本产品事件契约与订阅**经 `register_product_event_contracts()` 登记进目标注册表
  （缺省进程级默认注册表 `default_event_contract_registry()`）——产品服务应用装配时调用，
  或经 `backend/ops/event_contracts.py --product-contracts <模块路径>` 注入快照 CLI；
- 事件域须已在服务目录登记（`known_event_domains()` 取 `SERVICE_CATALOG.event_domain`），
  命名与兼容规则见 `bms_core/events/contracts.py` 与《后端开发规范》「事件与任务规范」节；
- **本期产品契约为空清单**（产品随接入补登）；空清单登记为无操作，快照与现状零漂移。
"""

from bms_core.events.contracts import (
    EventContract,
    EventContractRegistry,
    EventSubscription,
    default_event_contract_registry,
)

__all__ = [
    "PRODUCT_EVENT_CONTRACTS",
    "PRODUCT_EVENT_SUBSCRIPTIONS",
    "register_product_event_contracts",
]

PRODUCT_EVENT_CONTRACTS: tuple[EventContract, ...] = ()
"""产品事件契约（bms 侧本期为空；产品侧经本节登记扩展点注入）。"""

PRODUCT_EVENT_SUBSCRIPTIONS: tuple[EventSubscription, ...] = ()
"""产品事件订阅声明（bms 侧本期为空；产品侧经本节登记扩展点注入）。"""


def register_product_event_contracts(
    contracts: tuple[EventContract, ...] = PRODUCT_EVENT_CONTRACTS,
    *,
    subscriptions: tuple[EventSubscription, ...] = PRODUCT_EVENT_SUBSCRIPTIONS,
    registry: EventContractRegistry | None = None,
) -> None:
    """把产品事件契约与订阅登记进目标注册表（幂等；同值重复登记无操作）。

    Args:
        contracts: 产品事件契约清单（缺省 bms 侧空清单）。
        subscriptions: 产品事件订阅声明清单（缺省 bms 侧空清单）。
        registry: 目标注册表（缺省进程级默认注册表）。
    """
    target = registry or default_event_contract_registry()
    for contract in contracts:
        target.register(contract)
    for subscription in subscriptions:
        target.register_subscription(subscription)
