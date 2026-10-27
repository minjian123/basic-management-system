"""三档失败语义中的「降级声明」与统一执行入口（07B `02_02`）。

- **声明落在消费方**（提供方无权替消费者决定能否接受空集）：`CapabilityUsage(name, degrade, reason)`；
- **装载期校验**（`validate_capability_usages`）：声明必须指向已登记能力、`degrade != none` 必须给理由、
  `stale` 在无投影来源前一律拒（无法兑现的承诺不开）、写 / 强一致能力不得声明降级 → 失败即 `CatalogError` 拒启；
- **统一执行入口**（`call_capability`）：解析 → 调用 → 失败时**仅按声明**降级（输出 `WARNING` 结构化日志 +
  指标计数）→ 返回兜底值；未声明降级（或无声明）时失败原样上抛。

指标口径：`bms_capability_degrade_total{capability, consumer, mode}`、
`bms_capability_resolve_error_total{capability, consumer}`（均登记于 `METRIC_NAMES`）；
审计不落链（读侧降级属运行态，非业务变更）。
"""

from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass

from bms_core.collaboration.base import WRITE_KINDS, CapabilityEndpoint
from bms_core.collaboration.resolver import resolve_capability
from bms_core.core.concurrent import (
    ConcurrentStableDict,
    ConcurrentStableFrozenList,
    ConcurrentStableList,
)
from bms_core.core.exceptions import CatalogError
from bms_core.core.logging import get_logger
from bms_core.core.objects import BaseValueObject
from bms_core.metrics.base import BaseMetrics, MetricLabels
from bms_core.services.module_registry import CollaborationStatus, collaboration_catalog_view

__all__ = [
    "DEGRADE_EMPTY",
    "DEGRADE_MODES",
    "DEGRADE_NONE",
    "DEGRADE_STALE",
    "METRIC_CAPABILITY_DEGRADE",
    "METRIC_CAPABILITY_RESOLVE_ERROR",
    "CapabilityUsage",
    "call_capability",
    "capability_usage_view",
    "capability_usages",
    "find_capability_usage",
    "inspect_capability_usages",
    "register_capability_usages",
    "reset_capability_usages",
    "validate_capability_usages",
]

DEGRADE_NONE = "none"
"""不降级（缺省；失败即上抛）。"""

DEGRADE_EMPTY = "empty"
"""有界降级：返回空集。"""

DEGRADE_STALE = "stale"
"""有界降级：返回旧副本（本地投影来源；**本任务未落地，声明即拒启**）。"""

DEGRADE_MODES: ConcurrentStableFrozenList[str] = ConcurrentStableFrozenList(
    (DEGRADE_NONE, DEGRADE_EMPTY, DEGRADE_STALE)
)
"""降级模式取值集合。"""

METRIC_CAPABILITY_DEGRADE = "bms_capability_degrade_total"
"""降级计数指标名（`{capability, consumer, mode}`）。"""

METRIC_CAPABILITY_RESOLVE_ERROR = "bms_capability_resolve_error_total"
"""能力取用失败计数指标名（`{capability, consumer}`；契约断链，不可降级）。"""

_LOGGER = "bms_core.collaboration"


@dataclass(frozen=True)
class CapabilityUsage(BaseValueObject):
    """消费方对某能力的**使用登记**（含降级策略）。"""

    name: str
    """能力名（装载期校验须已登记）。"""

    degrade: str = DEGRADE_NONE
    """降级模式（`none` / `empty` / `stale`；缺省不降级）。"""

    reason: str = ""
    """降级理由（`degrade != none` 时必填，不允许无理由降级）。"""


_CONSUMER_USAGES: ConcurrentStableDict[str, ConcurrentStableFrozenList[CapabilityUsage]] = ConcurrentStableDict()
"""消费方使用登记（`{消费方标识: 声明列表}`；应用级视图，装配期登记一次）。"""


def register_capability_usages(consumer: str, usages: Iterable[CapabilityUsage]) -> None:
    """登记消费方使用声明（幂等：同消费方同值覆盖、异值即拒）。

    Args:
        consumer: 消费方标识（服务键 / 产品键）。
        usages: 使用声明（插入序）。

    Raises:
        CatalogError: 消费方未知或与已登记声明同键异值（fail-closed，不静默取一侧）。
        ParamError: 消费方标识为空。
    """
    if not consumer:
        raise CatalogError("能力使用登记缺少消费方标识（consumer 不得为空）")
    declared = ConcurrentStableFrozenList(usages)
    existing = _CONSUMER_USAGES.get(consumer)
    if existing is not None and existing.to_list() != declared.to_list():
        raise CatalogError(
            f"能力使用登记冲突：{consumer!r}（已登记 {[item.name for item in existing]}，"
            f"新 {[item.name for item in declared]}）"
        )
    _CONSUMER_USAGES.set(consumer, declared)


def reset_capability_usages() -> None:
    """清空已登记的使用声明（测试隔离用；生产路径不调用）。"""
    _CONSUMER_USAGES.clear()


def capability_usage_view() -> ConcurrentStableDict[str, ConcurrentStableFrozenList[CapabilityUsage]]:
    """使用登记视图（消费方 → 声明列表）。

    Returns:
        ConcurrentStableDict[str, ConcurrentStableFrozenList[CapabilityUsage]]: 只读视图（插入序）。
    """
    return ConcurrentStableDict(ConcurrentStableList(_CONSUMER_USAGES.to_list()))


def capability_usages(consumer: str) -> ConcurrentStableFrozenList[CapabilityUsage]:
    """取消费方的使用声明（未登记返回空清单）。

    Args:
        consumer: 消费方标识。

    Returns:
        ConcurrentStableFrozenList[CapabilityUsage]: 使用声明（插入序）。
    """
    return _CONSUMER_USAGES.get(consumer) or ConcurrentStableFrozenList()


def find_capability_usage(consumer: str, name: str) -> CapabilityUsage | None:
    """按消费方与能力名取使用声明。

    Args:
        consumer: 消费方标识。
        name: 能力名。

    Returns:
        CapabilityUsage | None: 使用声明；未登记该能力返回 None。
    """
    for usage in capability_usages(consumer):
        if usage.name == name:
            return usage
    return None


def inspect_capability_usages(consumer: str, usages: Iterable[CapabilityUsage]) -> ConcurrentStableList[str]:
    """校验使用声明（不抛错；装配期与用例共用）。

    Args:
        consumer: 消费方标识。
        usages: 使用声明。

    Returns:
        ConcurrentStableList[str]: 错误明细（空表示通过）。
    """
    errors: ConcurrentStableList[str] = ConcurrentStableList()
    records = ConcurrentStableDict({record.name: record for record in collaboration_catalog_view()})
    seen: ConcurrentStableDict[str, CapabilityUsage] = ConcurrentStableDict()
    for usage in usages:
        prefix = f"{consumer}｜能力 {usage.name}"
        if usage.degrade not in DEGRADE_MODES:
            errors.add(f"{prefix}：降级模式非法（{usage.degrade}；取值 {'/'.join(DEGRADE_MODES)}）")
        if usage.degrade != DEGRADE_NONE and not usage.reason.strip():
            errors.add(f"{prefix}：声明降级须给出理由（reason 不得为空）")
        if usage.degrade == DEGRADE_STALE:
            errors.add(f"{prefix}：降级模式暂不支持（stale 需本地投影来源，当前未落地）")
        if usage.name in seen:
            errors.add(f"{prefix}：使用声明重复（同一消费方不得重复声明同一能力）")
        seen.set(usage.name, usage)
        record = records.get(usage.name)
        if record is None:
            errors.add(f"{prefix}：声明了未登记的能力（请检查产品清单拼写与装载）")
            continue
        if record.status == CollaborationStatus.DISABLED:
            errors.add(f"{prefix}：声明了已禁用的能力（status=disabled）")
        if usage.degrade != DEGRADE_NONE and record.kind in WRITE_KINDS:
            errors.add(f"{prefix}：写 / 强一致能力不得声明降级（kind={record.kind}，该档失败即整体失败）")
    return errors


def validate_capability_usages(consumer: str, usages: Iterable[CapabilityUsage]) -> None:
    """校验使用声明（失败即拒启）。

    Args:
        consumer: 消费方标识。
        usages: 使用声明。

    Raises:
        CatalogError: 任一声明不满足（信息定位到能力名）。
    """
    errors = inspect_capability_usages(consumer, usages)
    if errors:
        raise CatalogError("能力使用登记校验失败：" + "；".join(errors))


async def call_capability[ResultT](
    name: str,
    *,
    consumer: str,
    metrics: BaseMetrics | None,
    call: Callable[[CapabilityEndpoint], Awaitable[ResultT]],
    fallback: Callable[[], ResultT],
) -> ResultT:
    """按能力名调用，并按消费方声明决定失败处置（读 / 弱一致路径的统一入口）。

    行为：

    - 能力取用失败（未声明 / 已禁用 / 业务域未登记）→ 计 `capability_resolve_error_total` 并**上抛**
      （契约断链不可降级）；
    - 调用失败且**未声明降级** → 原样上抛；
    - 调用失败且声明了降级 → 计 `capability_degrade_total`、输出 `WARNING` 结构化日志、返回兜底值。

    Args:
        name: 能力名。
        consumer: 消费方标识（使用登记的键）。
        metrics: 指标器（None 表示不记录，测试 / 无指标环境）。
        call: 业务调用（入参为取用结果，返回值原样返回）。
        fallback: 兜底值构造（仅在声明降级时调用，返回空集或旧副本）。

    Returns:
        ResultT: 业务调用结果，或按声明降级后的兜底值。

    Raises:
        ParamError: 能力名为空、未声明或已禁用（10001）。
        CatalogError: 业务域未在部署拓扑登记（配置缺失）。
        Exception: 调用失败且未声明降级时原样上抛。
    """
    try:
        endpoint = resolve_capability(name)
    except Exception:
        await _count(metrics, METRIC_CAPABILITY_RESOLVE_ERROR, {"capability": name, "consumer": consumer})
        raise
    try:
        return await call(endpoint)
    except Exception as exc:
        usage = find_capability_usage(consumer, name)
        if usage is None or usage.degrade == DEGRADE_NONE:
            raise
        await _count(
            metrics,
            METRIC_CAPABILITY_DEGRADE,
            {"capability": name, "consumer": consumer, "mode": usage.degrade},
        )
        get_logger(_LOGGER).warning(
            "capability_degrade",
            capability=name,
            consumer=consumer,
            degrade_mode=usage.degrade,
            reason=usage.reason,
            target_service=endpoint.target.service_key,
            error_code=getattr(exc, "code", None),
            error_type=type(exc).__name__,
        )
        return fallback()


async def _count(metrics: BaseMetrics | None, name: str, labels: MetricLabels) -> None:
    """记录一次计数（指标器缺省时跳过）。

    Args:
        metrics: 指标器（可为 None）。
        name: 指标名。
        labels: 标签集。
    """
    if metrics is None:
        return
    await metrics.counter(name, labels=labels)
