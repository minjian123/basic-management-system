"""01-8-1 outbox 适配与 relay 切换用例（Kiwi 2481）。

覆盖：provider 三态、msg 工厂固定解析 msg 发布实现、业务代码零改动、真发件箱投递 /
失败重试 / 效果一次 / 双写窗口、CLI 与运行期同解析、事务消息与 CDC 后置边界。

真发件箱用例复用本目录 `conftest.py` 的临时 SQLite 库；网络发布实现全部用测试替身，
真实链路联调证据在 msg 仓跨仓用例。
"""

from __future__ import annotations

import asyncio
from typing import Any, cast

import pytest
from fastapi import FastAPI
from sqlalchemy import select

from bms_core.core import assembly
from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.config import Settings, get_settings
from bms_core.core.exceptions import PluginError
from bms_core.core.plugin import default_plugin_registry, plugin_registry_snapshot
from bms_core.core.resources import ResourceManager
from bms_core.db.engine import PLATFORM_DB_KEY
from bms_core.db.registry import EngineRegistry
from bms_core.db.session import SessionFactory
from bms_core.db.sync import DbSession
from bms_core.events.base import EventEnvelope, EventPublisher, EventPublishError
from bms_core.metrics.null import NullMetrics
from bms_core.models.outbox import SysOutbox
from bms_core.msgclient.adapter.event_publisher import MsgEventPublisher
from bms_core.msgclient.constants import MSG_PROVIDER_NAME
from bms_core.outbox.base import OUTBOX_STATUS_DELIVERED, BaseOutboxDispatcher
from bms_core.outbox.dispatcher import (
    MsgOutboxDispatcher,
    PollOutboxDispatcher,
    outbox_dispatcher_class,
)
from bms_core.outbox.null import NullOutboxDispatcher
from bms_core.outbox.store import SqlOutboxStore
from ops import outbox as outbox_cli

pytestmark = pytest.mark.kiwi_id(2481)


class _RecordingPublisher(EventPublisher):
    """记录成功发布的事件。"""

    def __init__(self) -> None:
        """初始化。"""
        self.events: ConcurrentStableList[EventEnvelope] = ConcurrentStableList()

    @property
    def event_type(self) -> str:
        """事件类型（测试固定）。"""
        return "test.probe"

    async def publish(self, event: EventEnvelope) -> None:
        """记录一条已投递事件。"""
        self.events.add(event)

    async def publish_transactional(self, event: EventEnvelope) -> None:
        """事务发布（同 `publish`）。"""
        await self.publish(event)


class _UnreachablePublisher(EventPublisher):
    """恒抛 `EventPublishError` 的发布器（模拟 msg 实例不可达）。"""

    def __init__(self) -> None:
        """初始化。"""
        self.attempts: ConcurrentStableList[str] = ConcurrentStableList()

    @property
    def event_type(self) -> str:
        """事件类型（测试固定）。"""
        return "test.probe"

    async def publish(self, event: EventEnvelope) -> None:
        """记录一次尝试后抛投递失败。"""
        self.attempts.add(event.event_id or "")
        raise EventPublishError("msg 实例不可达（注入）")

    async def publish_transactional(self, event: EventEnvelope) -> None:
        """事务发布（同 `publish`）。"""
        await self.publish(event)


def _dispatcher(
    dispatcher_type: type[PollOutboxDispatcher], registry: EngineRegistry, publisher: EventPublisher
) -> PollOutboxDispatcher:
    """按实现类构造投递器（零退避，让失败行下一轮立即可见）。

    Args:
        dispatcher_type: 投递器实现类（`poll` / `msg`）。
        registry: 引擎注册表。
        publisher: 事件发布端口。

    Returns:
        PollOutboxDispatcher: 投递器实例。
    """
    return dispatcher_type(
        store=SqlOutboxStore(),
        publisher=publisher,
        engine_registry=registry,
        session_factory=SessionFactory(),
        batch_size=100,
        max_retries=3,
        backoff=0.0,
        db_keys=ConcurrentStableList((PLATFORM_DB_KEY,)),
    )


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> Any:
    """每个用例前后清配置缓存，避免环境变量覆盖串味。"""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


# ---------------------------------------------------------------------------
# T1 三态解析
# ---------------------------------------------------------------------------


def test_provider_three_states() -> None:
    """T1：poll / msg 映射到对应实现类，未注册实现名抛 `PluginError`（不回落）。"""
    assert outbox_dispatcher_class("poll") is PollOutboxDispatcher
    assert outbox_dispatcher_class(MSG_PROVIDER_NAME) is MsgOutboxDispatcher
    assert MsgOutboxDispatcher.plugin_name == MSG_PROVIDER_NAME
    with pytest.raises(PluginError, match="未注册的 outbox_dispatcher 实现：ghost"):
        outbox_dispatcher_class("ghost")


def test_msg_dispatcher_registered_in_plugin_registry() -> None:
    """T1：装配登记表中 `outbox_dispatcher` 同时具备 `poll` / `msg` 两个实现。"""
    registry = default_plugin_registry()
    registry.reset()
    try:
        app = FastAPI()
        app.state.settings = Settings()
        assembly.register_platform_plugins(Settings(), app, ResourceManager())
        bucket = plugin_registry_snapshot().get("outbox_dispatcher")
        assert bucket is not None
        assert bucket.get("poll") is not None
        assert bucket.get(MSG_PROVIDER_NAME) is not None
    finally:
        registry.reset()


# ---------------------------------------------------------------------------
# T2 工厂：职责分离与 config_fingerprint 口径
# ---------------------------------------------------------------------------


def _stub_app() -> FastAPI:
    """构造带引擎注册表占位的应用（工厂只取 state，不启动 lifespan）。"""
    app = FastAPI()
    app.state.engine_registry = cast("Any", object())
    return app


def _patch_resolve(
    monkeypatch: pytest.MonkeyPatch, publisher: EventPublisher, calls: ConcurrentStableList[tuple[str, str]]
) -> None:
    """替换装配层的插件解析，记录 (plugin_key, provider) 并返回测试替身。"""

    def _resolve(plugin_key: str, provider: str | None = None, *, expected_version: str | None = None) -> object:
        del expected_version
        calls.add((plugin_key, provider or ""))
        if plugin_key == "event":
            return publisher
        if plugin_key == "outbox_store":
            return SqlOutboxStore()
        return NullMetrics()

    monkeypatch.setattr(assembly, "resolve_plugin", _resolve)


def test_msg_factory_pins_msg_publisher(monkeypatch: pytest.MonkeyPatch) -> None:
    """T2：msg 工厂固定解析 `msg` 发布实现，不读 `[event].provider`（避免假切换）。"""
    settings = Settings()
    settings.event.provider = "rocketmq"
    calls: ConcurrentStableList[tuple[str, str]] = ConcurrentStableList()
    _patch_resolve(monkeypatch, _RecordingPublisher(), calls)

    dispatcher = assembly.MsgOutboxDispatcherFactory(settings, _stub_app()).create()

    assert isinstance(dispatcher, MsgOutboxDispatcher)
    assert dispatcher.plugin_name == MSG_PROVIDER_NAME
    assert ("event", MSG_PROVIDER_NAME) in list(calls)
    assert ("event", "rocketmq") not in list(calls)


def test_poll_factory_keeps_event_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    """T2：poll 工厂行为不变，仍按 `[event].provider` 解析（切回原实现）。"""
    settings = Settings()
    settings.event.provider = "rocketmq"
    calls: ConcurrentStableList[tuple[str, str]] = ConcurrentStableList()
    _patch_resolve(monkeypatch, _RecordingPublisher(), calls)

    dispatcher = assembly.PollOutboxDispatcherFactory(settings, _stub_app()).create()

    assert isinstance(dispatcher, PollOutboxDispatcher)
    assert not isinstance(dispatcher, MsgOutboxDispatcher)
    assert ("event", "rocketmq") in list(calls)
    assert ("event", MSG_PROVIDER_NAME) not in list(calls)


# ---------------------------------------------------------------------------
# T3 / T9 业务代码零改动与后置边界
# ---------------------------------------------------------------------------


def test_port_contract_and_zero_duplicated_logic() -> None:
    """T3/T9：端口契约与版本不变，msg 版零逻辑复制，不引入事务消息 / connector 能力。"""
    assert MsgOutboxDispatcher.__mro__[1] is PollOutboxDispatcher
    assert MsgOutboxDispatcher.contract_version == BaseOutboxDispatcher.contract_version
    assert MsgOutboxDispatcher.dispatch_once is PollOutboxDispatcher.dispatch_once
    assert MsgOutboxDispatcher.dispatch_due is PollOutboxDispatcher.dispatch_due
    assert "publish_transactional" not in MsgOutboxDispatcher.__dict__
    assert "scan_outbox" not in MsgOutboxDispatcher.__dict__
    assert "enqueue" not in MsgOutboxDispatcher.__dict__


# ---------------------------------------------------------------------------
# T4 / T5 / T6 / T7 真发件箱行为
# ---------------------------------------------------------------------------


async def test_msg_relay_delivery_retry_and_switch_back(session: DbSession, registry: EngineRegistry) -> None:
    """T4~T7：失败保行计次、恢复补发一次、切回不重投、每轮只产生一条消息。"""
    store = SqlOutboxStore()
    async with session.begin():
        first = (
            await store.enqueue(
                session,
                EventEnvelope(event_type="order.created", payload=ConcurrentStableDict({"id": 1})),
            )
        ) or ""
        second = (
            await store.enqueue(
                session,
                EventEnvelope(event_type="order.paid", payload=ConcurrentStableDict({"id": 2})),
            )
        ) or ""

    unreachable = _UnreachablePublisher()
    failed_round = await _dispatcher(MsgOutboxDispatcher, registry, unreachable).dispatch_once(db_key=PLATFORM_DB_KEY)
    assert (failed_round.published, failed_round.failed, failed_round.dead) == (0, 2, 0)
    assert list(unreachable.attempts) == [first, second]
    async with session.begin():
        rows = (await session.execute(select(SysOutbox.status, SysOutbox.retry_count, SysOutbox.error_msg))).all()
    assert all(row.status != OUTBOX_STATUS_DELIVERED for row in rows)
    assert all(row.retry_count == 1 and row.error_msg for row in rows)

    working = _RecordingPublisher()
    ok_round = await _dispatcher(MsgOutboxDispatcher, registry, working).dispatch_once(db_key=PLATFORM_DB_KEY)
    assert (ok_round.published, ok_round.failed) == (2, 0)
    delivered_ids = [event.event_id or "" for event in working.events]
    assert sorted(delivered_ids) == sorted([first, second])
    assert len(delivered_ids) == len(set(delivered_ids))

    back_round = await _dispatcher(PollOutboxDispatcher, registry, unreachable).dispatch_once(db_key=PLATFORM_DB_KEY)
    assert (back_round.published, back_round.failed) == (0, 0)
    assert list(unreachable.attempts) == [first, second]
    async with session.begin():
        statuses = (await session.execute(select(SysOutbox.status))).scalars().all()
    assert set(statuses) == {OUTBOX_STATUS_DELIVERED}


# ---------------------------------------------------------------------------
# T8 CLI 通道一致
# ---------------------------------------------------------------------------


def _fake_base_url(_settings: Settings) -> str:
    """测试用 msg 实例基址（惰性建连，不发起网络）。"""
    return "http://msg.test"


def _fake_namespace(_settings: Settings) -> str:
    """测试用事件命名空间。"""
    return "bms"


def _cli_dispatcher(monkeypatch: pytest.MonkeyPatch, provider: str) -> BaseOutboxDispatcher:
    """按 provider 走 CLI 构造入口并返回投递器（同步释放引擎注册表）。"""
    monkeypatch.setenv("BMS_OUTBOX__PROVIDER", provider)
    get_settings.cache_clear()
    dispatcher, registry = outbox_cli._build_dispatcher()  # pyright: ignore[reportPrivateUsage]
    asyncio.run(registry.aclose())
    return dispatcher


def test_cli_null_placeholder(monkeypatch: pytest.MonkeyPatch) -> None:
    """T8：`[outbox].provider` 空串沿用 bms 既有 null 占位（不投递）。"""
    assert isinstance(_cli_dispatcher(monkeypatch, ""), NullOutboxDispatcher)


def test_cli_poll_uses_original(monkeypatch: pytest.MonkeyPatch) -> None:
    """T8：`poll` 解析为原实现（缺省口径不变）。"""
    dispatcher = _cli_dispatcher(monkeypatch, "poll")
    assert isinstance(dispatcher, PollOutboxDispatcher)
    assert not isinstance(dispatcher, MsgOutboxDispatcher)


def test_cli_msg_uses_msg_publisher(monkeypatch: pytest.MonkeyPatch) -> None:
    """T8：`msg` 解析为 msg 版且发布实现为 `MsgEventPublisher`（不读 `[event].provider`）。"""
    monkeypatch.setattr(outbox_cli, "msg_base_url", _fake_base_url)
    monkeypatch.setattr(outbox_cli, "msg_namespace", _fake_namespace)
    monkeypatch.setenv("BMS_EVENT__PROVIDER", "rocketmq")
    dispatcher = _cli_dispatcher(monkeypatch, MSG_PROVIDER_NAME)
    assert isinstance(dispatcher, MsgOutboxDispatcher)
    assert isinstance(dispatcher._publisher, MsgEventPublisher)  # pyright: ignore[reportPrivateUsage]


def test_cli_rejects_unknown_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    """T8：非法 provider 在 CLI 装配期抛 `PluginError`，不静默回落。"""
    monkeypatch.setenv("BMS_OUTBOX__PROVIDER", "ghost")
    get_settings.cache_clear()
    with pytest.raises(PluginError, match="未注册的 outbox_dispatcher 实现：ghost"):
        outbox_cli._build_dispatcher()  # pyright: ignore[reportPrivateUsage]
