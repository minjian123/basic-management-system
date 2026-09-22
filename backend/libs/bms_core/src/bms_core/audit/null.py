"""audit 能力域缺省实现（Null Object）：占位返回、无副作用。

（02-3 自 `bms_core.audit.hashchain.py` 迁入；05 补审计捕获。）
"""

from collections.abc import Mapping, Sequence

from bms_core.audit.base import AuditCapturer, FieldChange
from bms_core.audit.hashchain import BaseHashChain, ChainVerifyResult, HashChainEntry
from bms_core.core.capability import BaseNullObject
from bms_core.events.base import EventEnvelope

__all__ = [
    "NullAuditCapturer",
    "NullHashChain",
]


class NullAuditCapturer(AuditCapturer, BaseNullObject):
    """占位审计捕获：不判定 / 不落库，返回占位审计事件（不产生真实审计）。"""

    def is_audited(self, table: str) -> bool:
        """判断表是否纳入审计（占位恒不纳入）。

        Args:
            table: 逻辑表名（占位忽略）。

        Returns:
            bool: False。
        """
        return False

    def capture(
        self,
        *,
        table: str,
        model_id: int,
        changes: list[FieldChange],
        actor: int | None = None,
    ) -> EventEnvelope:
        """捕获字段级变更（占位返回空审计事件，不改写库）。

        Args:
            table: 逻辑表名（占位忽略）。
            model_id: 记录主键（占位忽略）。
            changes: 字段变更列表（占位忽略）。
            actor: 操作者 ID（占位忽略）。

        Returns:
            EventEnvelope: 占位审计事件。
        """
        return EventEnvelope(event_type="audit.null")


class NullHashChain(BaseHashChain, BaseNullObject):
    """占位哈希链：固定返回 / 恒定通过（不计算，未接入真实实现时使用）。"""

    def compute(self, prev_hash: str, record: Mapping[str, object]) -> str:
        """恒定返回占位哈希。

        Args:
            prev_hash: 前一条记录哈希（占位忽略）。
            record: 记录内容（占位忽略）。

        Returns:
            str: 占位记录哈希。
        """
        return "null-record-hash"

    def verify(self, entries: Sequence[HashChainEntry]) -> ChainVerifyResult:
        """恒定通过。

        Args:
            entries: 链上记录序列（占位不校验）。

        Returns:
            ChainVerifyResult: `valid=True`、无断裂。
        """
        return ChainVerifyResult(valid=True)
