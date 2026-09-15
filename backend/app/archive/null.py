"""archive 能力域缺省实现（Null Object）：占位返回、无副作用（02-3 自 app.archive.base.py 迁入）。"""

from collections.abc import Mapping, Sequence
from datetime import datetime

from app.archive.base import ArchiveResult, BaseArchivePolicy, BaseArchiveQueryRouter
from app.core.capability import BaseNullObject

__all__ = [
    "NullArchivePolicy",
    "NullArchiveQueryRouter",
]


class NullArchivePolicy(BaseArchivePolicy, BaseNullObject):
    """占位归档策略：恒定不归档（不搬数据，未接入真实实现时使用）。"""

    async def matches(self, record: Mapping[str, object], *, now: datetime | None = None) -> bool:
        """恒定不归档。

        Args:
            record: 记录数据（占位忽略）。
            now: 当前时间（占位忽略）。

        Returns:
            bool: False。
        """
        return False

    async def archive(self, records: Sequence[Mapping[str, object]]) -> ArchiveResult:
        """返回空归档结果（不搬迁）。

        Args:
            records: 待归档记录（占位忽略）。

        Returns:
            ArchiveResult: 空结果（命中 0 / 归档 0）。
        """
        return ArchiveResult(matched=0, archived=0)


class NullArchiveQueryRouter(BaseArchiveQueryRouter, BaseNullObject):
    """占位查询路由：恒定返回在线库（不路由归档库）。"""

    def resolve(self, *, table: str) -> str:
        """恒定在线库。

        Args:
            table: 逻辑表名（占位忽略）。

        Returns:
            str: `"online"`。
        """
        return "online"
