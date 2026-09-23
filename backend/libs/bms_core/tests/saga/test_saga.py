"""Saga 三态执行与幂等补偿用例（Kiwi 2175）：定义校验 / 三态幂等 / 回滚 / 发件箱事件 / 空实现。

测试库：临时 SQLite（建发件箱与消费幂等表）；执行器调用均包在显式事务内。
"""

from types import SimpleNamespace
from typing import Any, cast

import pytest
from fastapi import FastAPI, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from support_app import ApplicationFactory, lifespan

import bms_core.application as application
import bms_core.saga.base as saga_base
from bms_core.core.exceptions import ConfigError, EventContractError, ParamError
from bms_core.db.sync import DbSession
from bms_core.events.base import EventEnvelope
from bms_core.events.contracts import EventContract, EventContractRegistry
from bms_core.models.outbox import SysEventConsumed, SysOutbox
from bms_core.outbox.store import SqlOutboxStore
from bms_core.saga.base import (
    SAGA_STEP_CANCEL,
    SAGA_STEP_CONFIRM,
    SAGA_STEP_TRY,
    SagaAction,
    SagaDefinition,
    SagaStep,
    build_saga_consumer,
    build_saga_event,
    get_saga_executor,
    validate_saga_definition,
)
from bms_core.saga.choreography import ChoreographySagaExecutor
from bms_core.saga.null import NullSagaExecutor

_STEP = SagaStep(
    name="reserve_stock",
    try_event_type="sys.stock.reserved",
    confirm_event_type="sys.stock.confirmed",
    cancel_event_type="sys.stock.released",
)
_PLAIN_STEP = SagaStep(name="plain", try_event_type="sys.plain.tried")
_DEFINITION = SagaDefinition(key="order_flow", steps=(_STEP, _PLAIN_STEP))


def _action(calls: list[str], *, fail: bool = False) -> SagaAction:
    """构造步骤动作（记录调用；可选首次失败）。

    Args:
        calls: 调用记录。
        fail: 是否抛异常。

    Returns:
        SagaAction: 步骤动作。
    """

    async def action(_session: DbSession) -> None:
        if fail:
            raise RuntimeError("业务失败")
        calls.append("run")

    return action


async def _count(session: AsyncSession, model: Any) -> int:
    """计数（显式事务）。

    Args:
        session: 会话。
        model: ORM 模型。

    Returns:
        int: 行数。
    """
    async with session.begin():
        return int((await session.execute(select(func.count()).select_from(model))).scalar_one())


@pytest.mark.kiwi_id(2175)
def test_validate_saga_definition() -> None:
    """定义校验：合法通过；键 / 步骤重复 / 事件类型违规检出；契约注册表联动。"""
    assert validate_saga_definition(_DEFINITION) == ()
    assert _DEFINITION.step("reserve_stock") == _STEP
    assert _DEFINITION.step("ghost") is None

    assert any("定义键非法" in error for error in validate_saga_definition(SagaDefinition(key="Bad", steps=(_STEP,))))
    assert any("步骤为空" in error for error in validate_saga_definition(SagaDefinition(key="empty", steps=())))
    assert any(
        "步骤名重复" in error for error in validate_saga_definition(SagaDefinition(key="dup", steps=(_STEP, _STEP)))
    )
    assert any(
        "步骤名非法" in error
        for error in validate_saga_definition(
            SagaDefinition(key="bad_step", steps=(SagaStep(name="Bad", try_event_type="sys.a.b"),))
        )
    )
    assert any(
        "事件名非法" in error
        for error in validate_saga_definition(
            SagaDefinition(key="bad_event", steps=(SagaStep(name="step", try_event_type="Bad"),))
        )
    )

    registry = EventContractRegistry()
    registry.register(EventContract(event_type="sys.stock.reserved", version="1.0.0", fields={}))
    errors = validate_saga_definition(_DEFINITION, contracts=registry)
    assert any("未登记契约" in error for error in errors)
    registry.register(EventContract(event_type="sys.stock.confirmed", version="1.0.0", fields={}))
    registry.register(EventContract(event_type="sys.stock.released", version="1.0.0", fields={}))
    registry.register(EventContract(event_type="sys.plain.tried", version="1.0.0", fields={}))
    assert validate_saga_definition(_DEFINITION, contracts=registry) == ()
    assert _DEFINITION.validate(contracts=registry) == ()


@pytest.mark.kiwi_id(2175)
def test_build_saga_consumer_and_event() -> None:
    """消费标识与事件构建：三态取事件类型；未定义态 / 非法态抛参数错误。"""
    assert build_saga_consumer("order_flow", "reserve_stock", SAGA_STEP_TRY) == "saga:order_flow:reserve_stock:try"
    with pytest.raises(ParamError):
        build_saga_consumer("order_flow", "reserve_stock", "rollback")

    event = build_saga_event(_STEP, SAGA_STEP_CANCEL, {"order_id": "o1"}, saga_id="saga-1", tenant_id="demo")
    assert event.event_type == "sys.stock.released"
    assert event.aggregate_key == "saga-1"
    assert event.tenant_id == "demo"
    with pytest.raises(ParamError):
        build_saga_event(_PLAIN_STEP, SAGA_STEP_CONFIRM, {}, saga_id="saga-1")
    with pytest.raises(ParamError):
        _STEP.event_type_of("rollback")


@pytest.mark.kiwi_id(2175)
async def test_try_step_idempotent_and_emit(saga_session: AsyncSession) -> None:
    """预占态：首次执行动作 + 同事务发件箱事件；同一触发事件重复投递跳过副作用。"""
    executor = ChoreographySagaExecutor(SqlOutboxStore())
    calls: list[str] = []
    emit = build_saga_event(_STEP, SAGA_STEP_TRY, {"order_id": "o1"}, saga_id="saga-1")

    async with saga_session.begin():
        first = await executor.try_step(
            saga_session,
            definition=_DEFINITION,
            step=_STEP,
            trigger_event_id="evt-1",
            action=_action(calls),
            emit=emit,
        )
    assert first.kind == SAGA_STEP_TRY and first.executed is True and first.event_id == "evt-1"
    assert calls == ["run"]
    assert await _count(saga_session, SysEventConsumed) == 1
    assert await _count(saga_session, SysOutbox) == 1

    async with saga_session.begin():
        rows = (await saga_session.execute(select(SysOutbox))).scalars().all()
    assert rows[0].event_type == "sys.stock.reserved"
    assert rows[0].aggregate_key == "saga-1"

    async with saga_session.begin():
        repeat = await executor.try_step(
            saga_session,
            definition=_DEFINITION,
            step=_STEP,
            trigger_event_id="evt-1",
            action=_action(calls),
            emit=emit,
        )
    assert repeat.executed is False
    assert calls == ["run"]
    assert await _count(saga_session, SysOutbox) == 1


@pytest.mark.kiwi_id(2175)
async def test_confirm_and_cancel_steps(saga_session: AsyncSession) -> None:
    """确认 / 取消态：各自独立幂等（消费标识含 kind）；取消即幂等补偿。"""
    executor = ChoreographySagaExecutor(SqlOutboxStore())
    calls: list[str] = []

    async with saga_session.begin():
        confirmed = await executor.confirm_step(
            saga_session,
            definition=_DEFINITION,
            step=_STEP,
            trigger_event_id="evt-confirm",
            action=_action(calls),
        )
    assert confirmed.kind == SAGA_STEP_CONFIRM and confirmed.executed is True

    async with saga_session.begin():
        cancelled = await executor.cancel_step(
            saga_session,
            definition=_DEFINITION,
            step=_STEP,
            trigger_event_id="evt-abort",
            action=_action(calls),
        )
    assert cancelled.kind == SAGA_STEP_CANCEL and cancelled.executed is True

    async with saga_session.begin():
        again = await executor.cancel_step(
            saga_session,
            definition=_DEFINITION,
            step=_STEP,
            trigger_event_id="evt-abort",
            action=_action(calls),
        )
    assert again.executed is False
    assert calls == ["run", "run"]
    assert await _count(saga_session, SysEventConsumed) == 2


@pytest.mark.kiwi_id(2175)
async def test_action_failure_rolls_back_and_retries(saga_session: AsyncSession) -> None:
    """动作异常整体回滚（幂等登记与事件一并撤销）；同触发事件重投可再次执行。"""
    executor = ChoreographySagaExecutor(SqlOutboxStore())
    calls: list[str] = []
    emit = build_saga_event(_STEP, SAGA_STEP_TRY, {"order_id": "o1"}, saga_id="saga-2")

    with pytest.raises(RuntimeError):
        async with saga_session.begin():
            await executor.try_step(
                saga_session,
                definition=_DEFINITION,
                step=_STEP,
                trigger_event_id="evt-2",
                action=_action(calls, fail=True),
                emit=emit,
            )
    assert calls == []
    assert await _count(saga_session, SysEventConsumed) == 0
    assert await _count(saga_session, SysOutbox) == 0

    async with saga_session.begin():
        retried = await executor.try_step(
            saga_session,
            definition=_DEFINITION,
            step=_STEP,
            trigger_event_id="evt-2",
            action=_action(calls),
            emit=emit,
        )
    assert retried.executed is True
    assert calls == ["run"]
    assert await _count(saga_session, SysEventConsumed) == 1


@pytest.mark.kiwi_id(2175)
async def test_null_executor_raises_config_error(saga_session: AsyncSession) -> None:
    """空实现调用即抛配置错误（不静默跳过、不裸执行）。"""
    executor = NullSagaExecutor()
    for method in (executor.try_step, executor.confirm_step, executor.cancel_step):
        with pytest.raises(ConfigError):
            await method(
                saga_session,
                definition=_DEFINITION,
                step=_STEP,
                trigger_event_id="evt-null",
                action=_action([]),
            )


def test_provider_resolves(monkeypatch: pytest.MonkeyPatch) -> None:
    """依赖注入提供者按配置解析（装配 settings → `resolve_plugin`）。"""
    sentinel = object()

    def _fake_resolve(plugin_key: str, provider: str = "", *, expected_version: str = "") -> object:
        del plugin_key, provider, expected_version
        return sentinel

    monkeypatch.setattr(saga_base, "resolve_plugin", _fake_resolve)
    settings = SimpleNamespace(saga=SimpleNamespace(provider="choreography"))
    app = FastAPI()
    app.state.settings = settings
    request = Request({"type": "http", "app": app, "headers": []})
    assert get_saga_executor(request) is sentinel


@pytest.mark.kiwi_id(2175)
async def test_app_wires_saga_executor() -> None:
    """应用装配：默认配置解析真实协同式执行器，启动事件契约校验通过。"""
    app = ApplicationFactory().create(None)
    async with lifespan(app):
        assert isinstance(app.state.saga_executor, ChoreographySagaExecutor)
        assert isinstance(app.state.outbox_store, SqlOutboxStore)


def test_event_contract_validation_failure_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    """启动事件契约校验失败即拒启（`EventContractError`）。"""

    def _fake_validate(*args: object, **kwargs: object) -> tuple[str, ...]:
        del args, kwargs
        return ("事件域未登记：ghost",)

    monkeypatch.setattr(application, "validate_event_registry", _fake_validate)
    with pytest.raises(EventContractError):
        application._validate_event_contracts()  # pyright: ignore[reportPrivateUsage]


def test_saga_event_envelope_defaults() -> None:
    """Saga 事件信封字段缺省（版本由发件箱补齐；trace 等不设置）。"""
    event = build_saga_event(_STEP, SAGA_STEP_TRY, {}, saga_id="saga-3")
    assert isinstance(event, EventEnvelope)
    assert event.event_version is None
    assert event.payload == {}
    assert cast("object", event.tenant_id) is None
