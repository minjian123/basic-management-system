"""能力域基类登记语义测试（Kiwi 531）：40 类继承链 / Null 缺省登记 / 抽象与无名不登记。"""

import importlib
import inspect
import pkgutil
import re
from abc import ABC, abstractmethod
from typing import cast

import pytest

import app as app_pkg
from app.core import plugin as plugin_module
from app.core.capability import BaseNullObject
from app.core.plugin import (
    DEFAULT_CONTRACT_VERSION,
    NULL_PLUGIN_NAME,
    BasePluggable,
    PluginImpl,
    PluginRegistry,
)
from app.core.registry import BaseProviderRegistry
from app.events.base import BaseEventWorker, EventConsumer, EventPublisher
from app.health.registry import HealthCheckRegistry

_EXPECTED_PLUGIN_KEYS = frozenset(
    {
        "archive_policy",
        "archive_query_router",
        "audit",
        "cache",
        "captcha",
        "circuit_breaker",
        "dashboard_card_registry",
        "data_scope",
        "distributed_lock",
        "event",
        "exporter",
        "fallback",
        "field_type_registry",
        "hash_chain",
        "health_check_registry",
        "http_client",
        "idempotency",
        "identity_provider",
        "importer",
        "llm_provider",
        "masking",
        "metrics",
        "notifier",
        "oauth_server",
        "object_storage",
        "password_policy",
        "permission",
        "query_provider_registry",
        "rate_limiter",
        "realtime_publisher",
        "replay_guard",
        "scope_checker",
        "search_index",
        "session_store",
        "sharding",
        "task",
        "tracer",
        "translator",
        "webhook_sender",
        "workflow_engine",
    }
)


_PORTS_WITHOUT_NULL = frozenset({"audit", "cache", "event", "task"})
"""暂无 `NullXxx` 缺省实现的端口（不登记 `null`，随对应阶段补实现）。"""

_PLATFORM_FACTORY_KEYS = frozenset({"masking"})
"""构造需参数（`NullMasker` 需注入 checker），不自动登记、由装配清单显式工厂登记（01_02）。"""


def _collect_app_classes() -> list[type[BasePluggable]]:
    """导入 app 包全部模块并收集 `BasePluggable` 子类（仅 app 模块，过滤测试类）。

    Returns:
        list[type[BasePluggable]]: 应用侧插件子类（含间接子类）。
    """
    for info in pkgutil.walk_packages(app_pkg.__path__, prefix="app."):
        if ".tests" in info.name or info.name.endswith("main"):
            continue
        importlib.import_module(info.name)
    collected: list[type[BasePluggable]] = []
    pending = list(BasePluggable.__subclasses__())
    while pending:
        cls = pending.pop()
        collected.append(cls)
        pending.extend(cls.__subclasses__())
    return [cls for cls in collected if cls.__module__.startswith("app.")]


def _ports() -> list[type[BasePluggable]]:
    """40 个直接 BasePluggable 子类（能力域端口）。

    Returns:
        list[type[BasePluggable]]: 端口基类列表。
    """
    return [
        cls
        for cls in _collect_app_classes()
        if cls is not BaseProviderRegistry and (BasePluggable in cls.__bases__ or BaseProviderRegistry in cls.__bases__)
    ]


def _snapshot_of_app_classes() -> dict[str, dict[str, PluginImpl]]:
    """以独立注册表收集全部应用候选并构建快照。

    Returns:
        dict[str, dict[str, PluginImpl]]: 两级映射（可变副本，便于断言）。
    """
    registry = PluginRegistry()
    for cls in _collect_app_classes():
        registry.collect(cls)
    return {key: dict(bucket) for key, bucket in registry.build().items()}


@pytest.fixture
def registry(monkeypatch: pytest.MonkeyPatch) -> PluginRegistry:
    """隔离注册表：以独立实例替换进程级默认实例（用例类不污染真实默认注册表）。

    Args:
        monkeypatch: pytest 补丁夹具。

    Returns:
        PluginRegistry: 隔离的注册表实例。
    """
    isolated = PluginRegistry()
    monkeypatch.setattr(plugin_module, "_DEFAULT_REGISTRY", isolated)
    return isolated


@pytest.mark.kiwi_id(531)
def test_ports_declared_and_abstract() -> None:
    """40 个端口：清单一致、抽象、三属性自身声明（plugin_key 与 key 一致）。"""
    ports = _ports()
    assert {port.plugin_key for port in ports} == _EXPECTED_PLUGIN_KEYS
    for port in ports:
        assert inspect.isabstract(port), port.__name__
        assert port.plugin_key == port.key
        assert port.__dict__.get("plugin_name") == NULL_PLUGIN_NAME
        assert port.__dict__.get("contract_version") == DEFAULT_CONTRACT_VERSION
        assert re.fullmatch(r"\d+\.\d+\.\d+", port.contract_version)


@pytest.mark.kiwi_id(531)
def test_null_defaults_registered() -> None:
    """Null 缺省登记：有缺省实现的端口 `(plugin_key, null)` 登记为对应 `NullXxx`；无实现 / 需工厂的端口不登记。"""
    snapshot = _snapshot_of_app_classes()
    excluded = _PORTS_WITHOUT_NULL | _PLATFORM_FACTORY_KEYS
    assert set(snapshot) == _EXPECTED_PLUGIN_KEYS - excluded
    for port in _ports():
        if port.plugin_key in excluded:
            assert port.plugin_key not in snapshot
            continue
        assert set(snapshot[port.plugin_key]) == {NULL_PLUGIN_NAME}
        impl = snapshot[port.plugin_key][NULL_PLUGIN_NAME]
        assert isinstance(impl, type)
        assert issubclass(impl, port)
        assert issubclass(impl, BaseNullObject)


@pytest.mark.kiwi_id(531)
def test_abstract_ports_not_registered() -> None:
    """抽象端口不登记：快照实现中不含任何端口类。"""
    snapshot = _snapshot_of_app_classes()
    registered = {impl for bucket in snapshot.values() for impl in bucket.values()}
    assert not (set(_ports()) & registered)


@pytest.mark.kiwi_id(531)
def test_unnamed_concrete_subclass_not_registered() -> None:
    """无名具体子类不登记：`HealthCheckRegistry` 继承到端口申明但自身未声明。"""
    snapshot = _snapshot_of_app_classes()
    registered = {impl for bucket in snapshot.values() for impl in bucket.values()}
    assert HealthCheckRegistry not in registered
    assert HealthCheckRegistry.plugin_name == NULL_PLUGIN_NAME
    assert HealthCheckRegistry.__dict__.get("plugin_name") is None


@pytest.mark.kiwi_id(531)
def test_inherited_declaration_does_not_register(registry: PluginRegistry) -> None:
    """登记规则「自身声明优先」：继承申明不生效、自身声明登记。"""

    class Port(BasePluggable, ABC):
        plugin_key = "test_inherit"
        plugin_name = "parent"

        @abstractmethod
        def work(self) -> None:
            """抽象能力方法。"""

    class Child(Port):
        def work(self) -> None:
            """空实现（自身未声明 plugin_name）。"""

    class Named(Port):
        plugin_name = "named"

        def work(self) -> None:
            """空实现（自身声明实现名）。"""

    class Misdeclared(BasePluggable):
        plugin_key = "test_misdeclared"
        plugin_name = cast("str", 0)

    snapshot = registry.build()
    assert set(snapshot["test_inherit"]) == {"named"}
    assert snapshot["test_inherit"]["named"] is Named
    assert Child.__dict__.get("plugin_name") is None
    assert "test_misdeclared" not in snapshot
    assert Misdeclared.__dict__.get("plugin_name") == 0


@pytest.mark.kiwi_id(531)
def test_event_worker_location_and_abstraction() -> None:
    """事件基座落点：`BaseEventWorker` 在 events/base.py；发布 / 消费抽象不登记。"""
    assert BaseEventWorker.__module__ == "app.events.base"
    assert BaseEventWorker.plugin_key == "event"
    assert issubclass(BaseEventWorker, BasePluggable)
    assert inspect.isabstract(BaseEventWorker)
    assert issubclass(EventPublisher, BaseEventWorker)
    assert issubclass(EventConsumer, BaseEventWorker)
    assert inspect.isabstract(EventPublisher)
    assert inspect.isabstract(EventConsumer)
    snapshot = _snapshot_of_app_classes()
    registered = {impl for bucket in snapshot.values() for impl in bucket.values()}
    assert EventPublisher not in registered
    assert EventConsumer not in registered


@pytest.mark.kiwi_id(531)
async def test_app_starts() -> None:
    """应用可启动：`create_app` + lifespan 进出正常（装配接线前行为不变）。"""
    from app.main import create_app, lifespan

    application = create_app()
    async with lifespan(application):
        assert application.state.startup_complete is True
