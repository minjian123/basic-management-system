"""Saga 协同式执行器真实实现：`ChoreographySagaExecutor`。

- 三态（`try` / `confirm` / `cancel`）统一走「幂等登记 → 动作 → （可选）发件箱事件」：
  幂等经 `ProcessedEventStore`（`consumer = saga:{定义}:{步骤}:{kind}`）与副作用同一本地事务；
  命中即 `executed=false` 跳过，重复投递不重复执行副作用。
- 动作异常整体回滚（幂等登记与已写事件一并撤销），异常上抛由消费侧重试 / 转死信；
  补偿动作（`cancel`）本身仍须业务幂等（如释放预占用绝对语义）。
- 事件经事务性发件箱同事务写入（业务不直连 MQ），`aggregate_key = saga_id` 保证同 Saga 有序。
"""

from bms_core.db.sync import DbSession
from bms_core.events.base import EventEnvelope
from bms_core.outbox.base import BaseOutboxStore
from bms_core.outbox.consumed import ProcessedEventStore
from bms_core.saga.base import (
    SAGA_STEP_CANCEL,
    SAGA_STEP_CONFIRM,
    SAGA_STEP_TRY,
    BaseSagaExecutor,
    SagaAction,
    SagaDefinition,
    SagaStep,
    SagaStepOutcome,
    build_saga_consumer,
)

__all__ = ["ChoreographySagaExecutor"]


class ChoreographySagaExecutor(BaseSagaExecutor):
    """协同式 Saga 执行器（各服务订事件、各自补偿；无中心状态，编排式运行时按判据后置）。"""

    plugin_name: str = "choreography"

    def __init__(self, outbox_store: BaseOutboxStore) -> None:
        """初始化。

        Args:
            outbox_store: 事务性发件箱存储（`emit` 事件同事务写入）。
        """
        self._outbox_store = outbox_store

    async def try_step(
        self,
        session: DbSession,
        *,
        definition: SagaDefinition,
        step: SagaStep,
        trigger_event_id: str,
        action: SagaAction,
        emit: EventEnvelope | None = None,
    ) -> SagaStepOutcome:
        """执行预占态（幂等 + 本地事务 + 可选发件箱事件）。

        Args:
            session: 本地事务会话。
            definition: Saga 流程定义。
            step: Saga 步骤。
            trigger_event_id: 触发事件 ID（幂等键）。
            action: 预占动作。
            emit: 需随事务发出的事件（缺省不发）。

        Returns:
            SagaStepOutcome: 步骤执行结果。
        """
        return await self._run(
            session,
            kind=SAGA_STEP_TRY,
            definition=definition,
            step=step,
            trigger_event_id=trigger_event_id,
            action=action,
            emit=emit,
        )

    async def confirm_step(
        self,
        session: DbSession,
        *,
        definition: SagaDefinition,
        step: SagaStep,
        trigger_event_id: str,
        action: SagaAction,
        emit: EventEnvelope | None = None,
    ) -> SagaStepOutcome:
        """执行确认态（幂等口径同预占态）。

        Args:
            session: 本地事务会话。
            definition: Saga 流程定义。
            step: Saga 步骤。
            trigger_event_id: 触发事件 ID（幂等键）。
            action: 确认动作。
            emit: 需随事务发出的事件（缺省不发）。

        Returns:
            SagaStepOutcome: 步骤执行结果。
        """
        return await self._run(
            session,
            kind=SAGA_STEP_CONFIRM,
            definition=definition,
            step=step,
            trigger_event_id=trigger_event_id,
            action=action,
            emit=emit,
        )

    async def cancel_step(
        self,
        session: DbSession,
        *,
        definition: SagaDefinition,
        step: SagaStep,
        trigger_event_id: str,
        action: SagaAction,
        emit: EventEnvelope | None = None,
    ) -> SagaStepOutcome:
        """执行取消态（幂等补偿）。

        Args:
            session: 本地事务会话。
            definition: Saga 流程定义。
            step: Saga 步骤。
            trigger_event_id: 触发事件 ID（幂等键）。
            action: 取消 / 补偿动作。
            emit: 需随事务发出的事件（缺省不发）。

        Returns:
            SagaStepOutcome: 步骤执行结果。
        """
        return await self._run(
            session,
            kind=SAGA_STEP_CANCEL,
            definition=definition,
            step=step,
            trigger_event_id=trigger_event_id,
            action=action,
            emit=emit,
        )

    async def _run(
        self,
        session: DbSession,
        *,
        kind: str,
        definition: SagaDefinition,
        step: SagaStep,
        trigger_event_id: str,
        action: SagaAction,
        emit: EventEnvelope | None,
    ) -> SagaStepOutcome:
        """三态统一执行：幂等登记 → 动作 → （可选）发件箱事件。

        Args:
            session: 本地事务会话。
            kind: 步骤态。
            definition: Saga 流程定义。
            step: Saga 步骤。
            trigger_event_id: 触发事件 ID。
            action: 步骤动作。
            emit: 需随事务发出的事件。

        Returns:
            SagaStepOutcome: 步骤执行结果。

        Raises:
            ParamError: 该态事件类型未定义。
        """
        event_type = step.event_type_of(kind)
        consumer = build_saga_consumer(definition.key, step.name, kind)
        first = await ProcessedEventStore(session).mark(
            consumer=consumer,
            event_id=trigger_event_id,
            event_type=event_type,
        )
        if not first:
            return SagaStepOutcome(kind=kind, step=step.name, executed=False, event_id=trigger_event_id)
        await action(session)
        if emit is not None:
            await self._outbox_store.enqueue(session, emit)
        return SagaStepOutcome(kind=kind, step=step.name, executed=True, event_id=trigger_event_id)
