"""跨产品能力分配与授权（07B `02_04`）：授权记录、声明差异、三类派生与授权视图。

- `CapabilityGrant`：一条授权记录的值对象（能力 × 消费方；来源 `declared` / `manual`）；
- `declare_capability_grants()` / `plan_grant_sync()`：把产品声明的 `default_consumers` 与库中现状
  做**纯函数**差异计算（无 IO、无进程级状态），落库由 platform 服务执行；
- `granted_scopes(consumer)`：出站授权派生（`svc:{业务域}:read|write`；`codes` 不产生 scope）；
- `check_capability_access(capability, consumer, ...)`：入站判定（允许 / 未授权 / 已过期）+ 指标打点；
- 授权视图：`register_capability_grant_source()` 登记来源，`ensure_grant_view()` 按 TTL 惰性重拉，
  `capability_grant_pairs()` 同步读快照（出站 scope 用）；`RemoteCapabilityGrantSource` 为跨进程
  提供方 / 消费方实现（产品侧注册与预热归 `03_01`）。

口径（详见任务 `02_04` 详细设计）：**声明是基线、人工是覆盖**；**有有效分配即合法**（直连或经平台
中转均可），**无分配即越界**；撤销不删行、有界生效（不承诺跨实例强一致）。
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from datetime import UTC, datetime, timedelta
from typing import Protocol, cast

from bms_core.collaboration.base import WRITE_KINDS
from bms_core.core.concurrent import (
    ConcurrentStableDict,
    ConcurrentStableFrozenDict,
    ConcurrentStableFrozenList,
    ConcurrentStableList,
)
from bms_core.core.exceptions import CatalogError, PermissionError
from bms_core.core.logging import get_logger
from bms_core.core.objects import BaseFrameworkObject, BaseValueObject
from bms_core.metrics.base import BaseMetrics
from bms_core.models.platform.capability_grant import (
    GRANT_NOTE_DECLARED,
    GRANT_NOTE_REMOVED,
    GRANT_SOURCE_DECLARED,
    GRANT_SOURCE_MANUAL,
    GRANT_STATUS_DISABLED,
    GRANT_STATUS_ENABLED,
)
from bms_core.servicecall.base import BaseServiceClient, ServiceRequest
from bms_core.services.module_registry import (
    CollaborationKind,
    CollaborationStatus,
    collaboration_catalog_view,
)

__all__ = [
    "CALL_RESULT_ALLOWED",
    "CALL_RESULT_DENIED",
    "CALL_RESULT_EXPIRED",
    "GRANT_VIEW_PATH",
    "GRANT_VIEW_TTL_SECONDS",
    "METRIC_CAPABILITY_CALL",
    "METRIC_CAPABILITY_DENIED",
    "METRIC_CAPABILITY_GRANT_ACTIVE",
    "SCOPE_PREFIX",
    "CapabilityGrant",
    "CapabilityGrantSource",
    "GrantSyncPlan",
    "GrantViewSnapshot",
    "capability_grant_pairs",
    "check_capability_access",
    "declare_capability_grants",
    "ensure_grant_view",
    "grant_view_key",
    "granted_consumers",
    "granted_scopes",
    "invalidate_capability_grants",
    "is_grant_effective",
    "plan_grant_sync",
    "prime_grant_views",
    "record_capability_call",
    "register_capability_grant_source",
    "reset_capability_grants",
    "scope_action_of",
    "warm_grant_views",
]

SCOPE_PREFIX = "svc"
"""服务令牌 scope 的段首（`svc:{业务域}:{read|write}`）——与开放接口 `{产品键}:{动作}` 彻底分区。"""

GRANT_VIEW_TTL_SECONDS = 60.0
"""授权视图快照有效期（秒）：撤销 / 授予在 TTL 内有界生效，不承诺跨实例强一致。"""

GRANT_VIEW_PATH = "/api/v1/platform/internal/capability-grants"
"""授权视图内部出口路径（平台内部面，`require_auth_or_service` 双模鉴权）。

**必须与平台真实路由一致**（`services/platform/.../api/internal_capability_grants.py` 的
`prefix="/platform/internal/capability-grants"` + 统一挂载前缀 `/api/v1`）：路径写错时拉取只会
404 → 产品进程长期停留在「降级 + 首次访问 fail-closed」，很难在运行期发现。防漂断言见
`services/platform/tests/api/test_capability_grants.py`。
"""

CALL_RESULT_ALLOWED = "allowed"
"""调用结果：有有效分配（放行）。"""

CALL_RESULT_DENIED = "denied"
"""调用结果：无有效分配（越界拒绝）。"""

CALL_RESULT_EXPIRED = "expired"
"""调用结果：存在授权记录但已过有效期（按未授权拒绝并标注）。"""

METRIC_CAPABILITY_CALL = "bms_capability_call_total"
"""能力调用计数（`{capability, consumer, result}`；覆盖调用量 / 失败率 / 越权）。"""

METRIC_CAPABILITY_DENIED = "bms_capability_denied_total"
"""越权尝试计数（`{capability, consumer}`；与调用计数并存，便于单独告警）。"""

METRIC_CAPABILITY_GRANT_ACTIVE = "bms_capability_grant_active"
"""有效授权数（gauge，`{capability}`；授予 / 撤销 / 声明同步后刷新）。"""

_LOGGER = "bms_core.collaboration.grant"
"""日志通道名。"""

_SCOPE_READ_KINDS = (CollaborationKind.READ, CollaborationKind.DATASET)
"""派生只读 scope 的访问面类别。"""


@dataclass(frozen=True)
class CapabilityGrant(BaseValueObject):
    """一条授权记录（能力 × 消费方；值对象，消费方只读）。"""

    capability_name: str
    """能力名（须已在能力视图中登记）。"""

    consumer_key: str
    """消费方标识（服务键或产品键；前端应用不参与分配）。"""

    source: str = GRANT_SOURCE_DECLARED
    """来源（`declared` 产品声明装载 / `manual` 人工授予）。"""

    status: str = GRANT_STATUS_ENABLED
    """状态（`enabled` / `disabled`）。"""

    expire_at: datetime | None = None
    """有效期截止（UTC；None 表示长期有效）。"""

    note: str = ""
    """说明 / 授予理由（声明装载写默认说明；临时授权必填）。"""


def is_grant_effective(grant: CapabilityGrant, *, now: datetime | None = None) -> bool:
    """授权是否有效（`status=enabled` 且未过期）。

    Args:
        grant: 授权记录。
        now: 判定基准时刻（缺省取当前 UTC）。

    Returns:
        bool: 有效为 True。
    """
    if grant.status != GRANT_STATUS_ENABLED:
        return False
    return grant.expire_at is None or grant.expire_at > (now or datetime.now(UTC))


def scope_action_of(kind: str) -> str | None:
    """访问面类别 → scope 动作段（`codes` 无访问面，不产生 scope）。

    Args:
        kind: 访问面类别（`CollaborationKind` 取值）。

    Returns:
        str | None: `read` / `write`；`codes` 返回 None。
    """
    if kind in _SCOPE_READ_KINDS:
        return "read"
    if kind in WRITE_KINDS:
        return "write"
    return None


def declare_capability_grants() -> ConcurrentStableList[CapabilityGrant]:
    """取产品声明产生的默认授权（`collaborations[].default_consumers`）。

    Returns:
        ConcurrentStableList[CapabilityGrant]: 声明基线（`source=declared` / `status=enabled`，插入序）。
    """
    declared: ConcurrentStableList[CapabilityGrant] = ConcurrentStableList()
    for record in collaboration_catalog_view():
        for consumer in record.default_consumers:
            declared.add(
                CapabilityGrant(
                    capability_name=record.name,
                    consumer_key=consumer,
                    source=GRANT_SOURCE_DECLARED,
                    status=GRANT_STATUS_ENABLED,
                    note=GRANT_NOTE_DECLARED,
                )
            )
    return declared


@dataclass(frozen=True)
class GrantSyncPlan(BaseValueObject):
    """声明装载的差异计划（纯函数产物，由 platform 服务落库）。"""

    creates: ConcurrentStableFrozenList[CapabilityGrant]
    """需新建的声明记录。"""

    restores: ConcurrentStableFrozenList[CapabilityGrant]
    """需恢复为有效的声明记录（曾因声明移除被禁用）。"""

    revokes: ConcurrentStableFrozenList[CapabilityGrant]
    """需置为撤销的声明记录（声明已移除消费方）。"""

    warnings: ConcurrentStableFrozenList[str]
    """装载报告警示（声明与人工不一致等；不静默择一）。"""


def plan_grant_sync(
    declared: Iterable[CapabilityGrant],
    current: Iterable[CapabilityGrant],
    *,
    now: datetime | None = None,
) -> GrantSyncPlan:
    """计算声明基线与库中现状的差异（纯函数：无 IO、无进程级状态）。

    Args:
        declared: 声明基线（`declare_capability_grants()` 产物）。
        current: 库中现状（未软删的授权记录）。
        now: 判定基准时刻（缺省取当前 UTC；仅用于恢复记录的时间戳）。

    Returns:
        GrantSyncPlan: 差异计划（新建 / 恢复 / 撤销 / 警示）。
    """
    moment = now or datetime.now(UTC)
    existing: ConcurrentStableDict[tuple[str, str], CapabilityGrant] = ConcurrentStableDict()
    for grant in current:
        existing.set((grant.capability_name, grant.consumer_key), grant)
    creates: ConcurrentStableList[CapabilityGrant] = ConcurrentStableList()
    restores: ConcurrentStableList[CapabilityGrant] = ConcurrentStableList()
    revokes: ConcurrentStableList[CapabilityGrant] = ConcurrentStableList()
    warnings: ConcurrentStableList[str] = ConcurrentStableList()
    desired: ConcurrentStableDict[tuple[str, str], CapabilityGrant] = ConcurrentStableDict()
    for grant in declared:
        key = (grant.capability_name, grant.consumer_key)
        if key in desired:
            continue
        desired.set(key, grant)
        found = existing.get(key)
        if found is None:
            creates.add(grant)
            continue
        if found.source == GRANT_SOURCE_MANUAL:
            if not is_grant_effective(found, now=moment):
                warnings.add(
                    f"声明与人工不一致：能力 {grant.capability_name} 消费方 {grant.consumer_key}"
                    "（人工撤销优先，声明装载不重新打开）"
                )
            continue
        if found.status == GRANT_STATUS_ENABLED:
            continue
        restores.add(
            CapabilityGrant(
                capability_name=found.capability_name,
                consumer_key=found.consumer_key,
                source=GRANT_SOURCE_DECLARED,
                status=GRANT_STATUS_ENABLED,
                expire_at=found.expire_at,
                note=GRANT_NOTE_DECLARED,
            )
        )
    for grant in current:
        key = (grant.capability_name, grant.consumer_key)
        if key in desired:
            continue
        if grant.source != GRANT_SOURCE_DECLARED or grant.status != GRANT_STATUS_ENABLED:
            continue
        revokes.add(
            CapabilityGrant(
                capability_name=grant.capability_name,
                consumer_key=grant.consumer_key,
                source=GRANT_SOURCE_DECLARED,
                status=GRANT_STATUS_DISABLED,
                expire_at=grant.expire_at,
                note=GRANT_NOTE_REMOVED,
            )
        )
    return GrantSyncPlan(
        creates=ConcurrentStableFrozenList(creates),
        restores=ConcurrentStableFrozenList(restores),
        revokes=ConcurrentStableFrozenList(revokes),
        warnings=ConcurrentStableFrozenList(warnings),
    )


@dataclass(frozen=True)
class GrantViewSnapshot(BaseValueObject):
    """授权视图快照（某一维度的授权记录投影 + 加载时刻）。"""

    key: str
    """视图键（`provider:{业务域}` / `consumer:{服务键}`）。"""

    loaded_at: datetime
    """快照加载时刻（UTC；TTL 判定基准）。"""

    grants: ConcurrentStableFrozenList[CapabilityGrant] = dataclass_field(
        default_factory=lambda: ConcurrentStableFrozenList[CapabilityGrant]()
    )
    """该维度的授权记录（`status=enabled`，**含已过期行**——是否过期由调用方本地判定）。"""


class CapabilityGrantSource(Protocol):
    """授权视图来源协议（platform 为「本库直读」，产品服务为「内部出口拉取」）。"""

    async def load(
        self, *, provider: str | None = None, consumer: str | None = None
    ) -> ConcurrentStableList[CapabilityGrant]:
        """按维度加载授权记录。

        Args:
            provider: 提供方业务域（入站维度）。
            consumer: 消费方服务键（出站维度）。

        Returns:
            ConcurrentStableList[CapabilityGrant]: 该维度的授权记录（`status=enabled`）。

        Raises:
            CatalogError: 来源不可用（启动期拒启级；运行期按旧快照兜底）。
        """
        ...

    async def load_all(
        self, *, providers: ConcurrentStableList[str], consumer: str | None = None
    ) -> ConcurrentStableDict[str, ConcurrentStableList[CapabilityGrant]]:
        """一次加载多个维度的授权记录（启动预热专用，避免逐维取门 / 逐维往返）。

        **返回按维度分组**：键是 `grant_view_key(provider=…)` / `grant_view_key(consumer=…)`，值与该维度
        `load()` 的返回**逐条一致**（同一口径：入站维只含该业务域能力的启用记录，出站维只含该消费方的）。
        分组由实现方完成——本库直读实现一次查询后在进程内按能力目录切分，远端实现逐维拉取天然分组。

        Args:
            providers: 需预热的提供方业务域清单。
            consumer: 需预热的消费方服务键（None 表示不预热该维）。

        Returns:
            ConcurrentStableDict[str, ConcurrentStableList[CapabilityGrant]]: 视图键 → 该维度授权记录。

        Raises:
            CatalogError: 来源不可用（启动期拒启级）。
        """
        ...


class RemoteCapabilityGrantSource(BaseFrameworkObject):
    """跨进程实现：经 platform 内部出口拉取授权视图（`GET /api/v1/internal/capability-grants`）。

    产品服务在装配期登记本来源（`03_01` / 产品仓接线）；平台服务用「本库直读」来源，不走 HTTP。
    """

    def __init__(self, client: BaseServiceClient, *, service: str = "platform") -> None:
        """初始化远端来源。

        Args:
            client: 服务间调用客户端（`BaseServiceClient` 实现；鸭子类型，避免反向依赖）。
            service: 承载授权权威的服务标识（缺省 `platform`）。
        """
        self._client = client
        self._service = service

    async def load(
        self, *, provider: str | None = None, consumer: str | None = None
    ) -> ConcurrentStableList[CapabilityGrant]:
        """按维度拉取授权记录（失败抛 `CatalogError`，由 `ensure_grant_view` 决定拒启或兜底）。

        Args:
            provider: 提供方业务域。
            consumer: 消费方服务键。

        Returns:
            ConcurrentStableList[CapabilityGrant]: 该维度的授权记录。

        Raises:
            CatalogError: 出口不可达或响应非法。
        """
        query = ConcurrentStableFrozenDict(
            {"provider": provider} if provider is not None else {"consumer": consumer or ""}
        )
        response = await self._client.call(
            ServiceRequest(service=self._service, method="GET", path=GRANT_VIEW_PATH, query=query)
        )
        if response.status_code != 200:
            raise CatalogError(f"授权视图出口不可达（HTTP {response.status_code}）：{self._service}")
        payload = response.payload()
        if not isinstance(payload, dict):
            raise CatalogError("授权视图出口响应非法（非 JSON 对象）")
        root = cast("ConcurrentStableDict[str, object]", payload)
        raw_data = root.get("data")
        if not isinstance(raw_data, dict):
            raise CatalogError("授权视图出口响应非法（缺少 data 对象）")
        raw_rows = cast("ConcurrentStableDict[str, object]", raw_data).get("grants")
        if not isinstance(raw_rows, list):
            raise CatalogError("授权视图出口响应非法（缺少 grants 数组）")
        grants: ConcurrentStableList[CapabilityGrant] = ConcurrentStableList()
        for raw_row in cast("ConcurrentStableList[object]", raw_rows):
            if not isinstance(raw_row, dict):
                raise CatalogError("授权视图出口响应非法（grants 元素非对象）")
            row = cast("ConcurrentStableDict[str, object]", raw_row)
            grants.add(
                CapabilityGrant(
                    capability_name=str(row.get("capability_name", "")),
                    consumer_key=str(row.get("consumer_key", "")),
                    expire_at=_parse_expire_at(row.get("expire_at")),
                )
            )
        return grants

    async def load_all(
        self, *, providers: ConcurrentStableList[str], consumer: str | None = None
    ) -> ConcurrentStableDict[str, ConcurrentStableList[CapabilityGrant]]:
        """按维度逐项拉取后分组返回（启动预热专用）。

        **为什么逐项而不是一次拉全量**：产品进程走 HTTP，不涉及本地 SQLite 写门——多几次往返
        只是毫秒级网络成本；反之一旦给内部出口加「不传维度即全量」的口径，出口权限面会从
        「按维度读」放大成「可拉全库授权」，收益与代价不成比例。

        Args:
            providers: 需预热的提供方业务域清单。
            consumer: 需预热的消费方服务键（None 表示不预热该维）。

        Returns:
            ConcurrentStableDict[str, ConcurrentStableList[CapabilityGrant]]: 视图键 → 该维度授权记录。

        Raises:
            CatalogError: 任一维度拉取失败（出口不可达 / 响应非法）。
        """
        views: ConcurrentStableDict[str, ConcurrentStableList[CapabilityGrant]] = ConcurrentStableDict()
        for provider in providers:
            views.set(grant_view_key(provider=provider), await self.load(provider=provider))
        if consumer is not None:
            views.set(grant_view_key(consumer=consumer), await self.load(consumer=consumer))
        return views


def _parse_expire_at(raw: object) -> datetime | None:
    """解析授权有效期（ISO 8601；缺失 / 非法视为长期有效并告警）。

    Args:
        raw: 出口返回的有效期原值（字符串或 None）。

    Returns:
        datetime | None: UTC 感知时间；长期有效为 None。
    """
    if raw is None or raw == "":
        return None
    try:
        parsed = datetime.fromisoformat(str(raw))
    except ValueError:
        get_logger(_LOGGER).warning("capability_grant_expire_at_invalid", detail=str(raw))
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


_SOURCE_HOLDER: ConcurrentStableDict[str, CapabilityGrantSource] = ConcurrentStableDict()
"""已登记的授权视图来源（单键 `active`；空表示未装配——挂了 `require_capability` 的端点按未授权处理）。"""

_SOURCE_KEY = "active"
"""来源持有键（单值语义；用集合类承载进程级可变状态，避免模块级 `global` 断言）。"""

_SNAPSHOTS: ConcurrentStableDict[str, GrantViewSnapshot] = ConcurrentStableDict()
"""授权视图快照（键为 `provider:{域}` / `consumer:{服务键}`）。"""


def register_capability_grant_source(source: CapabilityGrantSource) -> None:
    """登记授权视图来源（重复登记以后者为准；测试隔离用 `reset_capability_grants` 复位）。

    Args:
        source: 实现 `CapabilityGrantSource` 协议的对象。
    """
    _SOURCE_HOLDER.set(_SOURCE_KEY, source)


def reset_capability_grants() -> None:
    """清空来源与快照（测试隔离用；生产路径不调用）。"""
    _SOURCE_HOLDER.clear()
    _SNAPSHOTS.clear()


def invalidate_capability_grants(*, provider: str | None = None, consumer: str | None = None) -> None:
    """使某维度快照失效（授予 / 撤销后调用，令变更有界即时生效）。

    Args:
        provider: 提供方业务域（None 表示不限）。
        consumer: 消费方服务键（None 表示不限）。
    """
    keys: ConcurrentStableList[str] = ConcurrentStableList()
    if provider is not None:
        keys.add(grant_view_key(provider=provider))
    if consumer is not None:
        keys.add(grant_view_key(consumer=consumer))
    if not keys:
        _SNAPSHOTS.clear()
        return
    for key in keys:
        if _SNAPSHOTS.get(key) is not None:
            _SNAPSHOTS.delete(key)


async def ensure_grant_view(
    *,
    provider: str | None = None,
    consumer: str | None = None,
    ttl: float = GRANT_VIEW_TTL_SECONDS,
    now: datetime | None = None,
) -> GrantViewSnapshot:
    """确保授权视图快照可用（缺失或超 TTL 即重拉；刷新失败保留旧快照）。

    Args:
        provider: 提供方业务域（入站维度）。
        consumer: 消费方服务键（出站维度）。
        ttl: 快照有效期（秒）。
        now: 判定基准时刻（缺省取当前 UTC）。

    Returns:
        GrantViewSnapshot: 该维度的快照（可能为旧快照）。

    Raises:
        CatalogError: 来源未登记，或首次加载失败且无旧快照（启动 / 首访即断链，fail-closed）。
    """
    key = grant_view_key(provider=provider, consumer=consumer)
    moment = now or datetime.now(UTC)
    cached = _SNAPSHOTS.get(key)
    if cached is not None and moment - cached.loaded_at < timedelta(seconds=ttl):
        return cached
    source = _SOURCE_HOLDER.get(_SOURCE_KEY)
    if source is None:
        raise CatalogError("授权视图来源未登记（请检查应用装配是否调用 register_capability_grant_source）")
    try:
        grants = await source.load(provider=provider, consumer=consumer)
    except Exception as exc:
        if cached is not None:
            get_logger(_LOGGER).warning(
                "capability_grant_refresh_failed",
                view=key,
                error=type(exc).__name__,
                detail=str(exc),
            )
            return cached
        raise
    snapshot = GrantViewSnapshot(
        key=key,
        loaded_at=moment,
        grants=ConcurrentStableFrozenList(grants),
    )
    _SNAPSHOTS.set(key, snapshot)
    return snapshot


def prime_grant_views(
    views: ConcurrentStableDict[str, ConcurrentStableList[CapabilityGrant]],
    *,
    now: datetime | None = None,
) -> None:
    """用一次批量加载的结果填充多个维度的快照（启动预热；与逐维 `ensure_grant_view` 同构）。

    分组口径由来源实现负责（`load_all` 的返回值就是「视图键 → 该维度记录」），本函数只做投影，
    因此平台直读与远端拉取两条来源填出来的快照逐条一致。

    Args:
        views: 视图键 → 该维度授权记录（键须由 `grant_view_key` 构造）。
        now: 快照加载时刻（缺省取当前 UTC）。
    """
    moment = now or datetime.now(UTC)
    for key in views:
        grants = views.get(key)
        _SNAPSHOTS.set(
            key,
            GrantViewSnapshot(
                key=key,
                loaded_at=moment,
                grants=ConcurrentStableFrozenList() if grants is None else ConcurrentStableFrozenList(grants),
            ),
        )


async def warm_grant_views(
    *,
    providers: ConcurrentStableList[str],
    consumer: str | None = None,
    ttl: float = GRANT_VIEW_TTL_SECONDS,
    now: datetime | None = None,
) -> None:
    """一次装载并填充多个维度的授权视图（启动预热入口）。

    与 `ensure_grant_view` 的关系：那个是运行期「按需单维度惰性刷新」，本函数是启动期「一次装载
    全部承载维度」——同一份快照结构、同一套维度口径，只是把 N 次取门压成 1 次。

    **已新鲜的维度不重拉**：启动链路上同一个维度可能被前后两步都要求预热，跳过 TTL 内的旧快照
    既省一次往返，也让「先只预热承载域、再连消费方一起预热」的组合不产生重复请求。

    Args:
        providers: 需预热的提供方业务域清单。
        consumer: 需预热的消费方服务键（None 表示不预热该维）。
        ttl: 快照有效期（秒）。
        now: 判定基准时刻（缺省取当前 UTC）。

    Raises:
        CatalogError: 来源未登记或加载失败（由调用方决定拒启或降级）。
    """
    moment = now or datetime.now(UTC)
    pending_providers: ConcurrentStableList[str] = ConcurrentStableList()
    for provider in providers:
        if _view_stale(provider=provider, moment=moment, ttl=ttl):
            pending_providers.add(provider)
    pending_consumer = consumer
    if pending_consumer is not None and not _view_stale(consumer=pending_consumer, moment=moment, ttl=ttl):
        pending_consumer = None
    if not pending_providers and pending_consumer is None:
        return
    source = _SOURCE_HOLDER.get(_SOURCE_KEY)
    if source is None:
        raise CatalogError("授权视图来源未登记（请检查应用装配是否调用 register_capability_grant_source）")
    views = await source.load_all(providers=pending_providers, consumer=pending_consumer)
    prime_grant_views(views, now=moment)


def _view_stale(*, provider: str | None = None, consumer: str | None = None, moment: datetime, ttl: float) -> bool:
    """维度快照是否需要重拉（缺失或已超 TTL）。

    Args:
        provider: 提供方业务域。
        consumer: 消费方服务键。
        moment: 判定基准时刻。
        ttl: 快照有效期（秒）。

    Returns:
        bool: 需要重拉返回 True。
    """
    cached = _SNAPSHOTS.get(grant_view_key(provider=provider, consumer=consumer))
    return cached is None or moment - cached.loaded_at >= timedelta(seconds=ttl)


def capability_grant_pairs(
    *, provider: str | None = None, consumer: str | None = None
) -> ConcurrentStableFrozenList[CapabilityGrant]:
    """同步读授权视图快照（出站 scope 派生用；未加载返回空清单，不抛错）。

    Args:
        provider: 提供方业务域（入站维度）。
        consumer: 消费方服务键（出站维度）。

    Returns:
        ConcurrentStableFrozenList[CapabilityGrant]: 该维度的授权记录（未加载为空）。
    """
    snapshot = _SNAPSHOTS.get(grant_view_key(provider=provider, consumer=consumer))
    return ConcurrentStableFrozenList() if snapshot is None else snapshot.grants


def granted_scopes(consumer: str) -> ConcurrentStableFrozenList[str]:
    """派生消费方的出站 scope 集合（`svc:{业务域}:read|write`）。

    Args:
        consumer: 消费方服务键（当前服务）。

    Returns:
        ConcurrentStableFrozenList[str]: scope 集合（插入序去重；`codes` 类不产生）。
    """
    if not consumer:
        return ConcurrentStableFrozenList()
    catalog = collaboration_catalog_view()
    scopes: ConcurrentStableList[str] = ConcurrentStableList()
    for grant in capability_grant_pairs(consumer=consumer):
        if not is_grant_effective(grant):
            continue
        record = next((item for item in catalog if item.name == grant.capability_name), None)
        if record is None or record.status == CollaborationStatus.DISABLED:
            continue
        action = scope_action_of(record.kind)
        if action is None:
            continue
        scope = f"{SCOPE_PREFIX}:{record.domain}:{action}"
        if scope not in scopes:
            scopes.add(scope)
    return ConcurrentStableFrozenList(scopes)


def granted_consumers(capability: str) -> ConcurrentStableFrozenList[str]:
    """派生能力的入站允许消费方集合（本能力的有效分配）。

    Args:
        capability: 能力名。

    Returns:
        ConcurrentStableFrozenList[str]: 有效授权的消费方标识（插入序去重）。
    """
    domain = capability_domain(capability)
    consumers: ConcurrentStableList[str] = ConcurrentStableList()
    for grant in capability_grant_pairs(provider=domain):
        if grant.capability_name != capability:
            continue
        if not is_grant_effective(grant):
            continue
        if grant.consumer_key not in consumers:
            consumers.add(grant.consumer_key)
    return ConcurrentStableFrozenList(consumers)


def capability_domain(capability: str) -> str:
    """取能力的提供方业务域（授权视图的入站维度）。

    Args:
        capability: 能力名。

    Returns:
        str: 业务域标识。

    Raises:
        CatalogError: 能力未在目录登记（端点声明的能力与清单不一致，属配置漂移）。
    """
    for record in collaboration_catalog_view():
        if record.name == capability:
            return record.domain
    raise CatalogError(f"能力未登记：{capability}（端点声明的能力须与产品清单 [[collaborations]] 一致）")


def decide_capability_access(capability: str, consumer: str, *, now: datetime | None = None) -> str:
    """入站判定：消费方对能力是否有有效分配。

    Args:
        capability: 能力名。
        consumer: 消费方标识（服务 JWT 签发方）。
        now: 判定基准时刻（缺省取当前 UTC）。

    Returns:
        str: `allowed` / `denied` / `expired`。
    """
    moment = now or datetime.now(UTC)
    domain = capability_domain(capability)
    matched: ConcurrentStableList[CapabilityGrant] = ConcurrentStableList()
    for grant in capability_grant_pairs(provider=domain):
        if grant.capability_name == capability and grant.consumer_key == consumer:
            matched.add(grant)
    if not matched:
        return CALL_RESULT_DENIED
    if any(is_grant_effective(grant, now=moment) for grant in matched):
        return CALL_RESULT_ALLOWED
    return CALL_RESULT_EXPIRED


async def record_capability_call(
    metrics: BaseMetrics | None,
    *,
    capability: str,
    consumer: str,
    result: str,
) -> None:
    """按「调用方 × 能力」打点（调用量 / 失败率 / 越权）。

    Args:
        metrics: 指标器（None 表示不记录）。
        capability: 能力名。
        consumer: 消费方标识。
        result: 判定结果（`allowed` / `denied` / `expired`）。
    """
    if metrics is None:
        return
    labels: ConcurrentStableDict[str, str] = ConcurrentStableDict(
        {"capability": capability, "consumer": consumer, "result": result}
    )
    await metrics.counter(METRIC_CAPABILITY_CALL, labels=labels)
    if result == CALL_RESULT_ALLOWED:
        return
    await metrics.counter(
        METRIC_CAPABILITY_DENIED, labels=ConcurrentStableDict({"capability": capability, "consumer": consumer})
    )
    get_logger(_LOGGER).warning(
        "capability_access_denied",
        capability=capability,
        consumer=consumer,
        reason=result,
    )


async def check_capability_access(
    capability: str,
    consumer: str,
    *,
    metrics: BaseMetrics | None = None,
) -> None:
    """入站校验单点入口（确保视图新鲜 → 判定 → 打点 → 拒绝即抛）。

    Args:
        capability: 端点声明的能力名。
        consumer: 调用方服务标识（服务 JWT 签发方）。
        metrics: 指标器（None 表示不记录）。

    Raises:
        PermissionError: 无有效分配（30001 / 403），消息含能力名、消费方与原因。
        CatalogError: 能力未登记或授权视图来源不可用（配置漂移 / 未装配，拒启级）。
    """
    if not consumer:
        raise PermissionError(f"缺少调用方服务标识，无法判定能力授权：{capability}")
    domain = capability_domain(capability)
    await ensure_grant_view(provider=domain)
    result = decide_capability_access(capability, consumer)
    await record_capability_call(metrics, capability=capability, consumer=consumer, result=result)
    if result == CALL_RESULT_ALLOWED:
        return
    reason = "授权已过期" if result == CALL_RESULT_EXPIRED else "无有效分配（越界）"
    raise PermissionError(f"未授权访问能力：{capability}（消费方 {consumer}；{reason}）")


def grant_view_key(*, provider: str | None = None, consumer: str | None = None) -> str:
    """视图键（`provider` / `consumer` 二选一，都缺或都给即拒）。

    Args:
        provider: 提供方业务域。
        consumer: 消费方服务键。

    Returns:
        str: 视图键。

    Raises:
        CatalogError: 维度取值非法（内部契约错误，非用户输入）。
    """
    if (provider is None) == (consumer is None):
        raise CatalogError("授权视图维度须且只须给出 provider 或 consumer 之一")
    return f"provider:{provider}" if provider is not None else f"consumer:{consumer}"
