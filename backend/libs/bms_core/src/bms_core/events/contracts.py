"""事件契约能力域：契约 / 订阅模型、注册表、命名与兼容校验、快照渲染。

- **事件名规则**：`{已登记事件域}.{对象}.{动作}` 点分小写——首段必须是服务目录
  （`SERVICE_CATALOG` 的 `event_domain`）已登记的事件域，其余段 ≥1 段。
- **契约** `EventContract`：事件类型 + 契约版本（`X.Y.Z`）+ 载荷字段规格 + 说明 + 弃用标记。
  事件是长期契约——字段只增不删、新增必须可选、破坏性变更升主版本（见《架构设计 · 事件总线》
  「幂等与重试」节）。
- **订阅** `EventSubscription`：消费方声明「消费标识 + 事件类型 + 支持主版本集合」，
  用于运行期版本判定与构建期主版本升级覆盖校验（消费方按订阅做新旧兼容）。
- **注册表** `EventContractRegistry`：进程级默认注册表（`default_event_contract_registry()`），
  登记入口 `register_event_contract` / `register_event_subscription`（同值重复登记无操作）。
- **校验**：`validate_event_contract` / `validate_event_registry`（启动与 CLI 共用）；
  **兼容**：`check_event_compatibility` / `check_subscription_coverage` / `check_snapshot_compatibility`。
- **快照**：`render_event_snapshot` / `parse_event_snapshot`（确定性 JSON；`ops/event_contracts.py`
  据此导出 `deploy/events/contracts.json` 与零漂移校验）。
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import cast

from bms_core.core.base import BaseObject
from bms_core.core.exceptions import EventContractError
from bms_core.core.version import contract_major
from bms_core.events.base import DEFAULT_EVENT_VERSION, EventEnvelope

__all__ = [
    "DEFAULT_EVENT_VERSION",
    "EVENT_CONTRACT_MODES",
    "EVENT_CONTRACT_MODE_ENFORCE",
    "EVENT_CONTRACT_MODE_OFF",
    "EVENT_CONTRACT_MODE_WARN",
    "EVENT_FIELD_TYPES",
    "EVENT_SNAPSHOT_PATH",
    "EVENT_TYPE_RE",
    "RESERVED_PAYLOAD_KEYS",
    "EventContract",
    "EventContractRegistry",
    "EventFieldSpec",
    "EventSubscription",
    "check_event_compatibility",
    "check_snapshot_compatibility",
    "check_subscription_coverage",
    "default_event_contract_registry",
    "event_snapshot_payload",
    "event_version_compatible",
    "parse_event_snapshot",
    "register_event_contract",
    "register_event_subscription",
    "render_event_snapshot",
    "require_event_version_compatible",
    "resolve_event_contract",
    "resolve_event_version",
    "validate_event_contract",
    "validate_event_registry",
]

EVENT_TYPE_RE = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$")
"""事件名格式：`{已登记事件域}.{对象}.{动作}` 点分小写（首段为事件域，其余 ≥1 段）。"""

EVENT_FIELD_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")
"""事件载荷字段名格式（小写下划线）。"""

EVENT_FIELD_TYPES: tuple[str, ...] = ("string", "integer", "number", "boolean", "datetime", "object", "array")
"""事件载荷字段类型清单（跨语言通用类型名）。"""

EVENT_CONTRACT_MODE_OFF = "off"
"""签发契约校验模式：不校验。"""

EVENT_CONTRACT_MODE_WARN = "warn"
"""签发契约校验模式：记录告警放行。"""

EVENT_CONTRACT_MODE_ENFORCE = "enforce"
"""签发契约校验模式：未登记 / 版本非法即拒发（10010）。"""

EVENT_CONTRACT_MODES: tuple[str, ...] = (EVENT_CONTRACT_MODE_OFF, EVENT_CONTRACT_MODE_WARN, EVENT_CONTRACT_MODE_ENFORCE)
"""签发契约校验模式清单（`[event].contract_mode`）。"""

RESERVED_PAYLOAD_KEYS: tuple[str, ...] = (
    "event_id",
    "event_type",
    "event_version",
    "occurred_at",
    "tenant_id",
    "trace_id",
    "aggregate_key",
)
"""事件信封保留键（载荷字段不得占用，避免与信封语义冲突）。"""

EVENT_SNAPSHOT_PATH = "deploy/events/contracts.json"
"""事件契约快照路径（相对仓库根；导出 / 零漂移校验用）。"""


@dataclass(frozen=True)
class EventFieldSpec(BaseObject):
    """事件载荷字段规格（对外字段的契约声明）。"""

    type: str = "string"
    """字段类型（`EVENT_FIELD_TYPES`）。"""

    required: bool = False
    """是否必填（新增字段必须为可选，否则属破坏性变更）。"""

    def to_snapshot(self) -> dict[str, object]:
        """渲染为快照条目。

        Returns:
            dict[str, object]: 字段规格快照。
        """
        return {"type": self.type, "required": self.required}

    @classmethod
    def from_snapshot(cls, entry: Mapping[str, object]) -> EventFieldSpec:
        """由快照条目构造。

        Args:
            entry: 字段规格快照。

        Returns:
            EventFieldSpec: 字段规格。
        """
        return cls(type=str(entry.get("type", "string")), required=bool(entry.get("required", False)))


@dataclass(frozen=True)
class EventContract(BaseObject):
    """事件契约：事件类型 + 契约版本 + 载荷字段规格 + 说明 + 弃用标记。"""

    event_type: str
    """事件类型（`{已登记事件域}.{对象}.{动作}`）。"""

    version: str = DEFAULT_EVENT_VERSION
    """契约版本（`X.Y.Z`；破坏性变更升主版本）。"""

    fields: Mapping[str, EventFieldSpec] = field(default_factory=dict[str, EventFieldSpec])
    """载荷字段规格（字段名 → 规格）。"""

    description: str = ""
    """说明（中文触发时机）。"""

    deprecated: bool = False
    """弃用标记（事件类型不物理删除，置弃用保留登记与快照）。"""

    @property
    def domain(self) -> str:
        """事件域（事件名首段）。

        Returns:
            str: 事件域。
        """
        return self.event_type.split(".", 1)[0]

    @property
    def major(self) -> int | None:
        """契约主版本号。

        Returns:
            int | None: 主版本号；版本非法 None。
        """
        return contract_major(self.version)

    def to_snapshot(self) -> dict[str, object]:
        """渲染为快照条目（字段按名排序，确定性输出）。

        Returns:
            dict[str, object]: 契约快照。
        """
        return {
            "event_type": self.event_type,
            "version": self.version,
            "deprecated": self.deprecated,
            "description": self.description,
            "fields": {name: self.fields[name].to_snapshot() for name in sorted(self.fields)},
        }

    @classmethod
    def from_snapshot(cls, entry: Mapping[str, object]) -> EventContract:
        """由快照条目构造。

        Args:
            entry: 契约快照。

        Returns:
            EventContract: 契约。
        """
        raw_fields = cast("Mapping[str, Mapping[str, object]]", entry.get("fields") or {})
        return cls(
            event_type=str(entry["event_type"]),
            version=str(entry.get("version", DEFAULT_EVENT_VERSION)),
            fields={name: EventFieldSpec.from_snapshot(spec) for name, spec in raw_fields.items()},
            description=str(entry.get("description", "")),
            deprecated=bool(entry.get("deprecated", False)),
        )


@dataclass(frozen=True)
class EventSubscription(BaseObject):
    """事件订阅：消费方对某事件的支持声明（消费标识 + 支持主版本集合）。"""

    consumer: str
    """消费方标识（消费组 / 处理者，如 `notification.inbox`）。"""

    event_type: str
    """订阅的事件类型。"""

    supported_majors: tuple[int, ...] = (1,)
    """支持的主版本集合（新旧兼容窗口；须含契约当前主版本）。"""

    description: str = ""
    """说明（中文）。"""

    def accepts(self, version: str | None) -> bool:
        """判定是否接受该事件版本（版本缺省取 `DEFAULT_EVENT_VERSION`）。

        Args:
            version: 事件契约版本。

        Returns:
            bool: 主版本属于支持集合 True。
        """
        major = contract_major(version or DEFAULT_EVENT_VERSION)
        return major is not None and major in self.supported_majors

    def to_snapshot(self) -> dict[str, object]:
        """渲染为快照条目。

        Returns:
            dict[str, object]: 订阅快照。
        """
        return {
            "consumer": self.consumer,
            "event_type": self.event_type,
            "supported_majors": list(self.supported_majors),
            "description": self.description,
        }

    @classmethod
    def from_snapshot(cls, entry: Mapping[str, object]) -> EventSubscription:
        """由快照条目构造。

        Args:
            entry: 订阅快照。

        Returns:
            EventSubscription: 订阅。
        """
        majors = cast("Sequence[object]", entry.get("supported_majors") or [])
        return cls(
            consumer=str(entry["consumer"]),
            event_type=str(entry["event_type"]),
            supported_majors=tuple(int(cast("str | int", major)) for major in majors),
            description=str(entry.get("description", "")),
        )


class EventContractRegistry(BaseObject):
    """事件契约与订阅注册表（进程级默认实例经 `default_event_contract_registry()` 取用）。"""

    def __init__(self) -> None:
        """初始化空注册表。"""
        self._contracts: dict[str, EventContract] = {}
        self._subscriptions: dict[tuple[str, str], EventSubscription] = {}

    def register(self, contract: EventContract) -> None:
        """登记契约（事件类型唯一；同值重复登记无操作）。

        Args:
            contract: 事件契约。

        Raises:
            EventContractError: 事件类型已登记且契约不一致。
        """
        existing = self._contracts.get(contract.event_type)
        if existing is None:
            self._contracts[contract.event_type] = contract
            return
        if existing != contract:
            raise EventContractError(f"事件契约重复登记（事件类型已存在且不一致）：{contract.event_type}")

    def register_subscription(self, subscription: EventSubscription) -> None:
        """登记订阅（(消费方, 事件类型) 唯一；同值重复登记无操作）。

        Args:
            subscription: 事件订阅。

        Raises:
            EventContractError: 订阅已登记且声明不一致。
        """
        key = (subscription.event_type, subscription.consumer)
        existing = self._subscriptions.get(key)
        if existing is None:
            self._subscriptions[key] = subscription
            return
        if existing != subscription:
            raise EventContractError(
                f"事件订阅重复登记（消费方与事件类型已存在且不一致）："
                f"{subscription.consumer} ← {subscription.event_type}"
            )

    def contract(self, event_type: str) -> EventContract | None:
        """取事件契约。

        Args:
            event_type: 事件类型。

        Returns:
            EventContract | None: 契约；未登记 None。
        """
        return self._contracts.get(event_type)

    def contracts(self) -> tuple[EventContract, ...]:
        """契约清单（按事件类型排序）。

        Returns:
            tuple[EventContract, ...]: 契约清单。
        """
        return tuple(self._contracts[key] for key in sorted(self._contracts))

    def subscriptions(self) -> tuple[EventSubscription, ...]:
        """订阅清单（按事件类型 + 消费方排序）。

        Returns:
            tuple[EventSubscription, ...]: 订阅清单。
        """
        return tuple(self._subscriptions[key] for key in sorted(self._subscriptions))

    def subscriptions_for(self, event_type: str) -> tuple[EventSubscription, ...]:
        """取某事件的全部订阅（按消费方排序）。

        Args:
            event_type: 事件类型。

        Returns:
            tuple[EventSubscription, ...]: 订阅清单。
        """
        return tuple(
            self._subscriptions[key]
            for key in sorted(self._subscriptions)
            if self._subscriptions[key].event_type == event_type
        )

    def resolve_version(self, event_type: str) -> str:
        """取事件当前契约版本（未登记回落 `DEFAULT_EVENT_VERSION`）。

        Args:
            event_type: 事件类型。

        Returns:
            str: 契约版本。
        """
        contract = self._contracts.get(event_type)
        return contract.version if contract is not None else DEFAULT_EVENT_VERSION


_DEFAULT_REGISTRY = EventContractRegistry()


def default_event_contract_registry() -> EventContractRegistry:
    """取进程级默认事件契约注册表（装配登记幂等 / 测试隔离使用）。

    Returns:
        EventContractRegistry: 默认注册表实例。
    """
    return _DEFAULT_REGISTRY


def register_event_contract(contract: EventContract, *, registry: EventContractRegistry | None = None) -> None:
    """登记事件契约到默认注册表（同值重复登记无操作）。

    Args:
        contract: 事件契约。
        registry: 目标注册表（缺省默认注册表；测试可传隔离实例）。
    """
    (registry or _DEFAULT_REGISTRY).register(contract)


def register_event_subscription(
    subscription: EventSubscription, *, registry: EventContractRegistry | None = None
) -> None:
    """登记事件订阅到默认注册表（同值重复登记无操作）。

    Args:
        subscription: 事件订阅。
        registry: 目标注册表（缺省默认注册表；测试可传隔离实例）。
    """
    (registry or _DEFAULT_REGISTRY).register_subscription(subscription)


def resolve_event_contract(event_type: str, *, registry: EventContractRegistry | None = None) -> EventContract | None:
    """取事件契约（默认注册表）。

    Args:
        event_type: 事件类型。
        registry: 目标注册表（缺省默认注册表）。

    Returns:
        EventContract | None: 契约；未登记 None。
    """
    return (registry or _DEFAULT_REGISTRY).contract(event_type)


def resolve_event_version(event_type: str, *, registry: EventContractRegistry | None = None) -> str:
    """取事件当前契约版本（未登记回落 `DEFAULT_EVENT_VERSION`）。

    Args:
        event_type: 事件类型。
        registry: 目标注册表（缺省默认注册表）。

    Returns:
        str: 契约版本。
    """
    return (registry or _DEFAULT_REGISTRY).resolve_version(event_type)


def validate_event_contract(contract: EventContract, *, domains: frozenset[str] | None = None) -> tuple[str, ...]:
    """校验单个契约（命名 / 事件域 / 版本 / 字段）。

    Args:
        contract: 事件契约。
        domains: 已登记事件域集合；None 跳过事件域校验。

    Returns:
        tuple[str, ...]: 违规明细；空元组通过。
    """
    errors: list[str] = []
    if not EVENT_TYPE_RE.fullmatch(contract.event_type):
        errors.append(f"事件名非法（应为「已登记事件域.对象.动作」点分小写）：{contract.event_type}")
    elif domains is not None and contract.domain not in domains:
        errors.append(f"事件域未登记：{contract.domain}（事件 {contract.event_type}）")
    if contract.major is None:
        errors.append(f"契约版本非法（应为 X.Y.Z）：{contract.event_type}@{contract.version}")
    for name, spec in contract.fields.items():
        if not EVENT_FIELD_NAME_RE.fullmatch(name):
            errors.append(f"字段名非法（应为小写下划线）：{contract.event_type}.{name}")
        if name in RESERVED_PAYLOAD_KEYS:
            errors.append(f"字段名占用事件信封保留键：{contract.event_type}.{name}")
        if spec.type not in EVENT_FIELD_TYPES:
            errors.append(f"字段类型非法：{contract.event_type}.{name}（{spec.type}）")
    return tuple(errors)


def validate_event_registry(
    registry: EventContractRegistry, *, domains: frozenset[str] | None = None
) -> tuple[str, ...]:
    """校验注册表（契约 + 订阅；启动与 CLI 共用）。

    Args:
        registry: 事件契约注册表。
        domains: 已登记事件域集合；None 跳过事件域校验。

    Returns:
        tuple[str, ...]: 违规明细；空元组通过。
    """
    errors: list[str] = []
    for contract in registry.contracts():
        errors.extend(validate_event_contract(contract, domains=domains))
    for subscription in registry.subscriptions():
        label = f"{subscription.consumer} ← {subscription.event_type}"
        contract = registry.contract(subscription.event_type)
        if contract is None:
            errors.append(f"订阅的事件未登记契约：{label}")
            continue
        if not subscription.supported_majors:
            errors.append(f"订阅支持主版本集合为空：{label}")
            continue
        if any(major <= 0 for major in subscription.supported_majors):
            errors.append(f"订阅支持主版本非法（应为正整数）：{label}")
            continue
        if contract.major is not None and contract.major not in subscription.supported_majors:
            errors.append(
                f"订阅未覆盖契约当前主版本 {contract.major}（支持 {sorted(subscription.supported_majors)}）：{label}"
            )
    return tuple(errors)


def _version_tuple(version: str) -> tuple[int, int, int] | None:
    """解析版本为三元组。

    Args:
        version: 契约版本。

    Returns:
        tuple[int, int, int] | None: 版本三元组；格式非法 None。
    """
    if contract_major(version) is None:
        return None
    major, minor, patch = version.split(".")
    return int(major), int(minor), int(patch)


def check_event_compatibility(previous: EventContract, current: EventContract) -> tuple[str, ...]:
    """兼容校验（只增不删 / 新增可选 / 破坏性升主版本）。

    Args:
        previous: 变更前契约（快照）。
        current: 变更后契约（现行注册表）。

    Returns:
        tuple[str, ...]: 违规明细；空元组兼容。
    """
    if previous.event_type != current.event_type:
        return (f"事件类型不一致：{previous.event_type} → {current.event_type}",)
    previous_version = _version_tuple(previous.version)
    current_version = _version_tuple(current.version)
    if previous_version is None or current_version is None:
        return (f"契约版本非法：{previous.event_type}（{previous.version} → {current.version}）",)

    violations: list[str] = []
    breaking = False
    for name, spec in previous.fields.items():
        if name not in current.fields:
            violations.append(f"字段只增不删，禁止删除：{current.event_type}.{name}")
            breaking = True
        elif current.fields[name].type != spec.type:
            violations.append(
                f"字段类型变更属破坏性：{current.event_type}.{name}（{spec.type} → {current.fields[name].type}）"
            )
            breaking = True
        elif current.fields[name].required != spec.required:
            violations.append(f"字段必填性变更属破坏性：{current.event_type}.{name}")
            breaking = True
    for name, spec in current.fields.items():
        if name not in previous.fields and spec.required:
            violations.append(f"新增字段必须可选：{current.event_type}.{name}")
            breaking = True
    if previous.deprecated and not current.deprecated:
        violations.append(f"弃用标记不可回退：{current.event_type}")
        breaking = True

    structured = previous.fields != current.fields or previous.deprecated != current.deprecated
    if current_version < previous_version:
        violations.append(f"契约版本不得回退：{current.event_type}（{previous.version} → {current.version}）")
    elif structured and current_version == previous_version:
        violations.append(f"契约结构变更必须升版本：{current.event_type}（仍为 {current.version}）")
    elif breaking and current_version[0] <= previous_version[0]:
        violations.append(
            f"存在破坏性变更，必须升主版本：{current.event_type}（{previous.version} → {current.version}）"
        )
    elif structured and not breaking and current_version[:2] == previous_version[:2]:
        violations.append(f"契约字段变更至少升次版本：{current.event_type}（{previous.version} → {current.version}）")
    return tuple(violations)


def check_subscription_coverage(
    previous: EventContract | None,
    current: EventContract,
    subscriptions: Sequence[EventSubscription],
) -> tuple[str, ...]:
    """订阅覆盖校验：主版本升级（或新增契约）时消费方须已支持新主版本。

    Args:
        previous: 变更前契约；新增契约 None。
        current: 变更后契约。
        subscriptions: 该事件的订阅清单。

    Returns:
        tuple[str, ...]: 违规明细；空元组通过。
    """
    current_major = current.major
    if current_major is None:
        return (f"契约版本非法：{current.event_type}@{current.version}",)
    previous_major = previous.major if previous is not None else None
    if previous_major is not None and current_major <= previous_major:
        return ()
    return tuple(
        f"主版本升级未覆盖订阅：{current.event_type}@{current.version} 需消费方 {subscription.consumer} "
        f"支持主版本 {current_major}（现支持 {sorted(subscription.supported_majors)}）"
        for subscription in subscriptions
        if current_major not in subscription.supported_majors
    )


def check_snapshot_compatibility(previous: Sequence[EventContract], registry: EventContractRegistry) -> tuple[str, ...]:
    """快照 → 现行注册表的兼容校验（事件类型不得消失 + 逐事件兼容 + 订阅覆盖）。

    Args:
        previous: 快照中的契约清单。
        registry: 现行注册表。

    Returns:
        tuple[str, ...]: 违规明细；空元组通过。
    """
    errors: list[str] = []
    previous_by_type = {contract.event_type: contract for contract in previous}
    current_by_type = {contract.event_type: contract for contract in registry.contracts()}
    for event_type, previous_contract in previous_by_type.items():
        current_contract = current_by_type.get(event_type)
        if current_contract is None:
            errors.append(f"事件类型不得删除（如需弃用请置 deprecated=True）：{event_type}")
            continue
        errors.extend(check_event_compatibility(previous_contract, current_contract))
    for current_contract in current_by_type.values():
        errors.extend(
            check_subscription_coverage(
                previous_by_type.get(current_contract.event_type),
                current_contract,
                registry.subscriptions_for(current_contract.event_type),
            )
        )
    return tuple(errors)


def event_version_compatible(contract: EventContract, version: str | None) -> bool:
    """判定事件版本与契约主版本兼容（主版本一致即兼容）。

    Args:
        contract: 事件契约。
        version: 事件契约版本（缺省取 `DEFAULT_EVENT_VERSION`）。

    Returns:
        bool: 主版本一致 True；版本非法 False。
    """
    expected = contract.major
    actual = contract_major(version or DEFAULT_EVENT_VERSION)
    return expected is not None and actual == expected


def require_event_version_compatible(subscription: EventSubscription, event: EventEnvelope) -> None:
    """消费方版本前置校验：不支持事件主版本即抛 `EventContractError`（10010）。

    Args:
        subscription: 消费方订阅声明。
        event: 收到的事件信封。

    Raises:
        EventContractError: 事件主版本不在订阅支持集合内。
    """
    if not subscription.accepts(event.event_version):
        raise EventContractError(
            f"消费方 {subscription.consumer} 不支持事件版本："
            f"{event.event_type}@{event.event_version or DEFAULT_EVENT_VERSION}"
        )


def event_snapshot_payload(registry: EventContractRegistry) -> dict[str, object]:
    """渲染快照载荷（契约 + 订阅，接口清单按类型排序）。

    Args:
        registry: 事件契约注册表。

    Returns:
        dict[str, object]: 快照载荷。
    """
    return {
        "contracts": [contract.to_snapshot() for contract in registry.contracts()],
        "subscriptions": [subscription.to_snapshot() for subscription in registry.subscriptions()],
    }


def render_event_snapshot(registry: EventContractRegistry) -> str:
    """确定性渲染快照文本（缩进 2 / 键排序 / 非 ASCII 直出 / 尾换行）。

    Args:
        registry: 事件契约注册表。

    Returns:
        str: 快照文本（同代码同文本，供 Git 比对与零漂移校验）。
    """
    return json.dumps(event_snapshot_payload(registry), ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def parse_event_snapshot(payload: object) -> tuple[tuple[EventContract, ...], tuple[EventSubscription, ...]]:
    """解析快照载荷为契约与订阅清单。

    Args:
        payload: 快照载荷（JSON 反序列化结果）。

    Returns:
        tuple[tuple[EventContract, ...], tuple[EventSubscription, ...]]: （契约清单，订阅清单）。

    Raises:
        EventContractError: 快照结构非法。
    """
    if not isinstance(payload, dict):
        raise EventContractError("事件契约快照结构非法（应为 JSON 对象）")
    data = cast("dict[str, object]", payload)
    try:
        contracts = tuple(
            EventContract.from_snapshot(entry)
            for entry in cast("list[Mapping[str, object]]", data.get("contracts") or [])
        )
        subscriptions = tuple(
            EventSubscription.from_snapshot(entry)
            for entry in cast("list[Mapping[str, object]]", data.get("subscriptions") or [])
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise EventContractError(f"事件契约快照解析失败：{exc!r}") from exc
    return contracts, subscriptions
