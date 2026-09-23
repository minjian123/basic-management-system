"""消费幂等：`ProcessedEventStore`（消费 + event_id 唯一，与业务副作用同事务）。

- 消费者在**自身业务事务**内先 `mark`：首次返回 `True` 后继续执行业务副作用（同事务提交）；
  重复返回 `False`（已处理，跳过副作用）。
- `mark` 先在事务内查 `sys_event_consumed`（`(consumer, event_id)`）：命中即返回 `False`；
  未命中则登记（`flush`，不提交）——幂等登记与业务副作用在同一本地事务，回滚一并撤销。
- **唯一约束兜底**：并发穿透（同事务内未查得、提交时冲突）由 `(consumer, event_id)` 唯一约束拦截。
"""

from sqlalchemy import select

from bms_core.core.base import BaseObject
from bms_core.db.sync import DbSession
from bms_core.models.outbox import SysEventConsumed

__all__ = ["ProcessedEventStore"]


class ProcessedEventStore(BaseObject):
    """消费幂等存储：会话绑定，`mark` 判定事件是否首次处理。"""

    def __init__(self, session: DbSession) -> None:
        """初始化。

        Args:
            session: 消费者本地事务会话。
        """
        self._session = session

    async def mark(self, *, consumer: str, event_id: str, event_type: str | None = None) -> bool:
        """登记已处理事件（首次占位）。

        Args:
            consumer: 消费者标识（消费组 / 处理者）。
            event_id: 事件 ID。
            event_type: 事件类型（排障用）。

        Returns:
            bool: 首次 True（可继续执行副作用）；重复 False（应跳过）。
        """
        existing = await self._session.execute(
            select(SysEventConsumed.id).where(
                SysEventConsumed.consumer == consumer,
                SysEventConsumed.event_id == event_id,
            )
        )
        if existing.first() is not None:
            return False
        self._session.add(SysEventConsumed(consumer=consumer, event_id=event_id, event_type=event_type))
        await self._session.flush()
        return True
