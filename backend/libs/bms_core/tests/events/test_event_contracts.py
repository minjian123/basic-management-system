"""事件契约用例（Kiwi 2174）：契约 / 订阅模型、注册表校验、兼容规则、快照渲染与解析。

无数据库依赖：注册表为内存结构，测试使用隔离实例（不污染进程级默认注册表）。
"""

import json
from collections.abc import Mapping

import pytest

from bms_core.core.exceptions import EventContractError
from bms_core.events.base import EventEnvelope
from bms_core.events.contracts import (
    DEFAULT_EVENT_VERSION,
    EventContract,
    EventContractRegistry,
    EventFieldSpec,
    EventSubscription,
    check_event_compatibility,
    check_snapshot_compatibility,
    check_subscription_coverage,
    event_version_compatible,
    parse_event_snapshot,
    register_event_contract,
    register_event_subscription,
    render_event_snapshot,
    require_event_version_compatible,
    resolve_event_contract,
    resolve_event_version,
    validate_event_contract,
    validate_event_registry,
)

DOMAINS = frozenset({"sys", "wf"})
_USER_FIELDS: Mapping[str, EventFieldSpec] = {"user_id": EventFieldSpec(type="string", required=True)}


def _contract(
    event_type: str = "sys.user.created",
    version: str = "1.0.0",
    fields: Mapping[str, EventFieldSpec] | None = None,
    description: str = "用户创建后",
    deprecated: bool = False,
) -> EventContract:
    """构造事件契约（默认合法）。"""
    return EventContract(
        event_type=event_type,
        version=version,
        fields=dict(_USER_FIELDS) if fields is None else fields,
        description=description,
        deprecated=deprecated,
    )


def _subscription(
    consumer: str = "indexer",
    event_type: str = "sys.user.created",
    majors: tuple[int, ...] = (1,),
    description: str = "索引同步",
) -> EventSubscription:
    """构造事件订阅（默认合法）。"""
    return EventSubscription(consumer=consumer, event_type=event_type, supported_majors=majors, description=description)


@pytest.mark.kiwi_id(2174)
def test_validate_contract_accepts_and_reports_all_violations() -> None:
    """合法契约通过；命名 / 事件域 / 版本 / 字段 / 保留键违规逐项检出。"""
    assert validate_event_contract(_contract(), domains=DOMAINS) == ()

    errors = validate_event_contract(_contract(event_type="Bad"), domains=DOMAINS)
    assert any("事件名非法" in error for error in errors)
    assert validate_event_contract(_contract(event_type="ghost.thing.created"), domains=DOMAINS) != ()
    assert any(
        "事件域未登记" in error
        for error in validate_event_contract(_contract(event_type="ghost.thing.created"), domains=DOMAINS)
    )
    assert any("契约版本非法" in error for error in validate_event_contract(_contract(version="v1")))
    bad_fields = {
        "Bad-Name": EventFieldSpec(type="string"),
        "event_id": EventFieldSpec(type="string"),
        "ok": EventFieldSpec(type="money"),
    }
    errors = validate_event_contract(_contract(fields=bad_fields))
    assert any("字段名非法" in error for error in errors)
    assert any("保留键" in error for error in errors)
    assert any("字段类型非法" in error for error in errors)


@pytest.mark.kiwi_id(2174)
def test_registry_register_idempotent_and_conflict() -> None:
    """同值重复登记无操作；同事件类型不同契约拒登；订阅同口径。"""
    registry = EventContractRegistry()
    contract = _contract()
    registry.register(contract)
    registry.register(_contract())
    assert len(registry.contracts()) == 1
    with pytest.raises(EventContractError):
        registry.register(_contract(version="1.1.0"))

    subscription = _subscription()
    registry.register_subscription(subscription)
    registry.register_subscription(_subscription())
    assert len(registry.subscriptions()) == 1
    with pytest.raises(EventContractError):
        registry.register_subscription(_subscription(majors=(1, 2)))

    assert registry.contract("sys.user.created") == contract
    assert registry.contract("ghost.thing.created") is None
    assert registry.subscriptions_for("sys.user.created") == (subscription,)
    assert registry.subscriptions_for("wf.instance.started") == ()
    assert registry.resolve_version("sys.user.created") == "1.0.0"
    assert registry.resolve_version("ghost.thing.created") == DEFAULT_EVENT_VERSION


@pytest.mark.kiwi_id(2174)
def test_contract_module_functions_with_isolated_registry() -> None:
    """模块级登记 / 解析入口支持传入隔离注册表。"""
    registry = EventContractRegistry()
    register_event_contract(_contract(), registry=registry)
    register_event_subscription(_subscription(), registry=registry)
    assert resolve_event_contract("sys.user.created", registry=registry) is not None
    assert resolve_event_contract("ghost.thing.created", registry=registry) is None
    assert resolve_event_version("sys.user.created", registry=registry) == "1.0.0"
    assert resolve_event_version("ghost.thing.created", registry=registry) == DEFAULT_EVENT_VERSION


@pytest.mark.kiwi_id(2174)
def test_subscription_validation_and_version_acceptance() -> None:
    """订阅校验：未登记事件 / 空主版本集 / 主版本非法 / 未覆盖当前主版本；运行时接受判定。"""
    registry = EventContractRegistry()
    registry.register(_contract(version="2.1.0"))

    registry.register_subscription(_subscription(event_type="ghost.thing.created", majors=(1,)))
    registry.register_subscription(_subscription(consumer="empty", majors=()))
    registry.register_subscription(_subscription(consumer="bad-major", majors=(0,)))
    registry.register_subscription(_subscription(consumer="stale", majors=(1,)))
    registry.register_subscription(_subscription(consumer="ready", majors=(1, 2)))

    errors = validate_event_registry(registry, domains=DOMAINS)
    assert any("未登记契约" in error for error in errors)
    assert any("集合为空" in error for error in errors)
    assert any("主版本非法" in error for error in errors)
    assert any("未覆盖契约当前主版本" in error for error in errors)

    ready = _subscription(consumer="ready", majors=(1, 2))
    assert ready.accepts("2.3.0") is True
    assert ready.accepts(None) is True
    assert ready.accepts("v2") is False
    assert _subscription(majors=(2,)).accepts(None) is False
    with pytest.raises(EventContractError):
        require_event_version_compatible(ready, EventEnvelope(event_type="sys.user.created", event_version="3.0.0"))
    require_event_version_compatible(ready, EventEnvelope(event_type="sys.user.created", event_version="2.0.0"))

    assert event_version_compatible(_contract(version="2.1.0"), "2.0.0") is True
    assert event_version_compatible(_contract(version="2.1.0"), "1.0.0") is False
    assert event_version_compatible(_contract(version="2.1.0"), "bad") is False
    assert event_version_compatible(_contract(version="bad"), "1.0.0") is False


@pytest.mark.kiwi_id(2174)
def test_compatibility_rules() -> None:
    """兼容规则逐条：只增不删 / 新增可选 / 破坏性升主版本 / 版本递增。"""
    base = _contract()

    assert check_event_compatibility(base, _contract(version="1.0.1", description="措辞更新")) == ()

    additive = _contract(version="1.1.0", fields={**_USER_FIELDS, "dept_id": EventFieldSpec(type="string")})
    assert check_event_compatibility(base, additive) == ()

    assert (
        check_event_compatibility(base, _contract(version="1.0.0", fields={**_USER_FIELDS, "extra": EventFieldSpec()}))
        != ()
    )
    assert any(
        "必须升版本" in error
        for error in check_event_compatibility(
            base, _contract(version="1.0.0", fields={**_USER_FIELDS, "extra": EventFieldSpec()})
        )
    )

    required_added = _contract(
        version="1.1.0", fields={**_USER_FIELDS, "extra": EventFieldSpec(type="string", required=True)}
    )
    errors = check_event_compatibility(base, required_added)
    assert any("新增字段必须可选" in error for error in errors)
    assert any("必须升主版本" in error for error in errors)

    major_ok = _contract(
        version="2.0.0", fields={**_USER_FIELDS, "extra": EventFieldSpec(type="string", required=True)}
    )
    errors = check_event_compatibility(base, major_ok)
    assert any("新增字段必须可选" in error for error in errors)
    assert not any("必须升主版本" in error for error in errors)

    assert any("禁止删除" in error for error in check_event_compatibility(base, _contract(version="2.0.0", fields={})))
    assert any(
        "字段类型变更" in error
        for error in check_event_compatibility(
            base, _contract(version="2.0.0", fields={"user_id": EventFieldSpec(type="integer", required=True)})
        )
    )
    assert any(
        "必填性变更" in error
        for error in check_event_compatibility(
            base, _contract(version="2.0.0", fields={"user_id": EventFieldSpec(type="string")})
        )
    )
    assert any(
        "弃用标记不可回退" in error
        for error in check_event_compatibility(_contract(deprecated=True), _contract(version="2.0.0"))
    )
    assert any("版本不得回退" in error for error in check_event_compatibility(_contract(version="2.0.0"), base))
    assert any(
        "事件类型不一致" in error
        for error in check_event_compatibility(base, _contract(event_type="wf.task.completed"))
    )
    assert any("契约版本非法" in error for error in check_event_compatibility(base, _contract(version="bad")))
    assert any("至少升次版本" in error for error in check_event_compatibility(base, _additive_but_patch()))


def _additive_but_patch() -> EventContract:
    """新增可选字段但只升补丁版本（违规样例）。

    Returns:
        EventContract: 违规契约。
    """
    return _contract(version="1.0.1", fields={**_USER_FIELDS, "dept_id": EventFieldSpec(type="string")})


@pytest.mark.kiwi_id(2174)
def test_subscription_coverage_and_snapshot_compatibility() -> None:
    """主版本升级订阅覆盖校验；快照 → 现行注册表（事件类型不得消失 + 逐事件兼容）。"""
    previous = _contract()
    upgraded = _contract(version="2.0.0", fields={**_USER_FIELDS, "dept_id": EventFieldSpec(type="string")})
    stale = _subscription(majors=(1,))
    ready = _subscription(majors=(1, 2))

    errors = check_subscription_coverage(previous, upgraded, [stale])
    assert any("主版本升级未覆盖订阅" in error for error in errors)
    assert check_subscription_coverage(previous, upgraded, [ready]) == ()
    assert check_subscription_coverage(previous, previous, [stale]) == ()
    assert check_subscription_coverage(None, upgraded, [stale]) != ()
    assert check_subscription_coverage(previous, _contract(version="bad"), [ready]) != ()

    registry = EventContractRegistry()
    registry.register(_contract())
    errors = check_snapshot_compatibility([_contract(), _contract(event_type="wf.instance.finished")], registry)
    assert any("事件类型不得删除" in error for error in errors)

    registry = EventContractRegistry()
    registry.register(_contract(version="1.0.0"))
    assert check_snapshot_compatibility([_contract()], registry) == ()
    registry.register(_contract(event_type="wf.instance.finished", version="2.0.0"))
    registry.register_subscription(_subscription(event_type="wf.instance.finished", majors=(1,)))
    errors = check_snapshot_compatibility([_contract()], registry)
    assert any("主版本升级未覆盖订阅" in error for error in errors)


@pytest.mark.kiwi_id(2174)
def test_snapshot_render_deterministic_and_parse_roundtrip() -> None:
    """快照渲染确定性（同内容同文本）；解析回环等值；非法结构抛错。"""
    registry = EventContractRegistry()
    registry.register(_contract())
    registry.register(_contract(event_type="wf.instance.finished", version="1.2.0"))
    registry.register_subscription(_subscription())

    text = render_event_snapshot(registry)
    assert text == render_event_snapshot(registry)
    assert text.endswith("\n")

    contracts, subscriptions = parse_event_snapshot(json.loads(text))
    assert contracts == registry.contracts()
    assert subscriptions == registry.subscriptions()

    with pytest.raises(EventContractError):
        parse_event_snapshot([])
    with pytest.raises(EventContractError):
        parse_event_snapshot({"contracts": [{"version": "1.0.0"}]})
    with pytest.raises(EventContractError):
        parse_event_snapshot(
            {"subscriptions": [{"consumer": "x", "event_type": "sys.user.created", "supported_majors": ["bad"]}]}
        )
