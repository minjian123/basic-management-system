"""投递器真实实现 `PollOutboxDispatcher`：轮询发件箱、经事件发布端口转发并标记。

- `dispatch_once(db_key)`：开该库事务 → `claim_pending`（同聚合队首、到期者）→ 逐条
  `EventPublisher.publish(record.to_envelope())` → 成功 `mark_delivered`、失败 `mark_failed`
  （指数退避，超限转死信）→ 提交。
- `dispatch_due()`：遍历目标库键（显式 `db_keys` 或引擎注册表活跃键），单库异常隔离。
- `setup()` 在 `enabled` 时启动后台轮询任务；`aclose()` 取消并等待（随资源统一回收）。
- 至少一次语义：发布成功但提交失败会在下轮重投；消费端按 `event_id` 幂等收敛为效果一次。
"""

import asyncio
import contextlib
from datetime import datetime

from bms_core.core.config import Settings
from bms_core.core.exceptions import OutboxDeliveryError
from bms_core.core.logging import get_logger
from bms_core.db.engine import PLATFORM_DB_KEY
from bms_core.db.registry import EngineRegistry
from bms_core.db.session import SessionFactory, session_scope
from bms_core.events.base import EventPublisher
from bms_core.metrics.base import BaseMetrics
from bms_core.outbox.base import (
    DEFAULT_BATCH_SIZE,
    DEFAULT_MAX_RETRIES,
    DEFAULT_RETRY_BACKOFF_SECONDS,
    BaseOutboxDispatcher,
    BaseOutboxStore,
    DispatchResult,
)

_LOGGER = get_logger("bms")
_METRIC_DELIVERY = "bms_outbox_delivery_total"
_METRIC_BACKLOG = "bms_outbox_backlog"


def _utc_now() -> datetime:
    """当前 UTC 时间（naive）。

    Returns:
        datetime: UTC 时间。
    """
    from datetime import UTC

    return datetime.now(UTC).replace(tzinfo=None)


class PollOutboxDispatcher(BaseOutboxDispatcher):
    """轮询投递器（发件箱 → 事件发布端口）。"""

    plugin_name = "poll"

    def __init__(
        self,
        *,
        store: BaseOutboxStore,
        publisher: EventPublisher,
        engine_registry: EngineRegistry,
        session_factory: SessionFactory | None = None,
        batch_size: int = DEFAULT_BATCH_SIZE,
        max_retries: int = DEFAULT_MAX_RETRIES,
        backoff: float = DEFAULT_RETRY_BACKOFF_SECONDS,
        db_keys: tuple[str, ...] = (),
        interval: float = 5.0,
        metrics: BaseMetrics | None = None,
        enabled: bool = False,
    ) -> None:
        """初始化。

        Args:
            store: 发件箱存储。
            publisher: 事件发布端口。
            engine_registry: 引擎注册表（按库键开会话）。
            session_factory: 异步会话工厂（缺省新建）。
            batch_size: 单轮单库取待投递上限。
            max_retries: 转死信前的最大重试次数。
            backoff: 指数退避基数（秒）。
            db_keys: 轮询库键；空 = 引擎注册表活跃键。
            interval: 后台轮询间隔（秒）。
            metrics: 指标器（可选）。
            enabled: 后台轮询开关。
        """
        self._store = store
        self._publisher = publisher
        self._engine_registry = engine_registry
        self._session_factory = session_factory
        self._batch_size = batch_size
        self._max_retries = max_retries
        self._backoff = backoff
        self._db_keys = db_keys
        self._interval = interval
        self._metrics = metrics
        self._enabled = enabled
        self._task: asyncio.Task[None] | None = None

    @property
    def enabled(self) -> bool:
        """后台轮询是否启用。

        Returns:
            bool: 启用 True。
        """
        return self._enabled

    async def dispatch_once(self, *, db_key: str = PLATFORM_DB_KEY) -> DispatchResult:
        """对单个库执行一次投递。

        Args:
            db_key: 数据源键。

        Returns:
            DispatchResult: 投递汇总。

        Raises:
            OutboxDeliveryError: 取待投递 / 编排发生非预期异常。
        """
        published = 0
        failed = 0
        dead = 0
        try:
            async with (
                session_scope(self._engine_registry, db_key=db_key, factory=self._session_factory) as session,
                session.begin(),
            ):
                records = await self._store.claim_pending(session, now=_utc_now(), limit=self._batch_size)
                for record in records:
                    try:
                        await self._publisher.publish(record.to_envelope())
                    except Exception as exc:  # 单条失败：退避重试 / 转死信，不中断其余
                        became_dead = await self._store.mark_failed(
                            session,
                            record.event_id,
                            repr(exc),
                            max_retries=self._max_retries,
                            backoff=self._backoff,
                        )
                        failed += 1
                        dead += int(became_dead)
                    else:
                        await self._store.mark_delivered(session, record.event_id)
                        published += 1
                backlog = await self._store.backlog(session)
        except OutboxDeliveryError:
            raise
        except Exception as exc:  # 开会话 / 取待投递 / 提交失败
            raise OutboxDeliveryError(f"发件箱投递失败（{db_key}）：{exc!r}") from exc
        await self._report(published=published, failed=failed, dead=dead, backlog=backlog)
        return DispatchResult(published=published, failed=failed, dead=dead, backlog=backlog)

    async def dispatch_due(self) -> DispatchResult:
        """对目标库集合各执行一次投递（单库异常隔离）。

        Returns:
            DispatchResult: 汇总结果。
        """
        keys = list(self._db_keys) or self._engine_registry.active_keys()
        total = DispatchResult()
        for key in keys:
            try:
                total = total.merge(await self.dispatch_once(db_key=key))
            except OutboxDeliveryError as exc:
                _LOGGER.warning("outbox_dispatch_failed", db_key=key, error=str(exc))
        return total

    async def setup(self) -> None:
        """启动后台轮询（`enabled` 且尚未启动时）。"""
        if self._enabled and self._task is None:
            self._task = asyncio.create_task(self._run_forever())

    async def aclose(self) -> None:
        """取消后台轮询任务（幂等）。"""
        task = self._task
        self._task = None
        if task is None:
            return
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    async def _run_forever(self) -> None:
        """后台轮询循环（取消时退出）。"""
        while True:
            try:
                await self.dispatch_due()
                await asyncio.sleep(self._interval)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # 单轮异常不终止循环
                _LOGGER.warning("outbox_poll_error", error=repr(exc))
                await asyncio.sleep(self._interval)

    async def _report(self, *, published: int, failed: int, dead: int, backlog: int) -> None:
        """上报投递计数与积压（metrics 缺省时空操作）。

        Args:
            published: 成功条数。
            failed: 失败条数。
            dead: 转死信条数。
            backlog: 待投递积压。
        """
        if self._metrics is None:
            return
        for status, value in (("delivered", published), ("failed", failed), ("dead", dead)):
            if value:
                await self._metrics.counter(_METRIC_DELIVERY, value=float(value), labels={"status": status})
        await self._metrics.gauge(_METRIC_BACKLOG, value=float(backlog))

    @classmethod
    def from_settings(
        cls,
        settings: Settings,
        *,
        store: BaseOutboxStore,
        publisher: EventPublisher,
        engine_registry: EngineRegistry,
        session_factory: SessionFactory | None = None,
        metrics: BaseMetrics | None = None,
    ) -> PollOutboxDispatcher:
        """按配置构造投递器（装配工厂用）。

        Args:
            settings: 应用配置。
            store: 发件箱存储。
            publisher: 事件发布端口。
            engine_registry: 引擎注册表。
            session_factory: 异步会话工厂。
            metrics: 指标器。

        Returns:
            PollOutboxDispatcher: 投递器实例。
        """
        outbox = settings.outbox
        return cls(
            store=store,
            publisher=publisher,
            engine_registry=engine_registry,
            session_factory=session_factory,
            batch_size=outbox.batch_size,
            max_retries=outbox.max_retries,
            backoff=outbox.retry_backoff_seconds,
            db_keys=tuple(outbox.db_keys),
            interval=outbox.poll_interval_seconds,
            metrics=metrics,
            enabled=outbox.enabled,
        )
