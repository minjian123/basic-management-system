"""audit 能力域缺省实现（Null Object）：占位返回、无副作用（02-3 自 app.audit.hashchain.py 迁入）。"""

from collections.abc import Mapping, Sequence

from app.audit.hashchain import BaseHashChain, ChainVerifyResult, HashChainEntry
from app.core.capability import BaseNullObject

__all__ = [
    "NullHashChain",
]


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
