"""审计链消费组声明（`audit-chain`）：操作 / 登录日志事件 → 分片表链式落库（06_01）。

- 组名 `audit-chain`（装载时补 `[event_consumer].group_prefix` 前缀）；
- `ordered=True`：全组串行（架构 16 §5「强有序组退化为全组串行」），保证同租户 `prev_hash` 衔接不乱序；
- 处理器每次启动构造独立实例；写库用平台库短事务（`PLATFORM_DB_KEY`）；
- 哈希链实现按 `[hash_chain].provider` 解析（平台服务缺省置 `sha256`，测试可注入）。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import cast

from bms_core.audit.events import LOGIN_LOG_EVENT, OPERATION_LOG_EVENT
from bms_core.audit.hashchain import BaseHashChain
from bms_core.audit.sha256 import Sha256HashChain  # 导入即登记 sha256 链插件（零参类自动收集）
from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.config import get_settings
from bms_core.core.plugin import resolve_plugin
from bms_core.db.engine import EngineFactory
from bms_core.db.keys import PLATFORM_DB_KEY
from bms_core.db.registry import EngineRegistry
from bms_core.db.session import SessionFactory, session_scope
from bms_core.events.base import EventConsumer, EventEnvelope
from bms_core.events.consumer_records import EventConsumerRecord
from bms_platform.domains.log.services.writer import AuditLogWriter

__all__ = [
    "AUDIT_CHAIN_GROUP",
    "AuditLogConsumer",
    "event_consumer_records",
    "reset_audit_registry",
]

AUDIT_CHAIN_GROUP = "audit-chain"
"""消费组名（装载时补前缀，如 `bms-audit-chain`）。"""

_AUDIT_EVENTS = (OPERATION_LOG_EVENT, LOGIN_LOG_EVENT)
"""审计链组订阅的事件。"""

_registry_cache: EngineRegistry | None = None
"""懒建平台库引擎注册表（消费处理器无请求态，与作业监控同口径）。"""

_chain_cache: BaseHashChain | None = None
"""哈希链实例缓存（进程内单例）。"""


def _audit_registry() -> EngineRegistry:
    """取（懒建）平台库引擎注册表。

    Returns:
        EngineRegistry: 引擎注册表。
    """
    global _registry_cache
    if _registry_cache is None:
        _registry_cache = EngineRegistry(EngineFactory(get_settings()))
    return _registry_cache


def _hash_chain() -> BaseHashChain:
    """解析哈希链实现（`[hash_chain].provider`；缺省回落 null）。

    Returns:
        BaseHashChain: 哈希链实例。
    """
    global _chain_cache
    if _chain_cache is None:
        settings = get_settings()
        _chain_cache = cast(
            "BaseHashChain",
            resolve_plugin(
                "hash_chain",
                settings.hash_chain.provider or Sha256HashChain.plugin_name,
                expected_version=BaseHashChain.contract_version,
            ),
        )
    return _chain_cache


def reset_audit_registry() -> None:
    """清空懒建注册表与链缓存（测试隔离用）。"""
    global _registry_cache, _chain_cache
    _registry_cache = None
    _chain_cache = None


class AuditLogConsumer(EventConsumer):
    """单事件处理器：把一条审计事件写入对应分片表。"""

    def __init__(self, event_type: str) -> None:
        """初始化。

        Args:
            event_type: 订阅的事件类型。
        """
        self._event_type = event_type

    @property
    def event_type(self) -> str:
        """事件类型（订阅主题）。

        Returns:
            str: 事件类型。
        """
        return self._event_type

    async def consume(self, event: EventEnvelope) -> None:
        """消费一条审计事件（同事务内建表兜底 + 链计算 + 写入）。

        Args:
            event: 审计事件信封。
        """
        async with (
            session_scope(_audit_registry(), db_key=PLATFORM_DB_KEY, factory=SessionFactory()) as session,
            session.begin(),
        ):
            await AuditLogWriter(session, _hash_chain()).write(event)


def event_consumer_records() -> ConcurrentStableList[EventConsumerRecord]:
    """平台自持的审计链消费组声明（两条事件各一条记录）。

    Returns:
        ConcurrentStableList[EventConsumerRecord]: 消费组声明。
    """
    records: ConcurrentStableList[EventConsumerRecord] = ConcurrentStableList()
    for event_type in _AUDIT_EVENTS:
        records.add(
            EventConsumerRecord(
                consumer=AUDIT_CHAIN_GROUP,
                event_type=event_type,
                handler_factory=_factory(event_type),
                ordered=True,
                description=f"审计链落库：{event_type} → 按月分片 + 哈希链",
            )
        )
    return records


def _factory(event_type: str) -> Callable[[], AuditLogConsumer]:
    """构造处理器工厂（每次返回独立实例）。

    Args:
        event_type: 订阅的事件类型。

    Returns:
        Callable[[], AuditLogConsumer]: 零参工厂。
    """

    def _build() -> AuditLogConsumer:
        return AuditLogConsumer(event_type)

    return _build
