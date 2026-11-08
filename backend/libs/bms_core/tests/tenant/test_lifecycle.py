"""租户生命周期与产品资源动作（07D 需求 01-4）：契约、幂等、动作路由与装配。

覆盖详细设计 §4.5 用例 1~12：
- 事件构造与契约登记（四类事件、载荷含 `version` 可选字段）；
- 动作路由（四类事件各只触发对应动作）；
- 业务级幂等（同版本 / 旧版本跳过、新版本执行并记账）；
- 失败语义（动作抛错不记账且上抛，可重试成功）；
- 非法输入（未知事件类型、载荷缺字段、version 非法）；
- 旧生产者兼容（缺 version 按 0）；空实现与装配出口。
"""

from collections.abc import Iterator
from typing import Any, cast

import pytest
from fastapi import FastAPI
from starlette.requests import Request

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.config import Settings
from bms_core.core.exceptions import ConfigError, EventContractError, PluginError
from bms_core.events.base import EventEnvelope
from bms_core.events.contracts import resolve_event_contract
from bms_core.events.platform_events import register_platform_event_contracts
from bms_core.tenant.lifecycle import (
    TENANT_ACTION_ACTIVATED,
    TENANT_ACTION_CREATED,
    TENANT_ACTION_DELETED,
    TENANT_ACTION_SUSPENDED,
    TENANT_ACTIVATED,
    TENANT_CREATED,
    TENANT_DELETED,
    TENANT_SUSPENDED,
    BaseTenantResourceHandler,
    TenantLifecycleContext,
    TenantLifecycleDispatcher,
    build_tenant_lifecycle_event,
    get_tenant_resource_handler,
)
from bms_core.tenant.null import NullTenantResourceHandler

pytestmark = pytest.mark.kiwi_id(2449)

_TENANT_ID = 1000000000000000001
_DB_KEY = "tenant_demo"
_EVENT_TYPES = (TENANT_CREATED, TENANT_SUSPENDED, TENANT_ACTIVATED, TENANT_DELETED)
_ACTION_BY_EVENT = {
    TENANT_CREATED: TENANT_ACTION_CREATED,
    TENANT_SUSPENDED: TENANT_ACTION_SUSPENDED,
    TENANT_ACTIVATED: TENANT_ACTION_ACTIVATED,
    TENANT_DELETED: TENANT_ACTION_DELETED,
}


class _RecordingHandler(BaseTenantResourceHandler):
    """记录型资源实现：记录调用与账本，可按动作注入失败。"""

    plugin_name: str = "recording_lifecycle"

    def __init__(self, *, fail_on: str | None = None) -> None:
        """初始化。

        Args:
            fail_on: 让该动作抛错的动名（None 表示不注入失败）。
        """
        self.calls: ConcurrentStableList[str] = ConcurrentStableList()
        self.contexts: ConcurrentStableList[TenantLifecycleContext] = ConcurrentStableList()
        self._applied: ConcurrentStableDict[tuple[int, str], int] = ConcurrentStableDict()
        self._fail_on = fail_on

    async def applied_version(self, *, tenant_id: int, action: str) -> int:
        """读取账本。"""
        return self._applied.get((tenant_id, action), -1)

    async def mark_applied(self, *, tenant_id: int, action: str, version: int) -> None:
        """写入账本。"""
        self._applied.set((tenant_id, action), int(version))

    async def on_created(self, context: TenantLifecycleContext) -> None:
        """记录 created。"""
        self._record(context)

    async def on_suspended(self, context: TenantLifecycleContext) -> None:
        """记录 suspended。"""
        self._record(context)

    async def on_activated(self, context: TenantLifecycleContext) -> None:
        """记录 activated。"""
        self._record(context)

    async def on_deleted(self, context: TenantLifecycleContext) -> None:
        """记录 deleted。"""
        self._record(context)

    def stop_failing(self) -> None:
        """停止注入失败（模拟运维修复后重试）。"""
        self._fail_on = None

    def _record(self, context: TenantLifecycleContext) -> None:
        """记录调用（可注入失败）。

        Args:
            context: 生命周期上下文。

        Raises:
            RuntimeError: 命中注入的失败动作。
        """
        self.calls.append(context.action)
        self.contexts.append(context)
        if self._fail_on == context.action:
            raise RuntimeError(f"action failed: {context.action}")


class _LedgerOnlyHandler(BaseTenantResourceHandler):
    """只实现账本的子类：用于验证四动作基类默认空实现。"""

    plugin_name: str = "ledger_only_lifecycle"

    async def applied_version(self, *, tenant_id: int, action: str) -> int:
        """恒无记录。"""
        del tenant_id, action
        return -1

    async def mark_applied(self, *, tenant_id: int, action: str, version: int) -> None:
        """不记账。"""
        del tenant_id, action, version


@pytest.fixture(autouse=True)
def _reset_state() -> Iterator[None]:
    """用例隔离（当前无全局态，保留占位便于后续扩展）。

    Yields:
        None: 用例运行期。
    """
    register_platform_event_contracts()
    yield


def _event(event_type: str = TENANT_CREATED, *, version: int | None = 1) -> EventEnvelope:
    """构造一条生命周期事件。

    Args:
        event_type: 事件类型。
        version: 版本戳（None 表示不带该字段）。

    Returns:
        EventEnvelope: 事件信封。
    """
    event = build_tenant_lifecycle_event(
        event_type=event_type,
        tenant_id=_TENANT_ID,
        db_key=_DB_KEY,
        status="active",
        version=version,
    )
    event.event_id = "evt-1"
    return event


def _request(app: object) -> Request:
    """构造带 app 的最小请求。

    Args:
        app: 应用实例（提供 `state.settings`）。

    Returns:
        Request: Starlette 请求对象。
    """
    scope: dict[str, Any] = {  # bare-collections:allow（ASGI scope 为 Starlette 原生 dict）
        "type": "http",
        "method": "GET",
        "path": "/internal",
        "headers": [],
        "query_string": b"",
        "app": app,
    }
    return Request(cast("Any", scope))


def test_event_payload_and_envelope() -> None:
    """四类事件均可构造；载荷四字段齐备，信封租户位与聚合键正确。"""
    for event_type in _EVENT_TYPES:
        event = _event(event_type, version=3)

        assert event.event_type == event_type
        assert event.tenant_id == str(_TENANT_ID)
        assert event.payload["tenant_id"] == str(_TENANT_ID)
        assert event.payload["db_key"] == _DB_KEY
        assert event.payload["status"] == "active"
        assert event.payload["version"] == 3
        assert event.aggregate_key == f"tenant:{_TENANT_ID}"


def test_unknown_event_type_construction_rejected() -> None:
    """构造期即拒非法事件类型（编程错误，非运行期数据问题）。"""
    with pytest.raises(ConfigError):
        build_tenant_lifecycle_event(event_type="tenant.unknown", tenant_id=1, db_key="k", status="active")


def test_deleted_contract_registered() -> None:
    """`tenant.deleted` 已登记且属租户事件族 `2.2.0`；`version` / `purge_at` / `reason` 均可选。"""
    contract = resolve_event_contract(TENANT_DELETED)

    assert contract is not None
    assert contract.version == "2.2.0"
    assert contract.fields["version"].required is False
    assert contract.fields["version"].type == "integer"
    assert contract.fields["purge_at"].required is False
    assert contract.fields["reason"].required is False


@pytest.mark.parametrize("event_type", _EVENT_TYPES)
async def test_routes_to_matching_action(event_type: str) -> None:
    """四类事件各只触发对应动作一次。"""
    handler = _RecordingHandler()
    dispatcher = TenantLifecycleDispatcher(handler=handler)

    outcome = await dispatcher.dispatch(_event(event_type))

    assert outcome == "applied"
    assert list(handler.calls) == [_ACTION_BY_EVENT[event_type]]


async def test_non_numeric_tenant_id_rejected() -> None:
    """`tenant_id` 非十进制雪花 id 即拒（不猜、不截断）。"""
    dispatcher = TenantLifecycleDispatcher(handler=_RecordingHandler())

    event = _event(TENANT_CREATED)
    event.payload.set("tenant_id", "not-a-number")

    with pytest.raises(EventContractError):
        await dispatcher.dispatch(event)


async def test_null_handler_covers_all_actions() -> None:
    """空实现四动作均可调用（各自记漏配告警，不抛错）。"""
    handler = NullTenantResourceHandler()
    context = TenantLifecycleContext(
        tenant_id=_TENANT_ID, action=TENANT_ACTION_DELETED, version=1, db_key=_DB_KEY, status="suspended"
    )

    await handler.on_created(context)
    await handler.on_suspended(context)
    await handler.on_activated(context)
    await handler.on_deleted(context)


async def test_same_version_skipped() -> None:
    """同版本重复投递：动作只执行一次。"""
    handler = _RecordingHandler()
    dispatcher = TenantLifecycleDispatcher(handler=handler)

    assert await dispatcher.dispatch(_event(TENANT_CREATED, version=2)) == "applied"
    assert await dispatcher.dispatch(_event(TENANT_CREATED, version=2)) == "skipped"

    assert list(handler.calls) == [TENANT_ACTION_CREATED]


async def test_older_version_skipped() -> None:
    """乱序旧版本：直接跳过，不回退动作。"""
    handler = _RecordingHandler()
    dispatcher = TenantLifecycleDispatcher(handler=handler)

    assert await dispatcher.dispatch(_event(TENANT_SUSPENDED, version=5)) == "applied"
    assert await dispatcher.dispatch(_event(TENANT_SUSPENDED, version=4)) == "skipped"

    assert list(handler.calls) == [TENANT_ACTION_SUSPENDED]


async def test_newer_version_applied() -> None:
    """新版本继续执行并推进账本。"""
    handler = _RecordingHandler()
    dispatcher = TenantLifecycleDispatcher(handler=handler)

    await dispatcher.dispatch(_event(TENANT_ACTIVATED, version=1))
    assert await dispatcher.dispatch(_event(TENANT_ACTIVATED, version=2)) == "applied"

    assert list(handler.calls) == [TENANT_ACTION_ACTIVATED, TENANT_ACTION_ACTIVATED]
    assert await handler.applied_version(tenant_id=_TENANT_ID, action=TENANT_ACTION_ACTIVATED) == 2


async def test_action_failure_not_marked() -> None:
    """动作失败：上抛且不记账；再次投递可重试成功。"""
    handler = _RecordingHandler(fail_on=TENANT_ACTION_DELETED)
    dispatcher = TenantLifecycleDispatcher(handler=handler)

    with pytest.raises(RuntimeError):
        await dispatcher.dispatch(_event(TENANT_DELETED, version=1))

    assert await handler.applied_version(tenant_id=_TENANT_ID, action=TENANT_ACTION_DELETED) == -1

    handler.stop_failing()
    assert await dispatcher.dispatch(_event(TENANT_DELETED, version=1)) == "applied"
    assert await handler.applied_version(tenant_id=_TENANT_ID, action=TENANT_ACTION_DELETED) == 1


async def test_unknown_event_type_rejected() -> None:
    """分发器拒未知事件类型（10010，消费侧转死信）。"""
    dispatcher = TenantLifecycleDispatcher(handler=_RecordingHandler())
    event = EventEnvelope(event_type="sys.operation.logged", payload=ConcurrentStableDict())

    with pytest.raises(EventContractError):
        await dispatcher.dispatch(event)


@pytest.mark.parametrize("missing", ["tenant_id", "db_key", "status"])
async def test_missing_payload_rejected(missing: str) -> None:
    """载荷缺必填字段即 fail-closed（10010）。"""
    dispatcher = TenantLifecycleDispatcher(handler=_RecordingHandler())

    event = _event(TENANT_CREATED)
    event.payload.delete(missing)

    with pytest.raises(EventContractError):
        await dispatcher.dispatch(event)


async def test_invalid_version_rejected() -> None:
    """version 非整数即拒（不按 0 猜）。"""
    dispatcher = TenantLifecycleDispatcher(handler=_RecordingHandler())

    event = _event(TENANT_CREATED, version=None)
    event.payload.set("version", "abc")

    with pytest.raises(EventContractError):
        await dispatcher.dispatch(event)


async def test_missing_version_treated_as_zero() -> None:
    """旧生产者不带 version：按 0 处理，动作仍执行（投递级幂等兜底）。"""
    handler = _RecordingHandler()
    dispatcher = TenantLifecycleDispatcher(handler=handler)

    assert await dispatcher.dispatch(_event(TENANT_CREATED, version=None)) == "applied"

    assert list(handler.calls) == [TENANT_ACTION_CREATED]
    assert handler.contexts[0].version == 0


async def test_null_handler_noop_and_ledger() -> None:
    """空实现：四动作 no-op，账本可读写并递增。"""
    handler = NullTenantResourceHandler()
    context = TenantLifecycleContext(
        tenant_id=_TENANT_ID, action=TENANT_ACTION_CREATED, version=1, db_key=_DB_KEY, status="active"
    )

    await handler.on_created(context)
    assert await handler.applied_version(tenant_id=_TENANT_ID, action=TENANT_ACTION_CREATED) == -1

    await handler.mark_applied(tenant_id=_TENANT_ID, action=TENANT_ACTION_CREATED, version=1)
    assert await handler.applied_version(tenant_id=_TENANT_ID, action=TENANT_ACTION_CREATED) == 1


def test_get_handler_resolves_null_and_unknown() -> None:
    """依赖出口：null 缺省实现可解析；未登记实现名即 PluginError。"""
    settings = Settings()
    settings.tenant_resources.provider = "null"
    app = FastAPI()
    app.state.settings = settings

    assert isinstance(get_tenant_resource_handler(_request(app)), NullTenantResourceHandler)

    settings.tenant_resources.provider = "unknown"
    with pytest.raises(PluginError):
        get_tenant_resource_handler(_request(app))


def test_settings_default_provider_is_null() -> None:
    """缺省配置：`[tenant_resources].provider = "null"`（基座自身无产品资源）。"""
    assert Settings().tenant_resources.provider == "null"


async def test_base_handler_actions_default_to_noop() -> None:
    """基类四动作默认空实现：只实现账本的子类可直接跑通四类事件。"""
    handler = _LedgerOnlyHandler()
    dispatcher = TenantLifecycleDispatcher(handler=handler)

    for event_type in _EVENT_TYPES:
        assert await dispatcher.dispatch(_event(event_type)) == "applied"
