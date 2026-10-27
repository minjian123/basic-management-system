"""三档失败语义：降级声明 / 装载期校验 / 统一执行入口（07B `02_02`；Kiwi 编号归 `05_01`）。

覆盖详细设计 §5 用例 6~12：写路径不得声明降级（fail-closed）、读路径按声明有界降级（含日志与指标）、
未声明降级即上抛、声明无理由 / 未登记能力 / `stale` 无投影来源 / 重复声明 / 已禁用能力均装载期报错。
"""

import re
from collections.abc import Iterator

import pytest

from bms_core.collaboration import (
    DEGRADE_EMPTY,
    DEGRADE_NONE,
    DEGRADE_STALE,
    METRIC_CAPABILITY_DEGRADE,
    METRIC_CAPABILITY_RESOLVE_ERROR,
    CapabilityEndpoint,
    CapabilityUsage,
    call_capability,
    capability_usage_view,
    capability_usages,
    find_capability_usage,
    inspect_capability_usages,
    register_capability_usages,
    reset_capability_usages,
    validate_capability_usages,
)
from bms_core.collaboration import usage as usage_module
from bms_core.core.concurrent import (
    ConcurrentStableFrozenDict,
    ConcurrentStableFrozenList,
    ConcurrentStableList,
)
from bms_core.core.exceptions import CatalogError, ParamError, ServiceUnavailableError
from bms_core.metrics.base import BaseMetrics, MetricLabels
from bms_core.services.module_registry import (
    CollaborationRecord,
    CollaborationStatus,
    register_collaboration_records,
    register_domain_services,
    reset_collaboration_records,
    reset_domain_services,
)


class RecordingMetrics(BaseMetrics):
    """记录计数器调用（断言指标名与标签）。"""

    def __init__(self) -> None:
        """初始化计数器记录表。"""
        self.counters: ConcurrentStableList[tuple[str, MetricLabels | None]] = ConcurrentStableList()

    async def counter(self, name: str, *, value: float = 1.0, labels: MetricLabels | None = None) -> None:
        """记录计数器。

        Args:
            name: 指标名。
            value: 增量（未断言，保持契约形参）。
            labels: 标签集。
        """
        del value
        self.counters.add((name, labels))

    async def gauge(self, name: str, *, value: float, labels: MetricLabels | None = None) -> None:
        """未使用的瞬时值入口（保持契约完整）。"""
        del name, value, labels

    async def histogram(self, name: str, *, value: float, labels: MetricLabels | None = None) -> None:
        """未使用的直方图入口（保持契约完整）。"""
        del name, value, labels


class RecordingLogger:
    """记录结构化日志事件与字段的假日志门面。"""

    def __init__(self) -> None:
        """初始化事件记录表。"""
        self.events: ConcurrentStableList[tuple[str, ConcurrentStableFrozenDict[str, object]]] = ConcurrentStableList()

    def warning(self, event: str, **fields: object) -> None:
        """记录 WARNING 事件。

        Args:
            event: 事件名。
            **fields: 结构化字段。
        """
        self.events.add((event, ConcurrentStableFrozenDict(fields)))


def _read_record(
    *, name: str = "demo.org.user-roles", status: str = CollaborationStatus.ENABLED
) -> CollaborationRecord:
    """构造读类能力记录。

    Args:
        name: 能力名。
        status: 能力状态。

    Returns:
        CollaborationRecord: 能力记录。
    """
    return CollaborationRecord(
        name=name,
        domain="org",
        kind="read",
        contract_version="0.1.0",
        path="/api/v1/demo/user-roles",
        product_key="demo",
        frontend_prefix="demo",
        status=status,
    )


def _write_record(*, name: str = "demo.org.user-posts.assign") -> CollaborationRecord:
    """构造事务分支（写 / 强一致）能力记录。

    Args:
        name: 能力名。

    Returns:
        CollaborationRecord: 能力记录。
    """
    return CollaborationRecord(
        name=name,
        domain="org",
        kind="txn-branch",
        contract_version="0.1.0",
        path="/api/v1/demo/internal/user-posts/{user_id}",
        product_key="demo",
        branch_id="d",
        branch_op="demo.user-posts.assign",
        frontend_prefix="demo",
    )


@pytest.fixture(autouse=True)
def _isolate_state() -> Iterator[None]:
    """每例前后复位能力记录、使用声明与域→服务键映射（均为进程级状态）。

    Yields:
        None: 用例运行期。
    """
    reset_collaboration_records()
    reset_capability_usages()
    reset_domain_services()
    register_domain_services(ConcurrentStableFrozenDict({"org": "mdm"}))
    register_collaboration_records((_read_record(), _write_record()))
    yield
    reset_collaboration_records()
    reset_capability_usages()
    reset_domain_services()


def test_usage_registry_register_view_find_and_reset() -> None:
    """使用声明登记：幂等、视图只读副本、按名查找、复位清空。"""
    declaration = CapabilityUsage(
        name="demo.org.user-roles", degrade=DEGRADE_EMPTY, reason="组织角色链缺失按无角色处理"
    )

    register_capability_usages("platform", (declaration,))
    register_capability_usages("platform", (declaration,))

    assert capability_usages("platform") == [declaration]
    assert capability_usage_view()["platform"] == [declaration]
    assert find_capability_usage("platform", "demo.org.user-roles") == declaration
    assert find_capability_usage("platform", "demo.org.other") is None
    assert capability_usages("identity") == []

    reset_capability_usages()
    assert capability_usage_view() == {}


def test_usage_registry_rejects_conflict_and_blank_consumer() -> None:
    """登记通道纪律：同消费方异值即拒、消费方标识为空即拒。"""
    register_capability_usages("platform", (CapabilityUsage(name="demo.org.user-roles"),))

    with pytest.raises(CatalogError, match="能力使用登记冲突：'platform'"):
        register_capability_usages(
            "platform",
            (CapabilityUsage(name="demo.org.user-roles", degrade=DEGRADE_EMPTY, reason="理由"),),
        )

    with pytest.raises(CatalogError, match="缺少消费方标识"):
        register_capability_usages("", ())


def test_valid_declaration_passes_validation() -> None:
    """合规声明（读能力 + 有理由的 `empty` 降级）通过校验。"""
    usages = (
        CapabilityUsage(name="demo.org.user-roles", degrade=DEGRADE_EMPTY, reason="断链时按无岗位角色处理"),
        CapabilityUsage(name="demo.org.user-posts.assign"),
    )

    assert inspect_capability_usages("platform", usages) == []
    validate_capability_usages("platform", usages)


def test_inspection_reports_each_violation() -> None:
    """装载期校验反例：模式非法 / 无理由 / `stale` / 重复 / 未登记 / 已禁用 / 写能力降级（用例 10~12）。"""
    register_collaboration_records((_read_record(name="demo.org.dept-data", status=CollaborationStatus.DISABLED),))
    usages = (
        CapabilityUsage(name="demo.org.user-roles", degrade="degrade-me"),
        CapabilityUsage(name="demo.org.user-roles", degrade=DEGRADE_EMPTY),
        CapabilityUsage(name="demo.org.user-roles", degrade=DEGRADE_STALE, reason="旧副本"),
        CapabilityUsage(name="demo.org.unknown"),
        CapabilityUsage(name="demo.org.dept-data"),
        CapabilityUsage(name="demo.org.user-posts.assign", degrade=DEGRADE_EMPTY, reason="写路径不该降级"),
    )

    errors = inspect_capability_usages("platform", usages)

    joined = "；".join(errors)
    assert "降级模式非法（degrade-me；取值 none/empty/stale）" in joined
    assert "声明降级须给出理由" in joined
    assert "降级模式暂不支持（stale 需本地投影来源，当前未落地）" in joined
    assert "使用声明重复" in joined
    assert "声明了未登记的能力" in joined
    assert "声明了已禁用的能力（status=disabled）" in joined
    assert "写 / 强一致能力不得声明降级（kind=txn-branch，" in joined


def test_validation_raises_catalog_error() -> None:
    """校验失败即 `CatalogError`（装配期据此拒启），信息定位到能力名。"""
    with pytest.raises(CatalogError, match=re.escape("能力使用登记校验失败：platform｜能力 demo.org.unknown")):
        validate_capability_usages("platform", (CapabilityUsage(name="demo.org.unknown"),))


async def test_call_capability_returns_call_result() -> None:
    """取用成功：原样返回业务调用结果，不产生降级指标。"""
    metrics = RecordingMetrics()

    async def _call(endpoint: CapabilityEndpoint) -> str:
        """读取访问面路径。

        Args:
            endpoint: 取用结果。

        Returns:
            str: 访问面路径。
        """
        return endpoint.access_url()

    result = await call_capability(
        "demo.org.user-roles",
        consumer="platform",
        metrics=metrics,
        call=_call,
        fallback=lambda: "fallback",
    )

    assert result == "http://mdm:8000/api/v1/demo/user-roles"
    assert metrics.counters == []


async def test_call_capability_degrades_only_when_declared(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """声明 `empty` 且调用失败 → 返回兜底值 + 一条结构化 WARNING + 降级指标计数（用例 7）。"""
    register_capability_usages(
        "platform",
        (CapabilityUsage(name="demo.org.user-roles", degrade=DEGRADE_EMPTY, reason="断链时按无角色处理"),),
    )
    metrics = RecordingMetrics()
    logger = RecordingLogger()
    monkeypatch.setattr(usage_module, "get_logger", lambda _name="bms": logger)

    async def _boom(endpoint: object) -> ConcurrentStableList[str]:
        """恒抛下游不可用（模拟提供方不可达）。

        Args:
            endpoint: 取用结果（未使用）。

        Returns:
            ConcurrentStableList[str]: 不会返回。

        Raises:
            ServiceUnavailableError: 恒定抛出。
        """
        del endpoint
        raise ServiceUnavailableError("下游不可达")

    result = await call_capability(
        "demo.org.user-roles",
        consumer="platform",
        metrics=metrics,
        call=_boom,
        fallback=ConcurrentStableList,
    )

    assert result == []
    assert metrics.counters == [
        (
            METRIC_CAPABILITY_DEGRADE,
            {"capability": "demo.org.user-roles", "consumer": "platform", "mode": DEGRADE_EMPTY},
        )
    ]
    assert len(logger.events) == 1
    event, fields = logger.events[0]
    assert event == "capability_degrade"
    assert fields["capability"] == "demo.org.user-roles"
    assert fields["consumer"] == "platform"
    assert fields["degrade_mode"] == DEGRADE_EMPTY
    assert fields["reason"] == "断链时按无角色处理"
    assert fields["target_service"] == "mdm"
    assert fields["error_code"] == 10007
    assert fields["error_type"] == "ServiceUnavailableError"


async def test_call_capability_raises_when_undeclared() -> None:
    """未声明降级的读路径失败 → 原样上抛，不产生降级指标（用例 8）。"""
    metrics = RecordingMetrics()

    async def _boom(endpoint: object) -> None:
        """恒抛下游不可用。

        Args:
            endpoint: 取用结果（未使用）。

        Raises:
            ServiceUnavailableError: 恒定抛出。
        """
        del endpoint
        raise ServiceUnavailableError("下游不可达")

    with pytest.raises(ServiceUnavailableError, match="下游不可达"):
        await call_capability(
            "demo.org.user-roles",
            consumer="platform",
            metrics=metrics,
            call=_boom,
            fallback=ConcurrentStableList,
        )

    assert metrics.counters == []


async def test_call_capability_raises_when_declared_none() -> None:
    """声明 `degrade=none`（显式不降级）同样上抛。"""
    register_capability_usages("platform", (CapabilityUsage(name="demo.org.user-roles", degrade=DEGRADE_NONE),))

    async def _boom(endpoint: object) -> None:
        """恒抛下游不可用。

        Args:
            endpoint: 取用结果（未使用）。

        Raises:
            ServiceUnavailableError: 恒定抛出。
        """
        del endpoint
        raise ServiceUnavailableError("下游不可达")

    with pytest.raises(ServiceUnavailableError):
        await call_capability(
            "demo.org.user-roles",
            consumer="platform",
            metrics=RecordingMetrics(),
            call=_boom,
            fallback=ConcurrentStableList,
        )


async def test_call_capability_counts_resolve_error_and_raises() -> None:
    """能力取用失败（契约断链）→ 计 `capability_resolve_error_total` 并上抛，不可降级。"""
    metrics = RecordingMetrics()

    async def _unused(endpoint: object) -> None:
        """不会被调用（取用阶段已失败）。

        Args:
            endpoint: 取用结果（未使用）。
        """
        del endpoint

    with pytest.raises(ParamError, match=re.escape("能力未声明：demo.org.missing")):
        await call_capability(
            "demo.org.missing",
            consumer="platform",
            metrics=metrics,
            call=_unused,
            fallback=ConcurrentStableList,
        )

    assert metrics.counters == [
        (METRIC_CAPABILITY_RESOLVE_ERROR, {"capability": "demo.org.missing", "consumer": "platform"})
    ]


async def test_call_capability_without_metrics_still_degrades() -> None:
    """无指标器（测试 / 无监控环境）：降级仍生效（指标缺省跳过，日志照常）。"""
    register_capability_usages(
        "platform",
        (CapabilityUsage(name="demo.org.user-roles", degrade=DEGRADE_EMPTY, reason="断链时按无角色处理"),),
    )

    async def _boom(endpoint: object) -> None:
        """恒抛下游不可用。

        Args:
            endpoint: 取用结果（未使用）。

        Raises:
            ServiceUnavailableError: 恒定抛出。
        """
        del endpoint
        raise ServiceUnavailableError("下游不可达")

    result = await call_capability(
        "demo.org.user-roles",
        consumer="platform",
        metrics=None,
        call=_boom,
        fallback=lambda: ConcurrentStableFrozenList(("stale",)),
    )

    assert result == ["stale"]
