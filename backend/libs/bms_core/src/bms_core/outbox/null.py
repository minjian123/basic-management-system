"""outbox 能力域缺省实现（Null Object）：无副作用（未配置真实存储 / 投递器时使用）。"""

from datetime import datetime

from bms_core.core.capability import BaseNullObject
from bms_core.db.sync import DbSession
from bms_core.events.base import EventEnvelope
from bms_core.outbox.base import (
    BaseOutboxDispatcher,
    BaseOutboxStore,
    DeadLetterRecord,
    DispatchResult,
    OutboxRecord,
)

__all__ = ["NullOutboxDispatcher", "NullOutboxStore"]


class NullOutboxStore(BaseOutboxStore, BaseNullObject):
    """占位发件箱存储：不落库、恒定无待投递 / 无死信。"""

    async def enqueue(self, session: DbSession, event: EventEnvelope) -> str:
        """占位写入（不落库，回显事件 ID）。

        Args:
            session: 会话（占位忽略）。
            event: 事件信封。

        Returns:
            str: 事件 ID（缺省空串）。
        """
        return event.event_id or ""

    async def claim_pending(self, session: DbSession, *, now: datetime, limit: int) -> list[OutboxRecord]:
        """占位取待投递（恒定空集）。

        Args:
            session: 会话（占位忽略）。
            now: 当前时间（占位忽略）。
            limit: 上限（占位忽略）。

        Returns:
            list[OutboxRecord]: 空列表。
        """
        return []

    async def mark_delivered(self, session: DbSession, event_id: str) -> None:
        """占位标记已投递（空操作）。

        Args:
            session: 会话（占位忽略）。
            event_id: 事件 ID（占位忽略）。
        """

    async def mark_failed(
        self, session: DbSession, event_id: str, error: str, *, max_retries: int, backoff: float
    ) -> bool:
        """占位标记失败（恒定未转死信）。

        Args:
            session: 会话（占位忽略）。
            event_id: 事件 ID（占位忽略）。
            error: 失败原因（占位忽略）。
            max_retries: 最大重试次数（占位忽略）。
            backoff: 退避基数（占位忽略）。

        Returns:
            bool: False。
        """
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
        """占位重放（恒定 0 条）。

        Args:
            session: 会话（占位忽略）。
            event_id: 事件 ID 筛选（占位忽略）。
            event_type: 类型筛选（占位忽略）。
            aggregate_key: 聚合键筛选（占位忽略）。
            since: 时间下限（占位忽略）。
            limit: 上限（占位忽略）。

        Returns:
            int: 0。
        """
        return 0

    async def list_dead_letters(
        self,
        session: DbSession,
        *,
        status: str | None = None,
        source: str | None = None,
        offset: int = 0,
        limit: int = 20,
    ) -> tuple[list[DeadLetterRecord], int]:
        """占位死信列表（恒定空集）。

        Args:
            session: 会话（占位忽略）。
            status: 状态筛选（占位忽略）。
            source: 来源筛选（占位忽略）。
            offset: 偏移（占位忽略）。
            limit: 上限（占位忽略）。

        Returns:
            tuple[list[DeadLetterRecord], int]: （空列表，0）。
        """
        return [], 0

    async def get_dead_letter(self, session: DbSession, dead_letter_id: int) -> DeadLetterRecord | None:
        """占位取死信（恒定 None）。

        Args:
            session: 会话（占位忽略）。
            dead_letter_id: 死信主键（占位忽略）。

        Returns:
            DeadLetterRecord | None: None。
        """
        return None

    async def set_dead_letter_status(self, session: DbSession, dead_letter_id: int, status: str) -> bool:
        """占位设置死信状态（恒定未命中）。

        Args:
            session: 会话（占位忽略）。
            dead_letter_id: 死信主键（占位忽略）。
            status: 目标状态（占位忽略）。

        Returns:
            bool: False。
        """
        return False

    async def backlog(self, session: DbSession) -> int:
        """占位积压（恒定 0）。

        Args:
            session: 会话（占位忽略）。

        Returns:
            int: 0。
        """
        return 0


class NullOutboxDispatcher(BaseOutboxDispatcher, BaseNullObject):
    """占位投递器：不轮询、不投递。"""

    @property
    def enabled(self) -> bool:
        """后台轮询开关（占位恒定 False）。

        Returns:
            bool: False。
        """
        return False

    async def dispatch_once(self, *, db_key: str) -> DispatchResult:
        """占位单库投递（恒定空结果）。

        Args:
            db_key: 数据源键（占位忽略）。

        Returns:
            DispatchResult: 空结果。
        """
        return DispatchResult()

    async def dispatch_due(self) -> DispatchResult:
        """占位多库投递（恒定空结果）。

        Returns:
            DispatchResult: 空结果。
        """
        return DispatchResult()

    async def setup(self) -> None:
        """占位启动（空操作）。"""

    async def aclose(self) -> None:
        """占位释放（空操作）。"""
