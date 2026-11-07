"""审计事件发射器：平台库短会话写发件箱（06_01）。

- 用途：请求审计中间件与身份服务登录审计共用——事件统一经**本服务平台库**的 `sys_outbox`
  入账，由投递器转发到 RocketMQ；无 MQ 时事件留在发件箱（不丢）。
- 失败口径（07D `02_04` 分档）：
  - `required=False`（缺省）：只记告警 + 指标（`bms_audit_emit_failed_total`）并返回 False，
    **不得影响业务响应 / 登录结果**；
  - `required=True`（强审计操作，见 `audit_class_for()`）：记 `ERROR` 后抛 `InternalError`
    ——需强审计的操作「失败即失败」，不静默丢弃。
- 事务边界：本类自开短事务（`session.begin()`），写完即提交；不参与业务事务（捕获发生在响应后）。
"""

from __future__ import annotations

from typing import cast

from bms_core.core.concurrent import ConcurrentStableDict
from bms_core.core.config import Settings
from bms_core.core.exceptions import InternalError
from bms_core.core.logging import get_logger
from bms_core.core.plugin import resolve_plugin
from bms_core.core.roots import BaseFrameworkObject
from bms_core.db.keys import PLATFORM_DB_KEY
from bms_core.db.registry import EngineRegistry
from bms_core.db.session import SessionFactory, session_scope
from bms_core.events.base import EventEnvelope
from bms_core.metrics.base import BaseMetrics
from bms_core.outbox.base import BaseOutboxStore

__all__ = ["METRIC_AUDIT_EMIT_FAILED", "AuditEventEmitter"]

_LOGGER = get_logger("bms.audit")

METRIC_AUDIT_EMIT_FAILED = "bms_audit_emit_failed_total"
"""审计写入失败次数（标签 `event_type`；强审计失败同时抛错）。"""


class AuditEventEmitter(BaseFrameworkObject):
    """审计事件发射器（平台库短会话；失败分档）。"""

    def __init__(
        self,
        *,
        registry: EngineRegistry,
        session_factory: SessionFactory,
        settings: Settings,
        db_key: str = PLATFORM_DB_KEY,
        metrics: BaseMetrics | None = None,
    ) -> None:
        """初始化。

        Args:
            registry: 应用级引擎注册表。
            session_factory: 会话工厂（异步方言路径）。
            settings: 应用配置（取发件箱存储实现）。
            db_key: 数据源键（缺省本服务平台库）。
            metrics: 指标器（可选；写入失败时计数）。
        """
        self._registry = registry
        self._session_factory = session_factory
        self._db_key = db_key
        self._metrics = metrics
        self._store = cast(
            "BaseOutboxStore",
            resolve_plugin(
                "outbox_store",
                settings.outbox_store.provider,
                expected_version=BaseOutboxStore.contract_version,
            ),
        )

    async def emit(self, event: EventEnvelope, *, required: bool = False) -> bool:
        """写一条审计事件到发件箱（失败分档处置）。

        Args:
            event: 审计事件信封。
            required: 是否强审计（`True` 时写入失败抛 `InternalError`，业务随之失败）。

        Returns:
            bool: 写入成功 True；失败 False（`required=True` 时不返回，直接抛错）。

        Raises:
            InternalError: 强审计写入失败（10000 / 500）。
        """
        try:
            async with (
                session_scope(self._registry, db_key=self._db_key, factory=self._session_factory) as session,
                session.begin(),
            ):
                await self._store.enqueue(session, event)
        except Exception as exc:
            if required:
                _LOGGER.error(
                    "audit_emit_failed",
                    event_type=event.event_type,
                    required=True,
                    error=repr(exc),
                )
                raise InternalError("审计写入失败（该操作要求强审计，业务已中止）") from exc
            _LOGGER.warning("audit_emit_failed", event_type=event.event_type, error=repr(exc))
            await self._count_failure(event.event_type)
            return False
        return True

    async def _count_failure(self, event_type: str) -> None:
        """失败计数（未装配指标器时跳过）。

        Args:
            event_type: 事件类型（标签值）。
        """
        if self._metrics is None:
            return
        await self._metrics.counter(METRIC_AUDIT_EMIT_FAILED, labels=ConcurrentStableDict({"event_type": event_type}))
