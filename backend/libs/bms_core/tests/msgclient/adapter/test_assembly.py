"""07B `06_01` 步 2 用例（Kiwi 2441）：msg 适配的装配点、地址 / 命名空间解析与拒启。

拒启语义是这一步的唯一「运行期硬约束」：`provider = "msg"` 但地址或命名空间不可用时，
必须在**装配期**报明确错，而不是首次调用时静默回落到 `http` / `null` 发布器。
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi import FastAPI

from bms_core.core import assembly
from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.config import Settings
from bms_core.core.exceptions import ConfigError
from bms_core.core.plugin import default_plugin_registry, resolve_plugin
from bms_core.core.resources import ResourceManager
from bms_core.events.base import EventPublisher
from bms_core.msgclient.adapter.event_publisher import MsgEventPublisher
from bms_core.msgclient.adapter.service_client import MsgServiceClient
from bms_core.msgclient.instances import InstanceUnavailable
from bms_core.servicecall.base import SERVICE_CLIENT_OPTION_BASE_URL, BaseServiceClient

pytestmark = pytest.mark.kiwi_id(2441)


def _settings(*, endpoint: str | None = None, namespace: str | None = None, service: str = "biz") -> Settings:
    """构造一份可控配置（服务标识 / 端点覆盖 / 命名空间）。"""
    settings = Settings()
    settings.app.service = service
    if endpoint is not None:
        settings.service_client.endpoints["msg"] = endpoint
    if namespace is not None:
        settings.event.options.set("namespace", namespace)
    return settings


@pytest.fixture
def assembled() -> Iterator[Settings]:
    """在真实装配顺序下注册全部平台插件（工厂 create 依赖 rate_limiter / service_token 已登记）。"""
    registry = default_plugin_registry()
    registry.reset()
    settings = _settings(namespace="bms")
    assembly.register_platform_plugins(settings, FastAPI(), ResourceManager())
    try:
        yield settings
    finally:
        registry.reset()


def test_base_url_prefers_endpoint_override() -> None:
    """有端点覆盖时用覆盖值（本机裸跑由开发脚本注入，不改 hosts）。"""
    settings = _settings(endpoint="http://127.0.0.1:9100/")
    assert assembly.msg_base_url(settings) == "http://127.0.0.1:9100"


def test_base_url_prefers_instances_list() -> None:
    """多实例列表优先于端点覆盖与模板（事件发布取第一个）。"""
    settings = _settings()
    settings.service_client.instances["msg"] = ConcurrentStableList(["http://a:8000", "http://b:8000"])
    settings.service_client.endpoints["msg"] = "http://endpoint:8000"
    assert assembly.msg_base_url(settings) == "http://a:8000"


def test_instance_policy_defaults_to_round_robin() -> None:
    """未配置策略时缺省轮询。"""
    policy = assembly.msg_instance_policy(_settings())
    assert policy.strategy.value == "round_robin"


def test_instance_policy_accepts_least_inflight() -> None:
    """配置 `least_inflight` 生效。"""
    settings = _settings()
    settings.service_client.options.set(assembly.MSG_INSTANCE_STRATEGY_OPTION, "least_inflight")
    assert assembly.msg_instance_policy(settings).strategy.value == "least_inflight"


def test_instance_policy_rejects_unknown_value() -> None:
    """非法策略拒启（不静默回落轮询）。"""
    settings = _settings()
    settings.service_client.options.set(assembly.MSG_INSTANCE_STRATEGY_OPTION, "random")
    with pytest.raises(ConfigError, match="instance_strategy"):
        assembly.msg_instance_policy(settings)


def test_base_url_falls_back_to_template() -> None:
    """无覆盖时按基址模板派生（`{service}` 取 `msg`）。"""
    settings = _settings()
    assert assembly.msg_base_url(settings) == "http://msg:8000"


def test_base_url_rejects_template_without_placeholder() -> None:
    """模板缺 `{service}` 占位 → 装配期拒启（不静默回落）。"""
    settings = _settings()
    settings.service_client.options.set(SERVICE_CLIENT_OPTION_BASE_URL, "http://msg:8000")
    with pytest.raises(ConfigError, match="base_url_template"):
        assembly.msg_base_url(settings)


def test_base_url_rejects_non_http_derived() -> None:
    """派生结果不是 http(s) 绝对地址 → 拒启。"""
    settings = _settings()
    settings.service_client.options.set(SERVICE_CLIENT_OPTION_BASE_URL, "{service}:8000")
    with pytest.raises(ConfigError, match="http"):
        assembly.msg_base_url(settings)


def test_namespace_prefers_option() -> None:
    """`[event].options.namespace` 优先。"""
    assert assembly.msg_namespace(_settings(namespace="bms")) == "bms"


def test_namespace_falls_back_to_service() -> None:
    """未配选项时回落调用方服务标识（msg 侧要求是已启用 `module_key`）。"""
    assert assembly.msg_namespace(_settings(service="biz")) == "biz"


def test_namespace_requires_config() -> None:
    """两处都空 → 装配期拒启（空串会被 msg 判 `350010`）。"""
    settings = _settings(service="")
    settings.event.options.set("namespace", "")
    with pytest.raises(ConfigError, match="namespace"):
        assembly.msg_namespace(settings)


def test_service_client_factory_creates_msg_client(assembled: Settings) -> None:
    """工厂产出 `MsgServiceClient`（地址在构造期解析，不建连）。"""
    client = assembly.MsgServiceClientFactory(assembled).create()
    assert isinstance(client, MsgServiceClient)
    assert client.plugin_name == "msg"


def test_service_client_factory_rejects_unavailable_instances(
    assembled: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """目录不可用：装配期拒启（不把错误推迟到首次调用）。"""

    def _raise(self: object, service: str) -> object:
        raise InstanceUnavailable("empty", pool_key="msg", reason="empty_snapshot")

    monkeypatch.setattr(assembly.ServiceCatalogInstanceProvider, "resolve", _raise)
    with pytest.raises(ConfigError, match="实例不可用"):
        assembly.MsgServiceClientFactory(assembled).create()


def test_event_publisher_factory_creates_msg_publisher() -> None:
    """工厂产出 `MsgEventPublisher`（命名空间在构造期解析）。"""
    publisher = assembly.MsgEventPublisherFactory(_settings(namespace="bms")).create()
    assert isinstance(publisher, MsgEventPublisher)
    assert publisher.plugin_name == "msg"


def test_event_publisher_factory_rejects_missing_namespace() -> None:
    """命名空间缺失时工厂直接拒启（不产出「发不出去」的发布器）。"""
    settings = _settings(service="")
    settings.event.options.set("namespace", "")
    with pytest.raises(ConfigError):
        assembly.MsgEventPublisherFactory(settings).create()


def test_register_platform_plugins_exposes_msg_provider(assembled: Settings) -> None:
    """装配后 `provider = "msg"` 能解析出两个实现（同一份注册表、不另造路径）。"""
    client = resolve_plugin("service_client", "msg", expected_version=BaseServiceClient.contract_version)
    publisher = resolve_plugin("event", "msg", expected_version=EventPublisher.contract_version)
    assert isinstance(client, MsgServiceClient)
    assert isinstance(publisher, MsgEventPublisher)
