"""发件箱存储真实实现 `SqlOutboxStore`：会话绑定（仓储口径，flush 不提交）。

- `enqueue` 在业务事务内写发件箱（缺省补齐 `event_id` / `occurred_at` / `event_version`；
  按 `[event].contract_mode` 校验事件契约登记：`off` 不校验 / `warn` 记日志放行 / `enforce` 拒发）；
  投递器经 `claim_pending` / `mark_delivered` / `mark_failed` 在同一事务内完成读取与标记；
  死信看板经列表 / 详情 / 状态读写。
- 事务边界归调用方（工作单元 / 投递器），本类只 `flush` 不 `commit`。
"""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from sqlalchemy import ColumnElement, func, select, update
from sqlalchemy.engine import CursorResult

from bms_core.core.exceptions import ConfigError, EventContractError
from bms_core.core.id import id_generator
from bms_core.core.logging import get_logger
from bms_core.core.version import contract_major
from bms_core.db.sync import DbSession
from bms_core.events.base import DEFAULT_EVENT_VERSION, EventEnvelope
from bms_core.events.contracts import (
    EVENT_CONTRACT_MODE_ENFORCE,
    EVENT_CONTRACT_MODE_OFF,
    EVENT_CONTRACT_MODES,
    EventContract,
    resolve_event_contract,
)
from bms_core.models.outbox import SysEventDeadLetter, SysOutbox
from bms_core.outbox.base import (
    DEAD_LETTER_SOURCE_OUTBOX,
    ERROR_MSG_MAX_LENGTH,
    ORDER_SCAN_FACTOR,
    OUTBOX_STATUS_DEAD,
    OUTBOX_STATUS_DELIVERED,
    OUTBOX_STATUS_PENDING,
    BaseOutboxStore,
    DeadLetterRecord,
    OutboxRecord,
)


def _utc_now() -> datetime:
    """当前 UTC 时间（naive，跨库统一口径）。

    Returns:
        datetime: UTC 时间。
    """
    return datetime.now(UTC).replace(tzinfo=None)


def _truncate(text: str) -> str:
    """截断失败原因以对齐列宽。

    Args:
        text: 原始文本。

    Returns:
        str: 截断后文本。
    """
    return text[:ERROR_MSG_MAX_LENGTH]


def _to_record(row: SysOutbox) -> OutboxRecord:
    """ORM 行 → 发件箱记录。"""
    return OutboxRecord(
        event_id=row.event_id,
        event_type=row.event_type,
        event_version=row.event_version,
        aggregate_key=row.aggregate_key,
        tenant_id=row.tenant_id,
        payload=dict(row.payload),
        occurred_at=row.occurred_at,
        status=row.status,
        retry_count=row.retry_count,
        next_retry_at=row.next_retry_at,
        delivered_at=row.delivered_at,
        error_msg=row.error_msg,
    )


def _to_dead_record(row: SysEventDeadLetter) -> DeadLetterRecord:
    """ORM 行 → 死信记录。"""
    return DeadLetterRecord(
        id=row.id,
        source=row.source,
        event_id=row.event_id,
        event_type=row.event_type,
        consumer=row.consumer,
        aggregate_key=row.aggregate_key,
        tenant_id=row.tenant_id,
        payload=dict(row.payload),
        error_msg=row.error_msg,
        retry_count=row.retry_count,
        status=row.status,
        occurred_at=row.occurred_at,
    )


class SqlOutboxStore(BaseOutboxStore):
    """基于 SQLAlchemy 的发件箱存储（平台库 / 租户库同构）。

    `plugin_name` 不声明（避免零参类被插件注册表自动收集），经 `SqlOutboxStoreFactory`
    以 `sql` 显式登记（同 `LocalFieldTypeRegistry` 口径）。
    """

    def __init__(
        self,
        *,
        contract_mode: str = EVENT_CONTRACT_MODE_OFF,
        contract_resolver: Callable[[str], EventContract | None] | None = None,
    ) -> None:
        """初始化。

        Args:
            contract_mode: 签发契约校验模式（`off` / `warn` / `enforce`；缺省不校验，
                装配工厂按 `[event].contract_mode` 注入）。
            contract_resolver: 契约解析函数（缺省默认注册表解析；测试可注入隔离实现）。

        Raises:
            ConfigError: 校验模式非法。
        """
        if contract_mode not in EVENT_CONTRACT_MODES:
            raise ConfigError(f"事件契约校验模式非法：{contract_mode}（应为 {'/'.join(EVENT_CONTRACT_MODES)}）")
        self._contract_mode = contract_mode
        self._contract_resolver = contract_resolver or resolve_event_contract

    def _resolve_event_version(self, event: EventEnvelope) -> str:
        """解析事件版本：登记契约取契约版本、显式版本保真；按模式校验契约与版本。

        Args:
            event: 事件信封。

        Returns:
            str: 事件契约版本。

        Raises:
            EventContractError: `enforce` 模式下事件未登记契约或显式版本格式非法。
        """
        contract = self._contract_resolver(event.event_type)
        if contract is None and self._contract_mode != EVENT_CONTRACT_MODE_OFF:
            self._violation(f"事件未登记契约：{event.event_type}")
        if event.event_version is None:
            return contract.version if contract is not None else DEFAULT_EVENT_VERSION
        if contract_major(event.event_version) is None and self._contract_mode != EVENT_CONTRACT_MODE_OFF:
            self._violation(f"事件版本非法（应为 X.Y.Z）：{event.event_type}@{event.event_version}")
        return event.event_version

    def _violation(self, message: str) -> None:
        """契约违规处置：`enforce` 抛错、`warn` 记日志放行。

        Args:
            message: 违规明细。

        Raises:
            EventContractError: `enforce` 模式。
        """
        if self._contract_mode == EVENT_CONTRACT_MODE_ENFORCE:
            raise EventContractError(message)
        get_logger("bms_core.events").warning("event_contract_violation", detail=message)

    async def enqueue(self, session: DbSession, event: EventEnvelope) -> str:
        """写发件箱（同库同事务；缺省补齐 event_id / occurred_at / event_version）。

        Args:
            session: 业务事务会话。
            event: 事件信封。

        Returns:
            str: 事件 ID。
        """
        event_id = event.event_id or str(id_generator.next_id())
        occurred_at = event.occurred_at or _utc_now()
        event_version = self._resolve_event_version(event)
        session.add(
            SysOutbox(
                event_id=event_id,
                event_type=event.event_type,
                event_version=event_version,
                aggregate_key=event.aggregate_key,
                tenant_id=event.tenant_id,
                payload=dict(event.payload),
                occurred_at=occurred_at,
                status=OUTBOX_STATUS_PENDING,
            )
        )
        await session.flush()
        return event_id

    async def claim_pending(self, session: DbSession, *, now: datetime, limit: int) -> list[OutboxRecord]:
        """取待投递事件（同聚合仅队首、到期者）。

        Args:
            session: 会话。
            now: 当前时间（UTC）。
            limit: 返回上限。

        Returns:
            list[OutboxRecord]: 待投递记录。
        """
        if limit <= 0:
            return []
        statement = (
            select(SysOutbox)
            .where(SysOutbox.status == OUTBOX_STATUS_PENDING)
            .order_by(SysOutbox.id)
            .limit(limit * ORDER_SCAN_FACTOR)
        )
        rows = list((await session.execute(statement)).scalars())
        seen: set[str] = set()
        claimed: list[OutboxRecord] = []
        for row in rows:
            key = row.aggregate_key
            if key is not None:
                if key in seen:
                    continue
                seen.add(key)
                if row.next_retry_at is not None and row.next_retry_at > now:
                    continue
            claimed.append(_to_record(row))
            if len(claimed) >= limit:
                break
        return claimed

    async def mark_delivered(self, session: DbSession, event_id: str) -> None:
        """标记已投递。

        Args:
            session: 会话。
            event_id: 事件 ID。
        """
        row = await self._by_event_id(session, event_id)
        if row is None:
            return
        row.status = OUTBOX_STATUS_DELIVERED
        row.delivered_at = _utc_now()
        row.error_msg = None
        await session.flush()

    async def mark_failed(
        self,
        session: DbSession,
        event_id: str,
        error: str,
        *,
        max_retries: int,
        backoff: float,
    ) -> bool:
        """标记失败（指数退避；超限转死信并插死信行）。

        Args:
            session: 会话。
            event_id: 事件 ID。
            error: 失败原因。
            max_retries: 转死信前的最大重试次数。
            backoff: 退避基数（秒）。

        Returns:
            bool: 已转死信 True（仍待重试 False）。
        """
        row = await self._by_event_id(session, event_id)
        if row is None:
            return False
        row.retry_count += 1
        row.error_msg = _truncate(error)
        if row.retry_count >= max_retries:
            row.status = OUTBOX_STATUS_DEAD
            row.next_retry_at = None
            session.add(
                SysEventDeadLetter(
                    source=DEAD_LETTER_SOURCE_OUTBOX,
                    event_id=row.event_id,
                    event_type=row.event_type,
                    aggregate_key=row.aggregate_key,
                    tenant_id=row.tenant_id,
                    payload=dict(row.payload),
                    error_msg=_truncate(error),
                    retry_count=row.retry_count,
                    occurred_at=row.occurred_at,
                )
            )
            await session.flush()
            return True
        row.next_retry_at = _utc_now() + timedelta(seconds=backoff * (2 ** (row.retry_count - 1)))
        await session.flush()
        return False

    async def replay(
        self,
        session: DbSession,
        *,
        event_id: str | None = None,
        event_type: str | None = None,
        aggregate_key: str | None = None,
        since: datetime | None = None,
        limit: int | None = None,
    ) -> int:
        """重放：已投递 / 死信 → 待投递。

        Args:
            session: 会话。
            event_id: 事件 ID 精确筛选。
            event_type: 事件类型筛选。
            aggregate_key: 聚合键筛选。
            since: 发生时间下限（UTC）。
            limit: 重置上限。

        Returns:
            int: 重置条数。
        """
        conditions: list[ColumnElement[bool]] = [SysOutbox.status.in_((OUTBOX_STATUS_DELIVERED, OUTBOX_STATUS_DEAD))]
        if event_id is not None:
            conditions.append(SysOutbox.event_id == event_id)
        if event_type is not None:
            conditions.append(SysOutbox.event_type == event_type)
        if aggregate_key is not None:
            conditions.append(SysOutbox.aggregate_key == aggregate_key)
        if since is not None:
            conditions.append(SysOutbox.occurred_at >= since)
        id_statement = select(SysOutbox.id).where(*conditions).order_by(SysOutbox.id)
        if limit is not None:
            id_statement = id_statement.limit(limit)
        ids = list((await session.execute(id_statement)).scalars())
        if not ids:
            return 0
        reset = (
            update(SysOutbox)
            .where(SysOutbox.id.in_(ids))
            .values(
                status=OUTBOX_STATUS_PENDING,
                retry_count=0,
                next_retry_at=None,
                delivered_at=None,
                error_msg=None,
            )
        )
        result = cast("CursorResult[Any]", await session.execute(reset))
        await session.flush()
        return int(result.rowcount or 0)

    async def list_dead_letters(
        self,
        session: DbSession,
        *,
        status: str | None = None,
        source: str | None = None,
        offset: int = 0,
        limit: int = 20,
    ) -> tuple[list[DeadLetterRecord], int]:
        """死信列表（倒序 + 筛选 + 分页）。

        Args:
            session: 会话。
            status: 处置状态筛选。
            source: 来源筛选。
            offset: 偏移。
            limit: 上限。

        Returns:
            tuple[list[DeadLetterRecord], int]: （记录列表，总数）。
        """
        conditions: list[ColumnElement[bool]] = []
        if status is not None:
            conditions.append(SysEventDeadLetter.status == status)
        if source is not None:
            conditions.append(SysEventDeadLetter.source == source)
        count_statement = select(func.count()).select_from(SysEventDeadLetter).where(*conditions)
        total = int((await session.execute(count_statement)).scalar_one())
        statement = (
            select(SysEventDeadLetter)
            .where(*conditions)
            .order_by(SysEventDeadLetter.id.desc())
            .offset(offset)
            .limit(limit)
        )
        rows = list((await session.execute(statement)).scalars())
        return [_to_dead_record(row) for row in rows], total

    async def get_dead_letter(self, session: DbSession, dead_letter_id: int) -> DeadLetterRecord | None:
        """取单条死信。

        Args:
            session: 会话。
            dead_letter_id: 死信主键。

        Returns:
            DeadLetterRecord | None: 记录；不存在 None。
        """
        row = await session.get(SysEventDeadLetter, dead_letter_id)
        return None if row is None else _to_dead_record(row)

    async def set_dead_letter_status(self, session: DbSession, dead_letter_id: int, status: str) -> bool:
        """设置死信处置状态。

        Args:
            session: 会话。
            dead_letter_id: 死信主键。
            status: 目标状态。

        Returns:
            bool: 命中 True；不存在 False。
        """
        row = await session.get(SysEventDeadLetter, dead_letter_id)
        if row is None:
            return False
        row.status = status
        await session.flush()
        return True

    async def backlog(self, session: DbSession) -> int:
        """待投递积压数。

        Args:
            session: 会话。

        Returns:
            int: 待投递条数。
        """
        statement = select(func.count()).select_from(SysOutbox).where(SysOutbox.status == OUTBOX_STATUS_PENDING)
        return int((await session.execute(statement)).scalar_one())

    async def _by_event_id(self, session: DbSession, event_id: str) -> SysOutbox | None:
        """按事件 ID 取发件箱行。

        Args:
            session: 会话。
            event_id: 事件 ID。

        Returns:
            SysOutbox | None: ORM 行；不存在 None。
        """
        statement = select(SysOutbox).where(SysOutbox.event_id == event_id)
        return (await session.execute(statement)).scalars().first()
