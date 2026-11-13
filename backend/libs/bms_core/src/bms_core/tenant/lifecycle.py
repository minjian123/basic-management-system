"""租户生命周期事件与产品资源动作（07D `01_04`）：契约、幂等与失败语义。

- **单一权威**：租户开通 / 停用 / 启用 / 删除只由基座决定并落状态；产品只消费 `tenant.*` 事件，
  不自建租户状态表 / 状态机、不轮询基座租户表。
- **事件名**：沿用已登记的 `tenant.created` / `tenant.suspended` / `tenant.activated` / `tenant.deleted`
  （租户事件族 `2.2.0`），并登记 `tenant.purged`（`1.0.0`）；需求文本的 disabled / enabled 即
  suspended / activated，不另立同义事件。
- **两步删除**（任务 `04_03`）：`deleted` = 停写、**不授权删数据**；`purged` = 平台已物理清理，产品此刻才删数据。
- **幂等三层**：投递级 `(consumer, event_id)`（既有 `sys_event_consumed` 账本）→ 业务级
  `(tenant_id, action, version)`（本模块 `applied_version` / `mark_applied`）→ 动作自身幂等。
- **失败语义**：动作抛错**不记账、原样上抛**，由消费组运行时的退避重试与死信兜底（当前消费实现待 msg 版落地）；
  分发器不吞错（吞错等于静默丢资源）。
- **保留期**：`on_deleted` 内按 `ScopeResourceTypeRecord.retention_days` / `removal_policy` 处置；
  审计记录不随资源删除。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import cast

from fastapi import Request

from bms_core.audit.events import audit_aggregate_key
from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableFrozenDict
from bms_core.core.config import Settings
from bms_core.core.exceptions import ConfigError, EventContractError
from bms_core.core.logging import get_logger
from bms_core.core.objects import BaseFrameworkObject, BaseValueObject
from bms_core.core.plugin import DEFAULT_CONTRACT_VERSION, NULL_PLUGIN_NAME, BasePluggable, resolve_plugin
from bms_core.events.base import EventEnvelope
from bms_core.events.platform_events import TENANT_ID_PAYLOAD_KEY

__all__ = [
    "LIFECYCLE_APPLIED",
    "LIFECYCLE_SKIPPED",
    "TENANT_ACTION_ACTIVATED",
    "TENANT_ACTION_CREATED",
    "TENANT_ACTION_DELETED",
    "TENANT_ACTION_PURGED",
    "TENANT_ACTION_SUSPENDED",
    "TENANT_ACTIVATED",
    "TENANT_CREATED",
    "TENANT_DELETED",
    "TENANT_LIFECYCLE_ACTIONS",
    "TENANT_LIFECYCLE_EVENT_TYPES",
    "TENANT_PURGED",
    "TENANT_SUSPENDED",
    "BaseTenantResourceHandler",
    "TenantLifecycleContext",
    "TenantLifecycleDispatcher",
    "build_tenant_lifecycle_event",
    "get_tenant_resource_handler",
]

TENANT_CREATED = "tenant.created"
TENANT_SUSPENDED = "tenant.suspended"
TENANT_ACTIVATED = "tenant.activated"
TENANT_DELETED = "tenant.deleted"
TENANT_PURGED = "tenant.purged"

TENANT_ACTION_CREATED = "created"
TENANT_ACTION_SUSPENDED = "suspended"
TENANT_ACTION_ACTIVATED = "activated"
TENANT_ACTION_DELETED = "deleted"
TENANT_ACTION_PURGED = "purged"

TENANT_LIFECYCLE_EVENT_TYPES: ConcurrentStableFrozenDict[str, str] = ConcurrentStableFrozenDict(
    {
        TENANT_CREATED: TENANT_ACTION_CREATED,
        TENANT_SUSPENDED: TENANT_ACTION_SUSPENDED,
        TENANT_ACTIVATED: TENANT_ACTION_ACTIVATED,
        TENANT_DELETED: TENANT_ACTION_DELETED,
        TENANT_PURGED: TENANT_ACTION_PURGED,
    }
)
"""事件类型 → 动作名（唯一映射；分发器只认这张表）。"""

TENANT_LIFECYCLE_ACTIONS: ConcurrentStableFrozenDict[str, str] = ConcurrentStableFrozenDict(
    {action: event_type for event_type, action in TENANT_LIFECYCLE_EVENT_TYPES.items()}
)
"""动作名 → 事件类型（反向表；业务侧按动作名写判断时用）。"""

LIFECYCLE_APPLIED = "applied"
LIFECYCLE_SKIPPED = "skipped"

_LOGGER = get_logger("bms.tenant_lifecycle")


@dataclass(frozen=True)
class TenantLifecycleContext(BaseValueObject):
    """一次租户生命周期动作的入参（不可变）。

    Attributes:
        tenant_id: 租户雪花主键。
        action: 动作名（`created` / `suspended` / `activated` / `deleted` / `purged`）。
        version: 事件版本戳（`sys_tenant.version`；旧事件为 0）。
        db_key: 租户数据源键（产品据此定位本租户库 / 目录）。
        status: 事件发生后的租户状态（`provisioning` / `active` / `suspended` / `deleted` / `purged`）。
        event_id: 事件 ID（投递级幂等键，排障用）。
        occurred_at: 事件发生时间（UTC）。
    """

    tenant_id: int
    action: str
    version: int
    db_key: str
    status: str
    event_id: str | None = None
    occurred_at: datetime | None = None


def build_tenant_lifecycle_event(
    *,
    event_type: str,
    tenant_id: int | str,
    db_key: str,
    status: str,
    version: int | None = None,
    occurred_at: datetime | None = None,
    trace_id: str | None = None,
    extra: ConcurrentStableDict[str, object] | None = None,
) -> EventEnvelope:
    """构造租户生命周期事件信封（信封租户位与载荷同值，聚合键按租户分区）。

    Args:
        event_type: 五类事件类型之一。
        tenant_id: 租户雪花主键（整数或十进制字符串）。
        db_key: 租户数据源键。
        status: 事件发生后的租户状态。
        version: 版本戳（`sys_tenant.version`）；None 不写载荷，消费侧按 0 处理。
        occurred_at: 事件时间；None 由发件箱写入时取当前时刻。
        trace_id: 链路 id。
        extra: 事件专属附加载荷（如 `tenant.purged` 的 `dropped_services` / `failed_services`）。

    Returns:
        EventEnvelope: 事件信封。

    Raises:
        ConfigError: 事件类型不在五类之内（编程错误，非运行期数据问题）。
    """
    if event_type not in TENANT_LIFECYCLE_EVENT_TYPES:
        raise ConfigError(f"非法租户生命周期事件类型（仅支持 {list(TENANT_LIFECYCLE_EVENT_TYPES)}）：{event_type}")
    tenant_text = str(tenant_id)
    payload: ConcurrentStableDict[str, object] = ConcurrentStableDict(
        {
            TENANT_ID_PAYLOAD_KEY: tenant_text,
            "db_key": db_key,
            "status": status,
        }
    )
    if version is not None:
        payload.set("version", int(version))
    if extra:
        for key, value in extra.items():
            payload.set(key, value)
    return EventEnvelope(
        event_type=event_type,
        payload=payload,
        tenant_id=tenant_text,
        trace_id=trace_id,
        occurred_at=occurred_at,
        aggregate_key=audit_aggregate_key(tenant_text),
    )


class BaseTenantResourceHandler(BasePluggable, ABC):
    """产品资源动作契约（插件键 `tenant_resources`）：五动作 + 幂等账本。

    账本与资源**同库同事务**由产品实现（基座另存一份会引入两阶段一致性问题）；动作必须幂等可重入。
    """

    key: str = "tenant_resources"
    plugin_key: str = "tenant_resources"
    plugin_name: str = NULL_PLUGIN_NAME
    contract_version: str = DEFAULT_CONTRACT_VERSION

    @abstractmethod
    async def applied_version(self, *, tenant_id: int, action: str) -> int:
        """已成功处理到的版本（业务级幂等判定依据）。

        Args:
            tenant_id: 租户主键。
            action: 动作名。

        Returns:
            int: 已处理版本；无记录返回 `-1`。
        """
        ...

    @abstractmethod
    async def mark_applied(self, *, tenant_id: int, action: str, version: int) -> None:
        """记账（须与资源动作同事务）。

        Args:
            tenant_id: 租户主键。
            action: 动作名。
            version: 已处理的版本。
        """
        ...

    async def on_created(self, context: TenantLifecycleContext) -> None:
        """懒初始化（命名空间 / 默认配额 / 本地索引）；失败不阻塞开通。

        Args:
            context: 生命周期上下文（动作名恒为 `created`）。
        """
        return None

    async def on_suspended(self, context: TenantLifecycleContext) -> None:
        """拒绝收发（复用基座版本戳，不自建 TTL 缓存）。

        Args:
            context: 生命周期上下文（动作名恒为 `suspended`）。
        """
        return None

    async def on_activated(self, context: TenantLifecycleContext) -> None:
        """恢复受理。

        Args:
            context: 生命周期上下文（动作名恒为 `activated`）。
        """
        return None

    async def on_deleted(self, context: TenantLifecycleContext) -> None:
        """停写：断连接、清延迟区 / 易失资源；**不删数据**（保留期内可恢复）。

        Args:
            context: 生命周期上下文（动作名恒为 `deleted`）。
        """
        return None

    async def on_purged(self, context: TenantLifecycleContext) -> None:
        """物理清理：平台已删该租户数据，产品此刻删除自身残留（主题 / 位点 / 元数据）。

        缺省实现记 **WARNING**（而非静默 no-op）：`purged` 之后的残留数据无人再清，
        静默会表现为「注销成功了但数据一直在」，只有告警能让漏配实现暴露出来。

        Args:
            context: 生命周期上下文（动作名恒为 `purged`）。
        """
        _LOGGER.warning(
            "tenant_purged_unhandled",
            tenant_id=context.tenant_id,
            db_key=context.db_key,
            hint="产品未实现 on_purged，该租户残留资源不会被清理",
        )


class TenantLifecycleDispatcher(BaseFrameworkObject):
    """生命周期事件分发器：校验 → 版本判定 → 动作 → 记账。

    只做路由与幂等，不做重试：动作失败原样上抛，交给消费组的退避重试与死信。
    """

    def __init__(self, *, handler: BaseTenantResourceHandler) -> None:
        """初始化。

        Args:
            handler: 产品资源动作实现。
        """
        self._handler = handler

    async def dispatch(self, event: EventEnvelope) -> str:
        """分发一条租户生命周期事件。

        Args:
            event: 事件信封。

        Returns:
            str: `applied`（已执行）/ `skipped`（版本不新或非生命周期事件）。

        Raises:
            EventContractError: 事件类型未知或载荷缺必填字段（10010，消费侧转死信）。
        """
        action = TENANT_LIFECYCLE_EVENT_TYPES.get(event.event_type)
        if action is None:
            raise EventContractError(f"非租户生命周期事件，分发器不处理：{event.event_type}")
        context = _context_of(event, action=action)
        applied = await self._handler.applied_version(tenant_id=context.tenant_id, action=action)
        if context.version <= applied:
            _LOGGER.info(
                "tenant_lifecycle_skipped",
                tenant_id=context.tenant_id,
                action=action,
                version=context.version,
                applied=applied,
                event_id=context.event_id,
            )
            return LIFECYCLE_SKIPPED
        await self._invoke(context)
        await self._handler.mark_applied(tenant_id=context.tenant_id, action=action, version=context.version)
        _LOGGER.info(
            "tenant_lifecycle_applied",
            tenant_id=context.tenant_id,
            action=action,
            version=context.version,
            event_id=context.event_id,
        )
        return LIFECYCLE_APPLIED

    async def _invoke(self, context: TenantLifecycleContext) -> None:
        """按动作名调用对应方法。

        Args:
            context: 生命周期上下文。

        Raises:
            EventContractError: 动作名不在五类之内（理论不可达，防御性）。
        """
        if context.action == TENANT_ACTION_CREATED:
            await self._handler.on_created(context)
        elif context.action == TENANT_ACTION_SUSPENDED:
            await self._handler.on_suspended(context)
        elif context.action == TENANT_ACTION_ACTIVATED:
            await self._handler.on_activated(context)
        elif context.action == TENANT_ACTION_DELETED:
            await self._handler.on_deleted(context)
        elif context.action == TENANT_ACTION_PURGED:
            await self._handler.on_purged(context)
        else:  # pragma: no cover - 映射表已限定五类
            raise EventContractError(f"未知生命周期动作：{context.action}")


def _context_of(event: EventEnvelope, *, action: str) -> TenantLifecycleContext:
    """从事件信封解析生命周期上下文（缺必填字段即 fail-closed）。

    Args:
        event: 事件信封。
        action: 动作名（由事件类型映射所得）。

    Returns:
        TenantLifecycleContext: 生命周期上下文。

    Raises:
        EventContractError: `tenant_id` / `db_key` / `status` 缺失或形态非法（10010）。
    """
    raw_tenant = event.payload.get(TENANT_ID_PAYLOAD_KEY)
    if not isinstance(raw_tenant, str) or not raw_tenant:
        raise EventContractError(f"租户事件缺少 {TENANT_ID_PAYLOAD_KEY}：{event.event_type}")
    try:
        tenant_id = int(raw_tenant)
    except ValueError as exc:
        raise EventContractError(f"租户事件 {TENANT_ID_PAYLOAD_KEY} 非十进制雪花 id：{raw_tenant}") from exc
    db_key = event.payload.get("db_key")
    if not isinstance(db_key, str) or not db_key:
        raise EventContractError(f"租户事件缺少 db_key：{event.event_type}")
    status = event.payload.get("status")
    if not isinstance(status, str) or not status:
        raise EventContractError(f"租户事件缺少 status：{event.event_type}")
    raw_version = event.payload.get("version")
    if raw_version is None:
        version = 0
    elif isinstance(raw_version, int) and not isinstance(raw_version, bool):
        version = raw_version
    else:
        raise EventContractError(f"租户事件 version 非整数：{raw_version!r}")
    return TenantLifecycleContext(
        tenant_id=tenant_id,
        action=action,
        version=version,
        db_key=db_key,
        status=status,
        event_id=event.event_id,
        occurred_at=event.occurred_at,
    )


def get_tenant_resource_handler(request: Request) -> BaseTenantResourceHandler:
    """取应用级产品资源动作实现（依赖注入提供者）。

    Args:
        request: 请求对象。

    Returns:
        BaseTenantResourceHandler: 已装配的实现。

    Raises:
        PluginError: 配置的实现名未登记 / 契约版本不兼容。
    """
    settings = cast("Settings", request.app.state.settings)
    return cast(
        "BaseTenantResourceHandler",
        resolve_plugin(
            "tenant_resources",
            settings.tenant_resources.provider,
            expected_version=BaseTenantResourceHandler.contract_version,
        ),
    )
