"""Saga / 补偿能力域：协同式参与者执行器契约与数据契约（TCC 三态）。

- **适用判据**（《架构设计 · 服务间通信与分布式一致性》「跨服务一致性（Saga / 补偿）」节）：
  副作用可重复 / 单写者持有不变量 / 顺序无关的场景用「本地事务 + 事件 + 幂等」即可；
  **跨 ≥2 服务且部分完成业务上不可接受**（资金 / 权益可能重复消耗、长流程含人工审批）才用
  Saga / 补偿。短流程用**协同式**（各服务订事件、各自补偿）——本基座即协同式；
  长流程（≥4~5 步、含超时 / 人工节点）评估引入编排式运行时（Temporal，按判据再引入）。
- **TCC 三态**：`try`（预占）→ 全链成功由后续 `confirm`（确认）收口；失败由 `cancel`（取消，
  即幂等补偿）反向补偿。三态动作经 `ProcessedEventStore`（`consumer = saga:{定义}:{步骤}:{kind}`）
  幂等，与副作用**同一本地事务**；`emit` 事件经事务性发件箱同事务发出、`aggregate_key = saga_id`
  保证同 Saga 有序。
- **端口** `BaseSagaExecutor`（插件键 `saga_executor`）：`try_step` / `confirm_step` / `cancel_step`
  + 提供者 `get_saga_executor`；真实实现 `ChoreographySagaExecutor`（`choreography`）、
  缺省 `NullSagaExecutor`（调用即抛配置错误，不静默降级）。
"""

import re
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import cast

from fastapi import Request

from bms_core.core.base import BaseObject
from bms_core.core.config import Settings
from bms_core.core.exceptions import ParamError
from bms_core.core.plugin import DEFAULT_CONTRACT_VERSION, NULL_PLUGIN_NAME, BasePluggable, resolve_plugin
from bms_core.db.sync import DbSession
from bms_core.events.base import EventEnvelope
from bms_core.events.contracts import EVENT_TYPE_RE, EventContractRegistry

__all__ = [
    "SAGA_CONSUMER_PREFIX",
    "SAGA_KEY_RE",
    "SAGA_STEP_CANCEL",
    "SAGA_STEP_CONFIRM",
    "SAGA_STEP_KINDS",
    "SAGA_STEP_TRY",
    "BaseSagaExecutor",
    "SagaAction",
    "SagaDefinition",
    "SagaStep",
    "SagaStepOutcome",
    "build_saga_consumer",
    "build_saga_event",
    "get_saga_executor",
    "validate_saga_definition",
]

SAGA_STEP_TRY = "try"
"""TCC 预占态。"""

SAGA_STEP_CONFIRM = "confirm"
"""TCC 确认态。"""

SAGA_STEP_CANCEL = "cancel"
"""TCC 取消态（即幂等补偿）。"""

SAGA_STEP_KINDS: tuple[str, ...] = (SAGA_STEP_TRY, SAGA_STEP_CONFIRM, SAGA_STEP_CANCEL)
"""Saga 步骤态清单（TCC 三态）。"""

SAGA_CONSUMER_PREFIX = "saga"
"""Saga 幂等消费标识前缀（`saga:{定义}:{步骤}:{kind}`）。"""

SAGA_KEY_RE = re.compile(r"^[a-z][a-z0-9_]*$")
"""Saga 定义键 / 步骤名格式（小写下划线）。"""

SagaAction = Callable[[DbSession], Awaitable[None]]
"""步骤动作：在调用方本地事务内执行（幂等由执行器经 `ProcessedEventStore` 承载）。"""


@dataclass(frozen=True)
class SagaStep(BaseObject):
    """Saga 步骤：TCC 三态事件类型的声明式配对。"""

    name: str
    """步骤名（定义内唯一，小写下划线）。"""

    try_event_type: str
    """预占态事件类型。"""

    confirm_event_type: str | None = None
    """确认态事件类型（无确认步骤可为空）。"""

    cancel_event_type: str | None = None
    """取消态事件类型（无补偿动作可为空）。"""

    description: str = ""
    """说明（中文）。"""

    def event_type_of(self, kind: str) -> str:
        """取某态事件类型（未定义该态即抛参数错误）。

        Args:
            kind: 步骤态（`try` / `confirm` / `cancel`）。

        Returns:
            str: 事件类型。

        Raises:
            ParamError: 步骤态非法或该态事件类型未定义。
        """
        if kind not in SAGA_STEP_KINDS:
            raise ParamError(f"Saga 步骤态非法：{kind}（应为 {'/'.join(SAGA_STEP_KINDS)}）")
        event_type = {
            SAGA_STEP_TRY: self.try_event_type,
            SAGA_STEP_CONFIRM: self.confirm_event_type,
            SAGA_STEP_CANCEL: self.cancel_event_type,
        }[kind]
        if not event_type:
            raise ParamError(f"Saga 步骤未定义 {kind} 态事件：{self.name}")
        return event_type


@dataclass(frozen=True)
class SagaDefinition(BaseObject):
    """Saga 流程定义：定义键 + 步骤清单（声明式，协同式下不含中心状态）。"""

    key: str
    """定义键（小写下划线，幂等消费标识的一部分）。"""

    steps: tuple[SagaStep, ...]
    """步骤清单（顺序即设计顺序，运行期由事件驱动推进）。"""

    description: str = ""
    """说明（中文）。"""

    def step(self, name: str) -> SagaStep | None:
        """按名取步骤。

        Args:
            name: 步骤名。

        Returns:
            SagaStep | None: 步骤；不存在 None。
        """
        return next((step for step in self.steps if step.name == name), None)

    def validate(self, *, contracts: EventContractRegistry | None = None) -> tuple[str, ...]:
        """校验定义（键 / 步骤唯一 / 事件类型格式 / 契约登记联动）。

        Args:
            contracts: 事件契约注册表；提供时校验各事件类型已登记契约。

        Returns:
            tuple[str, ...]: 违规明细；空元组通过。
        """
        return validate_saga_definition(self, contracts=contracts)


@dataclass(frozen=True)
class SagaStepOutcome(BaseObject):
    """步骤执行结果（幂等判定与排障用）。"""

    kind: str
    """步骤态（`try` / `confirm` / `cancel`）。"""

    step: str
    """步骤名。"""

    executed: bool
    """是否首次执行（False = 命中幂等登记、已跳过副作用）。"""

    event_id: str
    """触发事件 ID（幂等键）。"""


def build_saga_consumer(definition_key: str, step_name: str, kind: str) -> str:
    """构建三态幂等消费标识（`saga:{定义}:{步骤}:{kind}`）。

    Args:
        definition_key: Saga 定义键。
        step_name: 步骤名。
        kind: 步骤态（`try` / `confirm` / `cancel`）。

    Returns:
        str: 消费标识。

    Raises:
        ParamError: 步骤态非法。
    """
    if kind not in SAGA_STEP_KINDS:
        raise ParamError(f"Saga 步骤态非法：{kind}（应为 {'/'.join(SAGA_STEP_KINDS)}）")
    return f"{SAGA_CONSUMER_PREFIX}:{definition_key}:{step_name}:{kind}"


def build_saga_event(
    step: SagaStep,
    kind: str,
    payload: Mapping[str, object],
    *,
    saga_id: str,
    tenant_id: str | None = None,
) -> EventEnvelope:
    """构建 Saga 步骤事件（事件类型取该态声明；`aggregate_key = saga_id` 保同 Saga 有序）。

    Args:
        step: Saga 步骤。
        kind: 步骤态（`try` / `confirm` / `cancel`）。
        payload: 事件载荷。
        saga_id: Saga 实例标识（同 Saga 事件的聚合键）。
        tenant_id: 租户标识。

    Returns:
        EventEnvelope: 事件信封。

    Raises:
        ParamError: 步骤态非法或该态事件类型未定义。
    """
    return EventEnvelope(
        event_type=step.event_type_of(kind),
        payload=dict(payload),
        tenant_id=tenant_id,
        aggregate_key=saga_id,
    )


def validate_saga_definition(
    definition: SagaDefinition, *, contracts: EventContractRegistry | None = None
) -> tuple[str, ...]:
    """校验 Saga 定义（键 / 步骤唯一 / 事件类型格式 / 契约登记联动）。

    Args:
        definition: Saga 流程定义。
        contracts: 事件契约注册表；提供时校验各事件类型已登记契约。

    Returns:
        tuple[str, ...]: 违规明细；空元组通过。
    """
    errors: list[str] = []
    if not SAGA_KEY_RE.fullmatch(definition.key):
        errors.append(f"Saga 定义键非法（应为小写下划线）：{definition.key}")
    if not definition.steps:
        errors.append(f"Saga 定义步骤为空：{definition.key}")
    names = [step.name for step in definition.steps]
    for name in sorted({name for name in names if names.count(name) > 1}):
        errors.append(f"Saga 步骤名重复：{definition.key}.{name}")
    for step in definition.steps:
        label = f"{definition.key}.{step.name}"
        if not SAGA_KEY_RE.fullmatch(step.name):
            errors.append(f"Saga 步骤名非法（应为小写下划线）：{label}")
        for kind, event_type in (
            (SAGA_STEP_TRY, step.try_event_type),
            (SAGA_STEP_CONFIRM, step.confirm_event_type),
            (SAGA_STEP_CANCEL, step.cancel_event_type),
        ):
            if not event_type:
                continue
            if not EVENT_TYPE_RE.fullmatch(event_type):
                errors.append(f"Saga 步骤 {kind} 态事件名非法：{label}（{event_type}）")
            elif contracts is not None and contracts.contract(event_type) is None:
                errors.append(f"Saga 步骤 {kind} 态事件未登记契约：{label}（{event_type}）")
    return tuple(errors)


class BaseSagaExecutor(BasePluggable, ABC):
    """Saga 执行器契约：协同式参与者三态步进（本地事务 + 幂等登记 + 发件箱事件）。

    `emit` 传入事件信封时由执行器在同一事务内经发件箱写入（`build_saga_event` 构建、
    `aggregate_key = saga_id` 保序）；动作异常整体回滚（幂等登记与事件一并撤销）。
    """

    key: str = "saga_executor"
    plugin_key: str = "saga_executor"
    plugin_name: str = NULL_PLUGIN_NAME
    contract_version: str = DEFAULT_CONTRACT_VERSION

    @abstractmethod
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
        """执行预占态：幂等判定 → 动作 → （可选）发件箱事件。

        Args:
            session: 本地事务会话。
            definition: Saga 流程定义。
            step: Saga 步骤。
            trigger_event_id: 触发事件 ID（幂等键）。
            action: 预占动作（本地事务内执行）。
            emit: 需随事务发出的事件（缺省不发）。

        Returns:
            SagaStepOutcome: 步骤执行结果。
        """

    @abstractmethod
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

    @abstractmethod
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
        """执行取消态（幂等补偿：同一触发事件只执行一次，动作自身仍须业务幂等）。

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


def get_saga_executor(request: Request) -> BaseSagaExecutor:
    """取应用级 Saga 执行器（依赖注入提供者）。

    Args:
        request: 请求对象。

    Returns:
        BaseSagaExecutor: 应用装配的 Saga 执行器实例。
    """
    settings = cast("Settings", request.app.state.settings)
    return cast(
        "BaseSagaExecutor",
        resolve_plugin(
            "saga_executor",
            settings.saga.provider,
            expected_version=BaseSagaExecutor.contract_version,
        ),
    )
