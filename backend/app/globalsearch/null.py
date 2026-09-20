"""globalsearch 能力域缺省实现（Null Object）：空结果 + 降级标记，不连 ES。"""

from collections.abc import Sequence
from datetime import datetime

from app.core.capability import BaseNullObject
from app.globalsearch.base import (
    DEFAULT_GLOBAL_SEARCH_SIZE,
    NULL_DEGRADE_REASON,
    NULL_SEARCH_ALTERNATIVE,
    AuditSearchResult,
    BaseAuditSearch,
    BaseFileContentSearch,
    BaseGlobalSearch,
    FileContentSearchResult,
    GlobalSearchResult,
)

__all__ = [
    "NullAuditSearch",
    "NullFileContentSearch",
    "NullGlobalSearch",
]


class NullGlobalSearch(BaseGlobalSearch, BaseNullObject):
    """占位多域聚合检索：固定空分组结果 + 降级标记（不连 ES）。"""

    async def domains(self) -> Sequence[str]:
        """当前用户可检索域（占位恒空）。

        Returns:
            Sequence[str]: 空元组。
        """
        return ()

    async def search(
        self,
        q: str,
        *,
        types: Sequence[str] | None = None,
        page: int = 1,
        size: int = DEFAULT_GLOBAL_SEARCH_SIZE,
    ) -> GlobalSearchResult:
        """多域聚合检索（占位空结果 + 降级标记）。

        Args:
            q: 检索关键词（占位忽略）。
            types: 限定域（占位忽略）。
            page: 页码（占位忽略）。
            size: 每页条数（占位忽略）。

        Returns:
            GlobalSearchResult: 空分组 + `degraded=True`。
        """
        del q, types, page, size
        return GlobalSearchResult(
            groups=[],
            total=0,
            degraded=True,
            degrade_reason=NULL_DEGRADE_REASON,
            alternative=NULL_SEARCH_ALTERNATIVE,
        )


class NullAuditSearch(BaseAuditSearch, BaseNullObject):
    """占位审计日志检索：固定空结果 + 降级标记（不连 ES）。"""

    async def audit_logs(
        self,
        q: str,
        *,
        log_type: str | None = None,
        start_time: datetime,
        end_time: datetime,
        page: int = 1,
        size: int = DEFAULT_GLOBAL_SEARCH_SIZE,
    ) -> AuditSearchResult:
        """审计日志检索（占位空结果 + 降级标记）。

        Args:
            q: 检索关键词（占位忽略）。
            log_type: 日志类型过滤（占位忽略）。
            start_time: 起始时间（占位忽略）。
            end_time: 结束时间（占位忽略）。
            page: 页码（占位忽略）。
            size: 每页条数（占位忽略）。

        Returns:
            AuditSearchResult: 空结果 + `degraded=True`。
        """
        del q, log_type, start_time, end_time, page, size
        return AuditSearchResult(
            hits=[],
            total=0,
            degraded=True,
            degrade_reason=NULL_DEGRADE_REASON,
            alternative=NULL_SEARCH_ALTERNATIVE,
        )


class NullFileContentSearch(BaseFileContentSearch, BaseNullObject):
    """占位文件内容检索：固定空结果 + 降级标记（不连 ES）。"""

    async def file_content(
        self,
        q: str,
        *,
        file_type: str | None = None,
        page: int = 1,
        size: int = DEFAULT_GLOBAL_SEARCH_SIZE,
    ) -> FileContentSearchResult:
        """文件内容检索（占位空结果 + 降级标记）。

        Args:
            q: 检索关键词（占位忽略）。
            file_type: 文件类型过滤（占位忽略）。
            page: 页码（占位忽略）。
            size: 每页条数（占位忽略）。

        Returns:
            FileContentSearchResult: 空结果 + `degraded=True`。
        """
        del q, file_type, page, size
        return FileContentSearchResult(
            hits=[],
            total=0,
            degraded=True,
            degrade_reason=NULL_DEGRADE_REASON,
            alternative=NULL_SEARCH_ALTERNATIVE,
        )
