"""RPC 实例来源与选择（任务 04-6）：快照、租约、策略、在途计数、摘除与半开恢复。

**为什么把「来源」与「选择」拆开**：来源只回答「有哪些实例」（配置 / DNS / 服务目录），选择器
只回答「选哪个、失败怎么摘、何时恢复」。两者分开后，换来源（静态列表 → 服务目录 → DNS）不改
选择策略；换策略（轮询 → 最少在途）不改来源实现。

**实例是 msg 平台节点**：RPC 请求发往 `/rpc/{service}/{method}`，`service` 是 msg 注册表里的逻辑
路由键，不是「被调服务实例」。因此池按 `pool_key`（首期为 `msg`）维护，失败计数按
`(pool_key, origin)` 独立于 04-4 的依赖熔断。

**不 import `rpc.py`**：本模块只依赖值对象、常量与 `Clock`；`InstanceUnavailable` 是内部异常，
由 RPC 层映射成 `InstanceUnavailableError(RpcCallError)`。这样 `rpc.py → instances.py` 单向依赖，
不会因「实例不可用要继承 RpcCallError」形成环。

**同步 `acquire` / `report` / `release`**：来源是进程内配置（未来是 DNS 缓存），选择本身是纯内存
操作；不引入额外 `await`。未来 DNS 刷新由 provider 内部维护快照，`resolve()` 仍同步返回最近值。
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum
from typing import NoReturn, Protocol

from bms_core.core.concurrent import (
    ConcurrentStableDict,
    ConcurrentStableFrozenList,
    ConcurrentStableList,
    ConcurrentStableSet,
)
from bms_core.core.logging import get_logger
from bms_core.core.roots import BaseValueObject
from bms_core.msgclient.constants import (
    RPC_INSTANCE_EVICT_TTL_MS,
    RPC_INSTANCE_FAILURE_THRESHOLD,
    RPC_INSTANCE_HALF_OPEN_MAX_PROBES,
    RPC_INSTANCE_SNAPSHOT_TTL_MS,
)
from bms_core.msgclient.retry import Clock, SystemClock

__all__ = [
    "InstanceEntryView",
    "InstanceLease",
    "InstanceOutcome",
    "InstancePolicy",
    "InstancePoolView",
    "InstanceProvider",
    "InstanceSelector",
    "InstanceSnapshot",
    "InstanceStrategy",
    "InstanceUnavailable",
    "StaticInstanceProvider",
    "StaticInstanceSelector",
    "selector_for",
]

_LOGGER = get_logger("bms_core.msgclient")
"""与 04-4 / 04-7-2 同一日志族：`msg_rpc_instance_*` 由 06-3 按事件名前缀分流。"""


class InstanceStrategy(StrEnum):
    """实例选择策略。"""

    ROUND_ROBIN = "round_robin"
    """插入序轮询：确定性、易断言，缺省。"""

    LEAST_INFLIGHT = "least_inflight"
    """最少在途：并发下更均匀；平局按轮询游标顺序。"""


class InstanceOutcome(StrEnum):
    """一次调用结束后反馈给实例健康的状态。"""

    SUCCESS = "success"
    """收到响应（含错误帧 / 4xx / 5xx）：实例可达。"""

    FAILURE = "failure"
    """传输失败 / 本地超时：实例不可达或不可用。"""

    NEUTRAL = "neutral"
    """协议错（帧不可解析 / 版本不符）：不归咎实例，不计数。"""


@dataclass(frozen=True)
class InstanceSnapshot(BaseValueObject):
    """一次实例来源解析结果（值对象；选择器按 `revision` 清理旧状态）。"""

    pool_key: str
    """池标识（首期 `msg`）：同一池的实例共享游标、在途计数与健康状态。"""

    addresses: ConcurrentStableFrozenList[str]
    """实例基址（`scheme://host:port`，无尾斜线、去重、插入序）。"""

    revision: int
    """快照版本：地址元组变化时递增；选择器据此清理消失的 origin。"""

    fetched_at_ms: int
    """解析时刻（毫秒；provider 注入时钟，用例可断言 TTL）。"""

    stale: bool = False
    """是否为过期快照（首期恒 False；DNS / 远程目录接入后用于诊断）。"""


@dataclass(frozen=True)
class InstanceLease(BaseValueObject):
    """一次调用占用的实例（在途计数 +1；`release` 时 -1）。"""

    pool_key: str
    """池标识。"""

    origin: str
    """实例基址。"""

    revision: int
    """租约所属快照版本：列表已变化时 `release` 不再影响新池状态。"""

    probe: bool = False
    """是否为半开探测请求（只放一个；失败续摘、成功恢复）。"""


@dataclass(frozen=True)
class InstancePolicy(BaseValueObject):
    """实例选择与摘除参数（构造注入；缺省值写 `constants.py`）。"""

    strategy: InstanceStrategy = InstanceStrategy.ROUND_ROBIN
    """选择策略。"""

    failure_threshold: int = RPC_INSTANCE_FAILURE_THRESHOLD
    """连续失败达到该次数即摘除。"""

    evict_ttl_ms: int = RPC_INSTANCE_EVICT_TTL_MS
    """摘除时长（毫秒）：到点转半开。"""

    snapshot_ttl_ms: int = RPC_INSTANCE_SNAPSHOT_TTL_MS
    """快照缓存时长（毫秒）：provider 用；选择器只做校验透传。"""

    half_open_max_probes: int = RPC_INSTANCE_HALF_OPEN_MAX_PROBES
    """半开期最大在途探测数。"""

    def __post_init__(self) -> None:
        """校验参数（装配期即拒，避免运行期出现 0 次摘除 / 负数 TTL）。

        Raises:
            ValueError: 任一参数越界。
        """
        if self.failure_threshold < 1:
            raise ValueError(f"failure_threshold 须 >= 1：{self.failure_threshold}")
        if self.evict_ttl_ms < 0:
            raise ValueError(f"evict_ttl_ms 须 >= 0：{self.evict_ttl_ms}")
        if self.snapshot_ttl_ms < 0:
            raise ValueError(f"snapshot_ttl_ms 须 >= 0：{self.snapshot_ttl_ms}")
        if self.half_open_max_probes < 1:
            raise ValueError(f"half_open_max_probes 须 >= 1：{self.half_open_max_probes}")


@dataclass(frozen=True)
class InstanceEntryView(BaseValueObject):
    """池内单个实例的可断言快照。"""

    origin: str
    """实例基址。"""

    failures: int
    """连续失败次数。"""

    evicted: bool
    """是否处于摘除态。"""

    evicted_at_ms: int | None
    """摘除起始时刻（健康态为 None）。"""

    probes: int
    """当前半开探测在途数。"""

    inflight: int
    """当前在途调用数。"""


@dataclass(frozen=True)
class InstancePoolView(BaseValueObject):
    """整个池的可断言快照（用例与排障用）。"""

    pool_key: str
    """池标识。"""

    revision: int
    """当前快照版本。"""

    entries: ConcurrentStableFrozenList[InstanceEntryView]
    """实例条目（插入序）。"""

    stale: bool
    """当前快照是否过期。"""


class InstanceUnavailable(Exception):
    """来源为空 / 全部摘除 / 探测在途（内部异常，由 RPC 层映射为 `InstanceUnavailableError`）。"""

    def __init__(self, message: str, *, pool_key: str | None = None, reason: str = "") -> None:
        """初始化。

        Args:
            message: 可读提示。
            pool_key: 池标识（可空）。
            reason: 机器可读原因（`empty_snapshot` / `all_evicted` / `probe_in_flight` / ...）。
        """
        super().__init__(message)
        self.pool_key = pool_key
        self.reason = reason


class InstanceProvider(Protocol):
    """实例来源：只回答「有哪些实例」，不关心选择策略与健康状态。"""

    def resolve(self, service: str) -> InstanceSnapshot:
        """解析目标服务对应的实例快照。

        Args:
            service: 逻辑服务标识（首期只用于日志与未来多池映射）。

        Returns:
            InstanceSnapshot: 实例快照。

        Raises:
            InstanceUnavailable: 来源为空或解析失败。
        """
        ...


class StaticInstanceProvider:
    """静态地址列表来源（单地址即单元素列表）。

    `revision` 恒 0、`fetched_at_ms` 恒 0：静态列表不会变化，选择器不需要清理状态。地址去尾斜线、
    按插入序去重；空列表构造期即拒绝（与 04-1 的「至少一个实例」口径一致）。
    """

    def __init__(self, endpoints: Iterable[str], *, pool_key: str = "static") -> None:
        """初始化。

        Args:
            endpoints: 实例基址列表（至少一个）。
            pool_key: 池标识（同池共享选择状态；单地址客户端可用默认值）。

        Raises:
            ValueError: 列表为空。
        """
        addresses = ConcurrentStableFrozenList(dict.fromkeys(endpoint.rstrip("/") for endpoint in endpoints))
        if not addresses:
            raise ValueError("InstanceProvider 至少需要一个实例地址")
        self._snapshot = InstanceSnapshot(pool_key=pool_key, addresses=addresses, revision=0, fetched_at_ms=0)

    def resolve(self, service: str) -> InstanceSnapshot:
        """返回构造时的静态快照。

        Args:
            service: 逻辑服务标识（未使用）。

        Returns:
            InstanceSnapshot: 静态快照。
        """
        del service
        return self._snapshot


@dataclass
class _InstanceState:
    """单个实例的可变健康 / 在途状态。"""

    failures: int = 0
    evicted_at_ms: int | None = None
    probes: int = 0
    inflight: int = 0


@dataclass
class _Pool:
    """单个池的可变状态。"""

    key: str
    revision: int
    addresses: ConcurrentStableFrozenList[str]
    states: ConcurrentStableDict[str, _InstanceState]
    cursor: int = 0
    stale: bool = False


class InstanceSelector:
    """实例选择器：策略 + 健康 + 在途计数（同步；不碰 IO）。"""

    def __init__(
        self,
        provider: InstanceProvider,
        *,
        policy: InstancePolicy | None = None,
        clock: Clock | None = None,
    ) -> None:
        """初始化。

        Args:
            provider: 实例来源。
            policy: 选择 / 摘除参数（缺省 `InstancePolicy()`）。
            clock: 时钟（缺省 `SystemClock()`；用例注入 fake clock）。
        """
        self._provider = provider
        self._policy = policy if policy is not None else InstancePolicy()
        self._clock = clock if clock is not None else SystemClock()
        self._pools: ConcurrentStableDict[str, _Pool] = ConcurrentStableDict()

    # ------------------------------------------------------------------ 对外入口

    def acquire(
        self,
        service: str,
        *,
        exclude: Iterable[str] = (),
        preferred: str | None = None,
    ) -> InstanceLease:
        """选一个实例并返回租约（在途 +1）。

        **选择顺序**：`preferred`（结果未知时回原实例）→ 健康 / 半开候选 → `exclude` 回退。
        `exclude` 覆盖全部健康实例时允许回退到被排除但健康的实例（单实例场景不能直接判死）。

        Args:
            service: 逻辑服务标识。
            exclude: 本次调用中已失败的 origin（优先跳过）。
            preferred: 指定 origin（存在且健康时直选；不可用即不可用，不换其他实例）。

        Returns:
            InstanceLease: 实例租约。

        Raises:
            InstanceUnavailable: 来源为空 / 全部摘除 / 探测在途 / preferred 不可用。
        """
        snapshot = self._provider.resolve(service)
        pool = self._sync(snapshot)
        if not pool.addresses:
            self._raise_unavailable(pool.key, service, "empty_snapshot", pool.addresses)
        now = self._clock.now_ms()

        if preferred is not None:
            state = pool.states.get(preferred)
            if state is None or state.evicted_at_ms is not None:
                self._raise_unavailable(pool.key, service, "preferred_unavailable", pool.addresses)
            return self._take(pool, service, preferred, state, probe=False)

        excluded = ConcurrentStableSet(exclude)
        selectable = ConcurrentStableList(
            origin for origin in pool.addresses if self._is_selectable(pool, origin, excluded, now)
        )
        if not selectable:
            # 单实例 / 全被排除：回退到被排除但健康的实例，避免「刚失败一次就再也打不到」。
            selectable = ConcurrentStableList(
                origin for origin in pool.addresses if origin in excluded and self._is_healthy(pool, origin)
            )
            if not selectable:
                reason = "probe_in_flight" if self._probe_in_flight(pool, now) else "all_evicted"
                self._raise_unavailable(pool.key, service, reason, pool.addresses)

        origin = self._pick(pool, selectable)
        state = pool.states[origin]
        return self._take(pool, service, origin, state, probe=state.evicted_at_ms is not None)

    def report(self, lease: InstanceLease, outcome: InstanceOutcome) -> None:
        """只更新健康状态（不减在途；流式打开阶段用）。

        Args:
            lease: 实例租约。
            outcome: 本次结果。
        """
        state = self._state_of(lease)
        if state is None:
            return
        now = self._clock.now_ms()
        if outcome is InstanceOutcome.SUCCESS:
            recovered = state.evicted_at_ms is not None
            state.failures = 0
            state.probes = max(0, state.probes - 1)
            if recovered:
                state.evicted_at_ms = None
                _LOGGER.info(
                    "msg_rpc_instance_recovered",
                    pool_key=lease.pool_key,
                    origin=lease.origin,
                    reason="probe_success",
                )
            return
        if outcome is InstanceOutcome.NEUTRAL:
            state.probes = max(0, state.probes - 1)
            if lease.probe or state.evicted_at_ms is not None:
                state.evicted_at_ms = now
                self._log_removed(lease, "probe_neutral")
            return
        # FAILURE
        state.probes = max(0, state.probes - 1)
        if state.evicted_at_ms is not None:
            state.evicted_at_ms = now
            self._log_removed(lease, "probe_failure")
            return
        state.failures += 1
        if state.failures >= self._policy.failure_threshold:
            state.evicted_at_ms = now
            self._log_removed(lease, "failure_threshold")

    def release(self, lease: InstanceLease, outcome: InstanceOutcome | None = None) -> None:
        """释放在途配额（幂等）；给了 `outcome` 时同时更新健康状态。

        Args:
            lease: 实例租约。
            outcome: 本次结果（None 表示只减在途，如流正常结束 / `aclose`）。
        """
        state = self._state_of(lease)
        if state is not None:
            state.inflight = max(0, state.inflight - 1)
        if outcome is not None:
            self.report(lease, outcome)

    def snapshot(self, pool_key: str) -> InstancePoolView:
        """取池快照（用例断言 / 排障）。

        Args:
            pool_key: 池标识。

        Returns:
            InstancePoolView: 池状态；未知池返回空视图。
        """
        pool = self._pools.get(pool_key)
        if pool is None:
            return InstancePoolView(
                pool_key=pool_key,
                revision=0,
                entries=ConcurrentStableFrozenList(),
                stale=False,
            )
        entries = ConcurrentStableFrozenList(
            InstanceEntryView(
                origin=origin,
                failures=state.failures,
                evicted=state.evicted_at_ms is not None,
                evicted_at_ms=state.evicted_at_ms,
                probes=state.probes,
                inflight=state.inflight,
            )
            for origin, state in pool.states.items()
        )
        return InstancePoolView(pool_key=pool_key, revision=pool.revision, entries=entries, stale=pool.stale)

    # ------------------------------------------------------------------ 内部

    def _sync(self, snapshot: InstanceSnapshot) -> _Pool:
        """按快照同步池状态（revision 变化时清理消失的 origin）。

        Args:
            snapshot: 来源快照。

        Returns:
            _Pool: 同步后的池。
        """
        pool = self._pools.get(snapshot.pool_key)
        if pool is None:
            pool = _Pool(
                key=snapshot.pool_key,
                revision=snapshot.revision,
                addresses=snapshot.addresses,
                states=ConcurrentStableDict((address, _InstanceState()) for address in snapshot.addresses),
            )
            self._pools[snapshot.pool_key] = pool
            return pool
        if pool.revision != snapshot.revision:
            pool.states = ConcurrentStableDict(
                (address, pool.states.get(address, _InstanceState())) for address in snapshot.addresses
            )
            pool.addresses = snapshot.addresses
            pool.revision = snapshot.revision
            pool.cursor = pool.cursor % len(pool.addresses) if pool.addresses else 0
        pool.stale = snapshot.stale
        return pool

    def _is_healthy(self, pool: _Pool, origin: str) -> bool:
        """实例是否健康（未摘除）。

        Args:
            pool: 池。
            origin: 实例基址。

        Returns:
            bool: 健康为 True。
        """
        state = pool.states.get(origin)
        return state is not None and state.evicted_at_ms is None

    def _is_selectable(self, pool: _Pool, origin: str, excluded: ConcurrentStableSet[str], now_ms: int) -> bool:
        """实例本刻是否可选（健康，或摘除 TTL 到期且探测名额可用）。

        Args:
            pool: 池。
            origin: 实例基址。
            excluded: 本次调用已失败的 origin。
            now_ms: 当前毫秒。

        Returns:
            bool: 可选为 True。
        """
        if origin in excluded:
            return False
        state = pool.states.get(origin)
        if state is None:  # pragma: no cover - 池状态与地址表同步后不可达
            return False
        if state.evicted_at_ms is None:
            return True
        return (
            now_ms - state.evicted_at_ms >= self._policy.evict_ttl_ms
            and state.probes < self._policy.half_open_max_probes
        )

    def _probe_in_flight(self, pool: _Pool, now_ms: int) -> bool:
        """是否存在「已到期但探测名额已满」的实例（用于不可用原因区分）。

        Args:
            pool: 池。
            now_ms: 当前毫秒。

        Returns:
            bool: 存在为 True。
        """
        return any(
            state.evicted_at_ms is not None
            and now_ms - state.evicted_at_ms >= self._policy.evict_ttl_ms
            and state.probes >= self._policy.half_open_max_probes
            for state in pool.states.values()
        )

    def _pick(self, pool: _Pool, selectable: Iterable[str]) -> str:
        """按策略从候选里选一个（并推进游标）。

        Args:
            pool: 池。
            selectable: 候选 origin（插入序）。

        Returns:
            str: 选中的 origin。
        """
        if self._policy.strategy is InstanceStrategy.LEAST_INFLIGHT:
            origin = min(
                selectable,
                key=lambda item: (pool.states[item].inflight, pool.addresses.index(item)),
            )
        else:
            start = pool.cursor % len(pool.addresses)
            ordered = pool.addresses[start:] + pool.addresses[:start]
            origin = next(item for item in ordered if item in selectable)
        pool.cursor = (pool.addresses.index(origin) + 1) % len(pool.addresses)
        return origin

    def _take(
        self,
        pool: _Pool,
        service: str,
        origin: str,
        state: _InstanceState,
        *,
        probe: bool,
    ) -> InstanceLease:
        """占用一个实例（在途 +1、探测名额 +1）并记选择事件。

        Args:
            pool: 池。
            service: 逻辑服务标识。
            origin: 实例基址。
            state: 实例状态。
            probe: 是否半开探测。

        Returns:
            InstanceLease: 租约。
        """
        state.inflight += 1
        if probe:
            state.probes += 1
        _LOGGER.info(
            "msg_rpc_instance_selected",
            pool_key=pool.key,
            service=service,
            origin=origin,
            strategy=self._policy.strategy.value,
            probe=probe,
            inflight=state.inflight,
        )
        return InstanceLease(
            pool_key=pool.key,
            origin=origin,
            revision=pool.revision,
            probe=probe,
        )

    def _state_of(self, lease: InstanceLease) -> _InstanceState | None:
        """按租约取实例状态（列表已变化 / 池已删则 None）。

        Args:
            lease: 实例租约。

        Returns:
            _InstanceState | None: 实例状态。
        """
        pool = self._pools.get(lease.pool_key)
        if pool is None:
            return None
        return pool.states.get(lease.origin)

    def _log_removed(self, lease: InstanceLease, reason: str) -> None:
        """记一条摘除事件。

        Args:
            lease: 实例租约。
            reason: `failure_threshold` / `probe_failure` / `probe_neutral`。
        """
        state = self._state_of(lease)
        _LOGGER.info(
            "msg_rpc_instance_removed",
            pool_key=lease.pool_key,
            origin=lease.origin,
            reason=reason,
            failures=0 if state is None else state.failures,
            evict_ttl_ms=self._policy.evict_ttl_ms,
        )

    def _raise_unavailable(
        self,
        pool_key: str,
        service: str,
        reason: str,
        addresses: Iterable[str],
    ) -> NoReturn:
        """记一条不可用事件并抛出内部异常。

        Args:
            pool_key: 池标识。
            service: 逻辑服务标识。
            reason: 机器可读原因。
            addresses: 当前地址列表。

        Raises:
            InstanceUnavailable: 恒抛。
        """
        _LOGGER.info(
            "msg_rpc_instance_unavailable",
            pool_key=pool_key,
            service=service,
            reason=reason,
            addresses=tuple(addresses),
        )
        raise InstanceUnavailable(
            f"无可用 RPC 实例（pool={pool_key}, reason={reason}）",
            pool_key=pool_key,
            reason=reason,
        )


class StaticInstanceSelector(InstanceSelector):
    """静态列表的便捷选择器（`InstanceSelector(StaticInstanceProvider(...))` 的语法糖）。"""

    def __init__(
        self,
        endpoints: Iterable[str],
        *,
        policy: InstancePolicy | None = None,
        clock: Clock | None = None,
    ) -> None:
        """初始化。

        Args:
            endpoints: 实例基址列表（至少一个）。
            policy: 选择 / 摘除参数。
            clock: 时钟。
        """
        super().__init__(StaticInstanceProvider(endpoints), policy=policy, clock=clock)


def selector_for(
    provider: InstanceProvider,
    *,
    policy: InstancePolicy | None = None,
    clock: Clock | None = None,
) -> InstanceSelector:
    """构造选择器（调用点迁移的便捷工厂）。

    Args:
        provider: 实例来源。
        policy: 选择 / 摘除参数。
        clock: 时钟。

    Returns:
        InstanceSelector: 选择器。
    """
    return InstanceSelector(provider, policy=policy, clock=clock)
