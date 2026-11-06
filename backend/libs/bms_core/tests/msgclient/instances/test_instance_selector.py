"""04-6 用例之一（Kiwi 2444）：实例选择、在途计数、摘除与半开恢复。

全部时间相关断言走 fake clock：摘除 TTL、半开探测、恢复不依赖真实等待。
"""

from __future__ import annotations

import pytest
from msgclient_support.rpc_retry import FakeClock
from structlog.testing import capture_logs

from bms_core.core.concurrent import (
    ConcurrentStableDict,
    ConcurrentStableFrozenList,
    ConcurrentStableList,
)
from bms_core.msgclient.instances import (
    InstanceLease,
    InstanceOutcome,
    InstancePolicy,
    InstanceProvider,
    InstanceSelector,
    InstanceSnapshot,
    InstanceStrategy,
    InstanceUnavailable,
    StaticInstanceSelector,
)

pytestmark = pytest.mark.kiwi_id(2444)

A = "http://a:8000"
"""实例 A。"""

B = "http://b:8000"
"""实例 B。"""

POOL = "static"
"""`StaticInstanceSelector` 的缺省池标识。"""


class _FixedProvider:
    """按给定快照作答的来源替身（用于 revision / 空快照用例）。"""

    def __init__(self, snapshot: InstanceSnapshot) -> None:
        """初始化。

        Args:
            snapshot: 固定快照。
        """
        self.snapshot = snapshot

    def resolve(self, service: str) -> InstanceSnapshot:
        """返回固定快照。

        Args:
            service: 逻辑服务标识（未使用）。

        Returns:
            InstanceSnapshot: 固定快照。
        """
        del service
        return self.snapshot


def _selector(*endpoints: str, **policy: object) -> tuple[InstanceSelector, FakeClock]:
    """构造注入 fake clock 的静态选择器。

    Args:
        *endpoints: 实例地址。
        **policy: 覆盖的 `InstancePolicy` 字段。

    Returns:
        tuple: 选择器与时钟。
    """
    clock = FakeClock()
    selector = StaticInstanceSelector(list(endpoints), policy=InstancePolicy(**policy), clock=clock)  # type: ignore[arg-type]
    return selector, clock


def _healthy(selector: InstanceSelector, origin: str) -> bool:
    """读池快照判断某实例是否健康。

    Args:
        selector: 选择器。
        origin: 实例基址。

    Returns:
        bool: 健康为 True。
    """
    view = selector.snapshot(POOL)
    return any(entry.origin == origin and not entry.evicted for entry in view.entries)


# ---------------------------------------------------------------------------
# 1. 选择策略
# ---------------------------------------------------------------------------


def test_round_robin_order_is_deterministic() -> None:
    """轮询按插入序：a → b → a → b。"""
    selector, _ = _selector(A, B)
    seen: ConcurrentStableList[str] = ConcurrentStableList()
    for _ in range(4):
        lease = selector.acquire("demo")
        seen.append(lease.origin)
        selector.release(lease, InstanceOutcome.SUCCESS)
    assert list(seen) == [A, B, A, B]


def test_single_instance_degrades_to_direct() -> None:
    """单实例：两种策略都只返回同一地址。"""
    selector, _ = _selector(A)
    for _ in range(3):
        lease = selector.acquire("demo")
        assert lease.origin == A
        selector.release(lease, InstanceOutcome.SUCCESS)


def test_least_inflight_prefers_lower_count() -> None:
    """最少在途：先选空载实例，平局按游标顺序。"""
    selector, _ = _selector(A, B, strategy=InstanceStrategy.LEAST_INFLIGHT)
    first = selector.acquire("demo")
    second = selector.acquire("demo")
    assert (first.origin, second.origin) == (A, B)
    third = selector.acquire("demo")
    assert third.origin == A  # 两者都在途 1，游标在 b 之后回到 a
    for lease in (first, second, third):
        selector.release(lease, InstanceOutcome.SUCCESS)


def test_exclude_prefers_other_instance() -> None:
    """排除刚失败实例：下一跳优先选另一个健康实例。"""
    selector, _ = _selector(A, B)
    lease = selector.acquire("demo", exclude={A})
    assert lease.origin == B
    selector.release(lease, InstanceOutcome.SUCCESS)


def test_exclude_falls_back_to_single_healthy_instance() -> None:
    """单实例被排除时允许回退（不能「失败一次就再也打不到」）。"""
    selector, _ = _selector(A)
    lease = selector.acquire("demo", exclude={A})
    assert lease.origin == A
    selector.release(lease, InstanceOutcome.SUCCESS)


def test_preferred_returns_to_original_instance() -> None:
    """结果未知时回到原实例，而不是换一个实例重放。"""
    selector, _ = _selector(A, B)
    lease = selector.acquire("demo", preferred=B)
    assert lease.origin == B
    selector.release(lease, InstanceOutcome.SUCCESS)


def test_preferred_unavailable_raises() -> None:
    """原实例已摘除时不再换其他实例，直接报不可用。"""
    selector, _ = _selector(A, B, failure_threshold=1)
    lease = selector.acquire("demo", preferred=A)
    selector.release(lease, InstanceOutcome.FAILURE)
    with pytest.raises(InstanceUnavailable, match="preferred_unavailable"):
        selector.acquire("demo", preferred=A)


# ---------------------------------------------------------------------------
# 2. 摘除与恢复
# ---------------------------------------------------------------------------


def test_evicts_after_threshold_and_recovers_from_half_open() -> None:
    """连续失败达到阈值摘除；TTL 到期放一个探测，成功即恢复。"""
    selector, clock = _selector(A, failure_threshold=2)
    first = selector.acquire("demo")
    selector.release(first, InstanceOutcome.FAILURE)
    second = selector.acquire("demo")
    selector.release(second, InstanceOutcome.FAILURE)
    assert not _healthy(selector, A)

    with pytest.raises(InstanceUnavailable, match="all_evicted"):
        selector.acquire("demo")

    clock.advance(30_000)
    probe = selector.acquire("demo")
    assert probe.probe is True
    selector.release(probe, InstanceOutcome.SUCCESS)
    assert _healthy(selector, A)


def test_probe_failure_re_evicts() -> None:
    """探测失败续摘，并重新计时 TTL。"""
    selector, clock = _selector(A, failure_threshold=1)
    lease = selector.acquire("demo")
    selector.release(lease, InstanceOutcome.FAILURE)
    clock.advance(30_000)
    probe = selector.acquire("demo")
    assert probe.probe is True
    selector.release(probe, InstanceOutcome.FAILURE)
    assert not _healthy(selector, A)
    with pytest.raises(InstanceUnavailable, match="all_evicted"):
        selector.acquire("demo")


def test_probe_neutral_re_evicts() -> None:
    """探测拿到中性结果（协议错）不恢复，按续摘处理。"""
    selector, clock = _selector(A, failure_threshold=1)
    lease = selector.acquire("demo")
    selector.release(lease, InstanceOutcome.FAILURE)
    clock.advance(30_000)
    probe = selector.acquire("demo")
    selector.release(probe, InstanceOutcome.NEUTRAL)
    assert not _healthy(selector, A)


def test_neutral_does_not_count_as_failure() -> None:
    """中性结果不增加连续失败计数，实例保持健康。"""
    selector, _ = _selector(A, failure_threshold=1)
    for _ in range(3):
        lease = selector.acquire("demo")
        selector.release(lease, InstanceOutcome.NEUTRAL)
    assert _healthy(selector, A)


def test_all_evicted_and_probe_in_flight_is_unavailable() -> None:
    """摘除到期但唯一探测仍在途：并发请求快速失败（不绕过半开限制）。"""
    selector, clock = _selector(A, failure_threshold=1)
    lease = selector.acquire("demo")
    selector.release(lease, InstanceOutcome.FAILURE)
    clock.advance(30_000)
    probe = selector.acquire("demo")
    with pytest.raises(InstanceUnavailable, match="probe_in_flight"):
        selector.acquire("demo")
    selector.release(probe, InstanceOutcome.SUCCESS)


def test_preferred_evicted_is_unavailable() -> None:
    """原实例被摘除后 preferred 不可用，不偷偷换实例。"""
    selector, _ = _selector(A, B, failure_threshold=1)
    lease = selector.acquire("demo", preferred=A)
    selector.release(lease, InstanceOutcome.FAILURE)
    with pytest.raises(InstanceUnavailable, match="preferred_unavailable"):
        selector.acquire("demo", preferred=A)


# ---------------------------------------------------------------------------
# 3. 快照与 revision
# ---------------------------------------------------------------------------


def test_empty_snapshot_is_unavailable() -> None:
    """来源没有地址：直接不可用（不静默回退写死地址）。"""
    provider: InstanceProvider = _FixedProvider(
        InstanceSnapshot(pool_key="p", addresses=ConcurrentStableFrozenList(), revision=0, fetched_at_ms=0)
    )
    selector = InstanceSelector(provider, clock=FakeClock())
    with pytest.raises(InstanceUnavailable, match="empty_snapshot"):
        selector.acquire("demo")


def test_revision_change_prunes_removed_instance() -> None:
    """列表变更按 revision 清理消失的 origin 状态。"""
    provider = _FixedProvider(
        InstanceSnapshot(pool_key="p", addresses=ConcurrentStableFrozenList([A, B]), revision=1, fetched_at_ms=0)
    )
    selector = InstanceSelector(provider, clock=FakeClock())
    lease_a = selector.acquire("demo")
    lease_b = selector.acquire("demo")
    assert {lease_a.origin, lease_b.origin} == {A, B}
    selector.release(lease_a, InstanceOutcome.FAILURE)
    selector.release(lease_b, InstanceOutcome.SUCCESS)

    provider.snapshot = InstanceSnapshot(
        pool_key="p", addresses=ConcurrentStableFrozenList([A]), revision=2, fetched_at_ms=0
    )
    lease = selector.acquire("demo", preferred=A)
    view = selector.snapshot("p")
    assert [entry.origin for entry in view.entries] == [A]
    assert view.revision == 2
    selector.release(lease, InstanceOutcome.SUCCESS)


def test_inflight_counts_are_visible() -> None:
    """acquire / release 正确维护在途计数（流式长租约同样适用）。"""
    selector, _ = _selector(A)
    lease = selector.acquire("demo")
    assert selector.snapshot(POOL).entries[0].inflight == 1
    selector.report(lease, InstanceOutcome.SUCCESS)
    assert selector.snapshot(POOL).entries[0].inflight == 1
    selector.release(lease)
    assert selector.snapshot(POOL).entries[0].inflight == 0


# ---------------------------------------------------------------------------
# 4. 观测
# ---------------------------------------------------------------------------


def test_logs_selected_removed_recovered_unavailable() -> None:
    """四个实例事件都按结构化字段输出。"""
    selector, clock = _selector(A, failure_threshold=1)
    with capture_logs() as logs:
        lease = selector.acquire("demo")
        selector.release(lease, InstanceOutcome.FAILURE)
        with pytest.raises(InstanceUnavailable):
            selector.acquire("demo")
        clock.advance(30_000)
        probe = selector.acquire("demo")
        selector.release(probe, InstanceOutcome.SUCCESS)

    events = [entry["event"] for entry in logs]
    assert "msg_rpc_instance_selected" in events
    assert "msg_rpc_instance_removed" in events
    assert "msg_rpc_instance_unavailable" in events
    assert "msg_rpc_instance_recovered" in events
    removed = next(entry for entry in logs if entry["event"] == "msg_rpc_instance_removed")
    assert removed["pool_key"] == POOL
    assert removed["origin"] == A
    assert removed["reason"] == "failure_threshold"


# ---------------------------------------------------------------------------
# 5. 参数校验与防御分支
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"failure_threshold": 0}, "failure_threshold"),
        ({"evict_ttl_ms": -1}, "evict_ttl_ms"),
        ({"snapshot_ttl_ms": -1}, "snapshot_ttl_ms"),
        ({"half_open_max_probes": 0}, "half_open_max_probes"),
    ],
)
def test_policy_rejects_invalid_values(kwargs: ConcurrentStableDict[str, int], message: str) -> None:
    """策略参数越界在构造期拒绝（不让 0 次摘除 / 负 TTL 进入运行期）。"""
    with pytest.raises(ValueError, match=message):
        InstancePolicy(**kwargs)  # type: ignore[arg-type]


def test_snapshot_unknown_pool_returns_empty_view() -> None:
    """未知池返回空视图（排障 / 用例读快照不炸）。"""
    selector, _ = _selector(A)
    view = selector.snapshot("missing")
    assert view.revision == 0
    assert len(view.entries) == 0
    assert view.stale is False


def test_release_unknown_lease_is_noop() -> None:
    """已不在池里的租约释放不抛（列表变更后的收尾路径）。"""
    selector, _ = _selector(A)
    lease = InstanceLease(pool_key="missing", origin=A, revision=0)
    selector.report(lease, InstanceOutcome.SUCCESS)
    selector.release(lease, InstanceOutcome.FAILURE)
