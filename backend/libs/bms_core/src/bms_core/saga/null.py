"""Saga 执行器缺省实现：`NullSagaExecutor`（调用即抛，不静默降级、不裸执行）。

Saga 用于**部分完成业务上不可接受**的场景——空实现若跳过动作或绕过幂等 / 补偿语义，
会静默破坏一致性；故缺省实现一律抛 `ConfigError`（40001），提示配置真实实现
（`[saga].provider = "choreography"`）。
"""

from typing import NoReturn

from bms_core.core.capability import BaseNullObject
from bms_core.core.exceptions import ConfigError
from bms_core.db.sync import DbSession
from bms_core.events.base import EventEnvelope
from bms_core.saga.base import BaseSagaExecutor, SagaAction, SagaDefinition, SagaStep, SagaStepOutcome

__all__ = ["NullSagaExecutor"]


class NullSagaExecutor(BaseSagaExecutor, BaseNullObject):
    """占位 Saga 执行器：三态调用均抛配置错误（未配置真实实现；不产生副作用）。"""

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
        """拒绝执行预占态（未配置真实实现）。

        Args:
            session: 本地事务会话。
            definition: Saga 流程定义。
            step: Saga 步骤。
            trigger_event_id: 触发事件 ID。
            action: 预占动作。
            emit: 需随事务发出的事件。

        Raises:
            ConfigError: 恒抛（Saga 执行器未配置）。
        """
        self._unavailable()

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
        """拒绝执行确认态（未配置真实实现）。

        Args:
            session: 本地事务会话。
            definition: Saga 流程定义。
            step: Saga 步骤。
            trigger_event_id: 触发事件 ID。
            action: 确认动作。
            emit: 需随事务发出的事件。

        Raises:
            ConfigError: 恒抛（Saga 执行器未配置）。
        """
        self._unavailable()

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
        """拒绝执行取消态（未配置真实实现）。

        Args:
            session: 本地事务会话。
            definition: Saga 流程定义。
            step: Saga 步骤。
            trigger_event_id: 触发事件 ID。
            action: 取消 / 补偿动作。
            emit: 需随事务发出的事件。

        Raises:
            ConfigError: 恒抛（Saga 执行器未配置）。
        """
        self._unavailable()

    def _unavailable(self) -> NoReturn:
        """抛配置错误（Saga 执行器未配置）。

        Raises:
            ConfigError: 恒抛（`40001`）。
        """
        raise ConfigError('Saga 执行器未配置（请设置 [saga].provider = "choreography"）')
