"""审计事件发射器：平台库短会话写发件箱（06_01）。

- 用途：请求审计中间件与身份服务登录审计共用——事件统一经**本服务平台库**的 `sys_outbox`
  入账，由投递器转发到 RocketMQ；无 MQ 时事件留在发件箱（不丢）。
- 失败口径：任何异常只记 `audit_emit_failed` 告警并返回 False，**不得影响业务响应 / 登录结果**。
- 事务边界：本类自开短事务（`session.begin()`），写完即提交；不参与业务事务（捕获发生在响应后）。
"""

from __future__ import annotations

from typing import cast

from bms_core.core.config import Settings
from bms_core.core.logging import get_logger
from bms_core.core.plugin import resolve_plugin
from bms_core.core.roots import BaseFrameworkObject
from bms_core.db.keys import PLATFORM_DB_KEY
from bms_core.db.registry import EngineRegistry
from bms_core.db.session import SessionFactory, session_scope
from bms_core.events.base import EventEnvelope
from bms_core.outbox.base import BaseOutboxStore

__all__ = ["AuditEventEmitter"]

_LOGGER = get_logger("bms.audit")


class AuditEventEmitter(BaseFrameworkObject):
    """审计事件发射器（平台库短会话；失败不抛出）。"""

    def __init__(
        self,
        *,
        registry: EngineRegistry,
        session_factory: SessionFactory,
        settings: Settings,
        db_key: str = PLATFORM_DB_KEY,
    ) -> None:
        """初始化。

        Args:
            registry: 应用级引擎注册表。
            session_factory: 会话工厂（异步方言路径）。
            settings: 应用配置（取发件箱存储实现）。
            db_key: 数据源键（缺省本服务平台库）。
        """
        self._registry = registry
        self._session_factory = session_factory
        self._db_key = db_key
        self._store = cast(
            "BaseOutboxStore",
            resolve_plugin(
                "outbox_store",
                settings.outbox_store.provider,
                expected_version=BaseOutboxStore.contract_version,
            ),
        )

    async def emit(self, event: EventEnvelope) -> bool:
        """写一条审计事件到发件箱（失败只告警）。

        Args:
            event: 审计事件信封。

        Returns:
            bool: 写入成功 True；失败 False（业务不受影响）。
        """
        try:
            async with (
                session_scope(self._registry, db_key=self._db_key, factory=self._session_factory) as session,
                session.begin(),
            ):
                await self._store.enqueue(session, event)
        except Exception as exc:  # 审计落库失败不得影响业务（降级口径见架构 16 §8）
            _LOGGER.warning("audit_emit_failed", event_type=event.event_type, error=repr(exc))
            return False
        return True
