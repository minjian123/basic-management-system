"""通知组消费（`notification-inbox`）：`notification.requested` → 偏好过滤 → 落库 / 推送 / 外发。

- 组声明在 `main.py::event_consumer_records()`；本模块只提供处理器。
- 站内信渠道开启才落库并发布 `notification.sent`；邮件 / 短信按开关交 `BaseNotifier`。
- 免打扰命中：站内信仍落库，仅跳过实时推送。
- 推送 / 邮件失败只告警，不重试、不回滚已落库事实。
"""

from __future__ import annotations

from collections.abc import AsyncGenerator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from datetime import UTC, datetime
from typing import cast

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableFrozenDict, ConcurrentStableList
from bms_core.core.config import get_settings
from bms_core.core.context import (
    reset_current_tenant,
    reset_current_tenant_id,
    reset_tenant_context,
    set_current_tenant,
    set_current_tenant_id,
    set_tenant_context,
)
from bms_core.core.exceptions import (
    ChannelConfigInvalidError,
    EventConsumeError,
    ParamError,
    SmsTemplateUnavailableError,
    TemplateRenderError,
)
from bms_core.core.logging import get_logger
from bms_core.core.plugin import resolve_plugin
from bms_core.db.engine import EngineFactory
from bms_core.db.registry import EngineRegistry
from bms_core.db.session import DbSession, SessionFactory, session_scope
from bms_core.db.tenant import TenantContext, TenantLookup
from bms_core.db.tenant_source import build_tenant_lookup
from bms_core.events.base import EventConsumer, EventEnvelope
from bms_core.events.consumer_records import EventConsumerRecord
from bms_core.notification.base import NotificationPayload
from bms_core.notification.preference import (
    BaseNotificationPreferenceStore,
    NotificationPreference,
    default_notification_preference,
)
from bms_core.notification.request import (
    NOTIFICATION_TYPE_APPROVAL,
    NOTIFICATION_TYPES,
    NotificationRequest,
)
from bms_core.outbox.base import BaseOutboxStore
from bms_core.ws.base import BaseRealtimePublisher, RealtimeEvent
from bms_notification.domains.notification.services.generation import NotificationGenerationService
from bms_notification.domains.notification.services.outbound import (
    CHANNEL_EMAIL,
    CHANNEL_SMS,
    DispatchRequest,
    JobSubmitter,
    OutboundDispatchService,
)
from bms_notification.domains.notification.services.recipient import RecipientResolver

__all__ = ["NOTIFICATION_GROUP", "NotificationRequestConsumer", "event_consumer_records"]

NOTIFICATION_GROUP = "notification-inbox"
"""消费组名（装载时补前缀，如 `bms-notification-inbox`）。"""

_LOGGER = get_logger("bms")

_registry_cache: EngineRegistry | None = None
"""懒建引擎注册表（消费处理器无请求态）。"""

_lookup_cache: TenantLookup | None = None
"""懒建租户源（按事件租户主键解析库键）。"""

_recipient_resolver_cache: RecipientResolver | None = None
"""懒建收件人解析器（平台用户只读出口）。"""

type SessionOpener = Callable[[TenantContext], AbstractAsyncContextManager[DbSession]]
"""按租户上下文开合会话（测试注入回滚会话）。"""


def _registry() -> EngineRegistry:
    """取（懒建）引擎注册表。

    Returns:
        EngineRegistry: 引擎注册表。
    """
    global _registry_cache
    if _registry_cache is None:
        _registry_cache = EngineRegistry(EngineFactory(get_settings()))
    return _registry_cache


def _lookup() -> TenantLookup:
    """取（懒建）租户源。

    Returns:
        TenantLookup: 租户源。
    """
    global _lookup_cache
    if _lookup_cache is None:
        settings = get_settings()
        _lookup_cache = build_tenant_lookup(
            settings.tenant.source,
            settings=settings,
            registry=_registry(),
            cache=None,
            session_factory=SessionFactory(),
        )
    return _lookup_cache


def _default_session_opener(tenant: TenantContext) -> AbstractAsyncContextManager[DbSession]:
    """按租户库键开会话。

    Args:
        tenant: 租户上下文。

    Returns:
        AbstractAsyncContextManager[DbSession]: 会话上下文。
    """

    @asynccontextmanager
    async def _open() -> AsyncGenerator[DbSession]:
        async with session_scope(_registry(), db_key=tenant.db_key, factory=SessionFactory()) as session:
            yield session

    return _open()


class NotificationRequestConsumer(EventConsumer):
    """单事件处理器：消费一条 `notification.requested`。"""

    def __init__(
        self,
        *,
        preference: BaseNotificationPreferenceStore | None = None,
        realtime: BaseRealtimePublisher | None = None,
        recipient_resolver: RecipientResolver | None = None,
        outbound_jobs: JobSubmitter | None = None,
        outbox: BaseOutboxStore | None = None,
        tenant_lookup: TenantLookup | None = None,
        session_opener: SessionOpener | None = None,
    ) -> None:
        """初始化（默认按配置解析；测试可全部注入替身）。

        Args:
            preference: 通知偏好读取实现。
            realtime: 实时推送实现。
            recipient_resolver: 收件人解析器。
            outbound_jobs: 外发作业提交器。
            outbox: 发件箱存储。
            tenant_lookup: 租户源。
            session_opener: 按租户开合会话。
        """
        self._preference = preference
        self._realtime = realtime
        self._recipient_resolver = recipient_resolver
        self._outbound_jobs = outbound_jobs
        self._outbox = outbox
        self._tenant_lookup = tenant_lookup
        self._session_opener = session_opener

    @property
    def event_type(self) -> str:
        """事件类型（订阅主题）。

        Returns:
            str: 事件类型。
        """
        return "notification.requested"

    async def consume(self, event: EventEnvelope) -> None:
        """消费一条通知请求。

        Args:
            event: 事件信封。

        Raises:
            EventConsumeError: 载荷非法 / 缺租户 / 租户不可解析。
        """
        request = _parse_request(event)
        tenant = await self._resolve_tenant(event)
        tokens = (
            set_tenant_context(tenant),
            set_current_tenant(tenant.code),
            set_current_tenant_id(str(tenant.tenant_id) if tenant.tenant_id is not None else None),
        )
        try:
            preference = await self._load_preference(request.user_id)
            if preference.channel_enabled("inbox"):
                await self._deliver_inbox(event, request, tenant, preference)
            await self._deliver_external(event, request, tenant, preference)
        finally:
            reset_tenant_context(tokens[0])
            reset_current_tenant(tokens[1])
            reset_current_tenant_id(tokens[2])

    async def _deliver_inbox(
        self,
        event: EventEnvelope,
        request: NotificationRequest,
        tenant: TenantContext,
        preference: NotificationPreference,
    ) -> None:
        """站内信落库 + `notification.sent` + 条件推送。"""
        opener = self._session_opener or _default_session_opener
        async with opener(tenant) as session, session.begin():
            row = await NotificationGenerationService(session, outbox=self._outbox).create(
                request, tenant_id=str(event.tenant_id)
            )
            created_at = row.created_at
        if preference.in_quiet_hours(datetime.now(UTC).replace(tzinfo=None)):
            _LOGGER.info("通知命中免打扰，跳过实时推送", user_id=request.user_id)
            return
        await self._push(request, created_at)

    async def _push(self, request: NotificationRequest, created_at: datetime | None) -> None:
        """按事件约定推送 `notification.new` / `approval.todo`（失败只告警）。"""
        realtime = self._realtime or _default_realtime()
        payload = NotificationPayload(
            title=request.title,
            type=request.type,
            biz_type=request.biz_type,
            biz_id=request.biz_id,
            created_at=created_at,
        )
        data = ConcurrentStableFrozenDict(payload.model_dump())
        events = ["notification.new"]
        if request.type == NOTIFICATION_TYPE_APPROVAL:
            events.append("approval.todo")
        for name in events:
            try:
                await realtime.emit(RealtimeEvent(event=name, data=data, user_id=str(request.user_id)))
            except Exception as exc:  # 推送失败不回滚、不重试，靠重连补偿
                _LOGGER.warning("通知实时推送失败", user_id=request.user_id, event_name=name, error=str(exc))

    async def _deliver_external(
        self,
        event: EventEnvelope,
        request: NotificationRequest,
        tenant: TenantContext,
        preference: NotificationPreference,
    ) -> None:
        """邮件 / 短信渠道：统一经外发调度器（渠道过滤 / 免打扰 / 日志 / 作业）。

        渠道关闭时跳过；短信未带模板 code 时记失败（云短信只支持模板）。
        """
        targets: ConcurrentStableList[
            tuple[str, str | None, str | None, ConcurrentStableFrozenDict[str, str] | None]
        ] = ConcurrentStableList(
            (
                (CHANNEL_EMAIL, request.email, request.title, None),
                (CHANNEL_SMS, request.phone, None, request.sms_params),
            )
        )
        opener = self._session_opener or _default_session_opener
        channels: ConcurrentStableList[
            tuple[str, str | None, str | None, ConcurrentStableFrozenDict[str, str] | None]
        ] = ConcurrentStableList()
        for channel, recipient, title, params in targets:
            if not preference.channel_enabled(channel):
                continue
            channels.append((channel, recipient, title, params))
        if not channels:
            return
        async with opener(tenant) as session, session.begin():
            dispatcher = OutboundDispatchService(
                session,
                preference=self._preference,
                recipient_resolver=self._recipient_resolver or _default_recipient_resolver(),
                jobs=self._outbound_jobs,
            )
            for channel, recipient, title, params in channels:
                dispatch_request = DispatchRequest(
                    channel=channel,
                    template_code=request.sms_template_code if channel == CHANNEL_SMS else None,
                    params=params or ConcurrentStableFrozenDict(),
                    user_id=request.user_id,
                    recipient=recipient,
                    transactional=False,
                    title=title or "",
                    content=request.content,
                    idempotency_key=f"notification:{event.event_id}:{channel}" if event.event_id else None,
                    record_skipped_when_disabled=False,
                    fail_on_missing_recipient=False,
                )
                try:
                    await dispatcher.dispatch(dispatch_request, preference=preference)
                except (ParamError, SmsTemplateUnavailableError, ChannelConfigInvalidError, TemplateRenderError) as exc:
                    await dispatcher.record_failure(dispatch_request, reason=str(exc))
                    _LOGGER.warning(
                        "通知外发未受理（已记失败）", channel=channel, user_id=request.user_id, error=str(exc)
                    )
                except Exception as exc:  # 外发是副作用：失败只告警，不影响站内信
                    _LOGGER.warning(
                        "通知外发异常（不影响站内信）", channel=channel, user_id=request.user_id, error=str(exc)
                    )

    async def _load_preference(self, user_id: int) -> NotificationPreference:
        """读取偏好（实现异常回落默认）。"""
        store = self._preference or _default_preference()
        try:
            return await store.load(user_id)
        except Exception as exc:
            _LOGGER.warning("通知偏好读取异常（回落默认）", user_id=user_id, error=str(exc))
            return default_notification_preference()

    async def _resolve_tenant(self, event: EventEnvelope) -> TenantContext:
        """解析事件租户。

        Raises:
            EventConsumeError: 缺租户位 / 租户不可解析。
        """
        if not event.tenant_id:
            raise EventConsumeError("通知请求缺少租户位")
        lookup = self._tenant_lookup or _lookup()
        try:
            return await lookup.by_id(event.tenant_id)
        except Exception as exc:
            raise EventConsumeError(f"通知请求租户不可解析：{event.tenant_id}") from exc


def _parse_request(event: EventEnvelope) -> NotificationRequest:
    """校验并解析事件载荷。

    Args:
        event: 事件信封。

    Returns:
        NotificationRequest: 通知请求。

    Raises:
        EventConsumeError: 必填字段缺失 / 类型非法 / 超长（毒消息转死信）。
    """
    payload = event.payload
    raw_user = payload.get("user_id")
    if not isinstance(raw_user, str) or not raw_user.isdigit():
        raise EventConsumeError("notification.requested 的 user_id 非法")
    raw_title = payload.get("title")
    if not isinstance(raw_title, str) or not raw_title.strip():
        raise EventConsumeError("notification.requested 的 title 非法")
    if len(raw_title) > 256:
        raise EventConsumeError("notification.requested 的 title 超长")
    raw_type = payload.get("type")
    if not isinstance(raw_type, str) or raw_type not in NOTIFICATION_TYPES:
        raise EventConsumeError("notification.requested 的 type 非法")
    content = payload.get("content")
    if content is not None and (not isinstance(content, str) or len(content) > 10000):
        raise EventConsumeError("notification.requested 的 content 非法")
    biz_type = _optional_text(payload.get("biz_type"), "biz_type", limit=64)
    biz_id = _optional_text(payload.get("biz_id"), "biz_id", limit=64)
    email = _optional_text(payload.get("email"), "email", limit=128)
    phone = _optional_text(payload.get("phone"), "phone", limit=32)
    sms_template_code = _optional_text(payload.get("sms_template_code"), "sms_template_code", limit=64)
    sms_params = _optional_params(payload.get("sms_params"))
    return NotificationRequest(
        user_id=int(raw_user),
        title=raw_title.strip(),
        type=raw_type,
        content=content or "",
        biz_type=biz_type,
        biz_id=biz_id,
        email=email,
        phone=phone,
        sms_template_code=sms_template_code,
        sms_params=sms_params,
    )


def _optional_params(value: object) -> ConcurrentStableFrozenDict[str, str] | None:
    """校验可选短信模板参数（扁平对象、字符串值、≤50 键）。

    Args:
        value: 原始值。

    Returns:
        ConcurrentStableFrozenDict[str, str] | None: 参数或 None。

    Raises:
        EventConsumeError: 非对象 / 值非字符串 / 超长。
    """
    if value is None:
        return None
    if not isinstance(value, dict):
        raise EventConsumeError("notification.requested 的 sms_params 非法")
    mapping = cast("dict[object, object]", value)
    if len(mapping) > 50:
        raise EventConsumeError("notification.requested 的 sms_params 过多")
    result: ConcurrentStableDict[str, str] = ConcurrentStableDict()
    for key, item in mapping.items():
        name = str(key)
        if not isinstance(item, str) or len(item) > 512:
            raise EventConsumeError("notification.requested 的 sms_params 值非法")
        result.set(name, item)
    return ConcurrentStableFrozenDict(result)


def _optional_text(value: object, name: str, *, limit: int) -> str | None:
    """校验可选文本字段。

    Args:
        value: 原始值。
        name: 字段名（错误信息用）。
        limit: 长度上限。

    Returns:
        str | None: 文本或 None。

    Raises:
        EventConsumeError: 非字符串或超长。
    """
    if value is None:
        return None
    if not isinstance(value, str) or len(value) > limit:
        raise EventConsumeError(f"notification.requested 的 {name} 非法")
    return value or None


def _default_preference() -> BaseNotificationPreferenceStore:
    """按配置解析通知偏好读取实现。"""
    settings = get_settings()
    return cast(
        "BaseNotificationPreferenceStore",
        resolve_plugin(
            "notification_preference",
            settings.notification_preference.provider,
            expected_version=BaseNotificationPreferenceStore.contract_version,
        ),
    )


def _default_realtime() -> BaseRealtimePublisher:
    """按配置解析实时推送实现。"""
    settings = get_settings()
    return cast(
        "BaseRealtimePublisher",
        resolve_plugin(
            "realtime_publisher",
            settings.realtime_publisher.provider,
            expected_version=BaseRealtimePublisher.contract_version,
        ),
    )


def _default_recipient_resolver() -> RecipientResolver:
    """按配置构建收件人解析器（进程级缓存；消费处理器无请求态）。"""
    global _recipient_resolver_cache
    if _recipient_resolver_cache is None:
        from bms_core.core.assembly import HttpServiceClientFactory

        _recipient_resolver_cache = RecipientResolver(HttpServiceClientFactory(get_settings()).create())
    return _recipient_resolver_cache


def event_consumer_records() -> ConcurrentStableList[EventConsumerRecord]:
    """通知组声明（一条事件）。

    Returns:
        ConcurrentStableList[EventConsumerRecord]: 消费组声明。
    """
    records: ConcurrentStableList[EventConsumerRecord] = ConcurrentStableList()
    records.add(
        EventConsumerRecord(
            consumer=NOTIFICATION_GROUP,
            event_type="notification.requested",
            handler_factory=_factory,
            ordered=False,
            description="通知组：notification.requested → 渠道过滤 → 站内信落库 + 实时推送",
        )
    )
    return records


def _factory() -> NotificationRequestConsumer:
    """构造处理器（每次返回独立实例）。

    Returns:
        NotificationRequestConsumer: 处理器。
    """
    return NotificationRequestConsumer()
