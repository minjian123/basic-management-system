"""审计能力域：ORM 字段级变更捕获基座契约（哈希链在阶段六回补）。"""

from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.core.base import BaseObject
from app.events.base import EventEnvelope


@dataclass
class FieldChange(BaseObject):
    """字段级变更：字段名 + 旧值 / 新值。"""

    field: str
    old: object = None
    new: object = None


class AuditCapturer(BaseObject, ABC):
    """审计捕获基座契约：关键表字段级变更 → 审计事件。"""

    @abstractmethod
    def is_audited(self, table: str) -> bool:
        """判断表是否纳入审计。

        Args:
            table: 逻辑表名。

        Returns:
            bool: 纳入为 True。
        """

    @abstractmethod
    def capture(
        self,
        *,
        table: str,
        model_id: int,
        changes: list[FieldChange],
        actor: int | None = None,
    ) -> EventEnvelope:
        """捕获字段级变更并生成审计事件。

        Args:
            table: 逻辑表名。
            model_id: 记录主键。
            changes: 字段变更列表。
            actor: 操作者 ID。

        Returns:
            EventEnvelope: 审计事件信封。
        """
