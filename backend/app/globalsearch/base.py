"""全文检索查询能力域：多域聚合 / 审计日志 / 文件内容三契约（真实 ES 随全文检索阶段回补）。

- 常量：可检索域 `GLOBAL_SEARCH_DOMAINS`、降级原因 `DEGRADE_REASONS`、默认条数 / 页深上限、
  占位降级原因与替代入口常量。
- 数据契约（`BaseSchema`）：`GlobalSearchHit` / `GlobalSearchGroup` / `GlobalSearchResult`（多域分组）、
  `AuditLogHit` / `AuditSearchResult`（审计日志）、`FileContentHit` / `FileContentSearchResult`（文件内容），
  三类结果均含降级字段 `degraded` / `degrade_reason` / `alternative`。
- `BaseGlobalSearch`（`key = "global_search"`）：`domains()`（可检索域 = 权限并集）+ `search`（多域聚合分组）。
- `BaseAuditSearch`（`key = "audit_search"`）：`audit_logs`（时间范围必填、跨月多索引归实现）。
- `BaseFileContentSearch`（`key = "file_content_search"`）：`file_content`（返回文件 ID 与上下文高亮）。
- 提供者 `get_global_search` / `get_audit_search` / `get_file_content_search`（应用级单例；公共依赖经
  `app/api/deps.py` 统一导出）。

口径：可检索域按**权限并集**确定（无权限域不展示 / 不查询）；`tenant_id` 强制隔离 + 动作级数据范围过滤由
**实现**从上下文与权限基座注入，契约方法不显式传租户 / 数据范围参数、**调用方不可绕过**；结果只承载业务标识
与高亮片段（详情回查库，避免双写一致性难题）；引擎不可用 / 超时 / 降级兜底时返回降级字段与替代入口，前端提示
不阻塞页面。真实索引 / 查询 DSL / 跨月路由 / 降级兜底归全文检索阶段上层。
"""

from abc import ABC, abstractmethod
from collections.abc import Sequence
from datetime import datetime
from typing import cast

from fastapi import Request
from pydantic import Field

from app.core.config import Settings
from app.core.plugin import DEFAULT_CONTRACT_VERSION, NULL_PLUGIN_NAME, BasePluggable, resolve_plugin
from app.schemas.base import BaseSchema

__all__ = [
    "DEFAULT_GLOBAL_SEARCH_SIZE",
    "DEGRADE_REASONS",
    "GLOBAL_SEARCH_DOMAINS",
    "GLOBAL_SEARCH_MAX_PAGE",
    "NULL_DEGRADE_REASON",
    "NULL_SEARCH_ALTERNATIVE",
    "AuditLogHit",
    "AuditSearchResult",
    "BaseAuditSearch",
    "BaseFileContentSearch",
    "BaseGlobalSearch",
    "FileContentHit",
    "FileContentSearchResult",
    "GlobalSearchGroup",
    "GlobalSearchHit",
    "GlobalSearchResult",
    "get_audit_search",
    "get_file_content_search",
    "get_global_search",
]

GLOBAL_SEARCH_DOMAINS: tuple[str, ...] = ("user", "dept", "role", "dict", "purchase", "file_meta", "help_article")
"""可检索域（对齐概要设计 33 `doc_type`）；实际可见域 = 权限并集，由实现在 `domains()` 给出。"""

DEGRADE_REASONS: tuple[str, ...] = ("unavailable", "timeout", "fallback")
"""降级原因：不可用 / 超时 / 已降级兜底。"""

NULL_DEGRADE_REASON = "unavailable"
"""占位降级原因（`NullXxx` 固定返回）。"""

NULL_SEARCH_ALTERNATIVE = "db_fuzzy"
"""占位替代入口口径（引擎不可用时降级数据库模糊查询 / 列表页兜底）。"""

DEFAULT_GLOBAL_SEARCH_SIZE = 20
"""默认返回条数。"""

GLOBAL_SEARCH_MAX_PAGE = 100
"""分页限深上限（对齐概要设计 33「limit/offset 限深 ≤ 100 页」）。"""


class GlobalSearchHit(BaseSchema):
    """多域检索命中项（只含业务标识与高亮，详情回查库）。"""

    doc_type: str = Field(description="域标识（user / dept / role / dict / purchase / file_meta / help_article）")
    biz_id: str = Field(description="业务标识（跳转与回查库）")
    title: str = Field(default="", description="命中标题")
    highlight: dict[str, str] = Field(default_factory=dict[str, str], description="高亮片段（字段 → 片段）")
    updated_at: datetime | None = Field(default=None, description="更新时间（UTC）")


class GlobalSearchGroup(BaseSchema):
    """按域分组的检索结果。"""

    doc_type: str = Field(description="域标识")
    hits: list[GlobalSearchHit] = Field(default_factory=list[GlobalSearchHit], description="本域命中")
    total: int = Field(default=0, ge=0, description="本域命中总数")


class GlobalSearchResult(BaseSchema):
    """多域聚合检索结果（含降级字段）。"""

    groups: list[GlobalSearchGroup] = Field(default_factory=list[GlobalSearchGroup], description="按域分组结果")
    total: int = Field(default=0, ge=0, description="命中总数")
    degraded: bool = Field(default=False, description="是否降级")
    degrade_reason: str | None = Field(default=None, description="降级原因（unavailable / timeout / fallback）")
    alternative: str | None = Field(default=None, description="替代入口（降级时的兜底口径）")


class AuditLogHit(BaseSchema):
    """审计日志检索命中项。"""

    log_type: str = Field(description="日志类型（operation / login / open / data_audit）")
    record_id: str = Field(description="日志记录标识")
    title: str = Field(default="", description="命中标题 / 摘要")
    user_id: str | None = Field(default=None, description="操作用户 ID")
    username: str | None = Field(default=None, description="操作用户名")
    highlight: dict[str, str] = Field(default_factory=dict[str, str], description="高亮片段（字段 → 片段）")
    time: datetime | None = Field(default=None, description="发生时间（UTC）")


class AuditSearchResult(BaseSchema):
    """审计日志检索结果（含降级字段）。"""

    hits: list[AuditLogHit] = Field(default_factory=list[AuditLogHit], description="命中项")
    total: int = Field(default=0, ge=0, description="命中总数")
    degraded: bool = Field(default=False, description="是否降级")
    degrade_reason: str | None = Field(default=None, description="降级原因")
    alternative: str | None = Field(default=None, description="替代入口")


class FileContentHit(BaseSchema):
    """文件内容检索命中项。"""

    file_id: str = Field(description="文件标识")
    name: str = Field(default="", description="文件名")
    mime_type: str | None = Field(default=None, description="MIME 类型")
    highlight: dict[str, str] = Field(default_factory=dict[str, str], description="上下文高亮片段")
    updated_at: datetime | None = Field(default=None, description="更新时间（UTC）")


class FileContentSearchResult(BaseSchema):
    """文件内容检索结果（含降级字段）。"""

    hits: list[FileContentHit] = Field(default_factory=list[FileContentHit], description="命中项")
    total: int = Field(default=0, ge=0, description="命中总数")
    degraded: bool = Field(default=False, description="是否降级")
    degrade_reason: str | None = Field(default=None, description="降级原因")
    alternative: str | None = Field(default=None, description="替代入口")


class BaseGlobalSearch(BasePluggable, ABC):
    """多域聚合检索契约：可检索域（权限并集）+ 多域分组检索。"""

    key: str = "global_search"
    plugin_key: str = "global_search"
    plugin_name: str = NULL_PLUGIN_NAME
    contract_version: str = DEFAULT_CONTRACT_VERSION

    @abstractmethod
    async def domains(self) -> Sequence[str]:
        """当前用户可检索域（权限并集；无权限域不返回）。

        Returns:
            Sequence[str]: 可检索域标识（占位空集）。
        """

    @abstractmethod
    async def search(
        self,
        q: str,
        *,
        types: Sequence[str] | None = None,
        page: int = 1,
        size: int = DEFAULT_GLOBAL_SEARCH_SIZE,
    ) -> GlobalSearchResult:
        """多域聚合检索（按域分组 + 高亮；租户隔离与数据范围由实现强制注入）。

        Args:
            q: 检索关键词。
            types: 限定域（None = 全部可检索域）。
            page: 页码（从 1 起）。
            size: 每页条数。

        Returns:
            GlobalSearchResult: 按域分组结果（含降级字段）。
        """


class BaseAuditSearch(BasePluggable, ABC):
    """审计日志检索契约（时间范围必填、跨月多索引归实现）。"""

    key: str = "audit_search"
    plugin_key: str = "audit_search"
    plugin_name: str = NULL_PLUGIN_NAME
    contract_version: str = DEFAULT_CONTRACT_VERSION

    @abstractmethod
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
        """审计日志检索（时间范围必填，单次 ≤ 31 天）。

        Args:
            q: 检索关键词。
            log_type: 日志类型过滤（None = 全部）。
            start_time: 起始时间（必填）。
            end_time: 结束时间（必填）。
            page: 页码（从 1 起）。
            size: 每页条数。

        Returns:
            AuditSearchResult: 审计日志命中（含降级字段）。
        """


class BaseFileContentSearch(BasePluggable, ABC):
    """文件内容检索契约（返回文件 ID 与上下文高亮）。"""

    key: str = "file_content_search"
    plugin_key: str = "file_content_search"
    plugin_name: str = NULL_PLUGIN_NAME
    contract_version: str = DEFAULT_CONTRACT_VERSION

    @abstractmethod
    async def file_content(
        self,
        q: str,
        *,
        file_type: str | None = None,
        page: int = 1,
        size: int = DEFAULT_GLOBAL_SEARCH_SIZE,
    ) -> FileContentSearchResult:
        """文件内容检索（返回文件 ID 与上下文高亮）。

        Args:
            q: 检索关键词。
            file_type: 文件类型过滤（None = 全部）。
            page: 页码（从 1 起）。
            size: 每页条数。

        Returns:
            FileContentSearchResult: 文件命中（含降级字段）。
        """


def get_global_search(request: Request) -> BaseGlobalSearch:
    """取应用级多域聚合检索契约（依赖注入提供者）。

    Args:
        request: 请求对象。

    Returns:
        BaseGlobalSearch: 应用装配的多域检索实例。
    """
    settings = cast("Settings", request.app.state.settings)
    return cast(
        "BaseGlobalSearch",
        resolve_plugin(
            "global_search",
            settings.global_search.provider,
            expected_version=BaseGlobalSearch.contract_version,
        ),
    )


def get_audit_search(request: Request) -> BaseAuditSearch:
    """取应用级审计日志检索契约（依赖注入提供者）。

    Args:
        request: 请求对象。

    Returns:
        BaseAuditSearch: 应用装配的审计日志检索实例。
    """
    settings = cast("Settings", request.app.state.settings)
    return cast(
        "BaseAuditSearch",
        resolve_plugin(
            "audit_search",
            settings.audit_search.provider,
            expected_version=BaseAuditSearch.contract_version,
        ),
    )


def get_file_content_search(request: Request) -> BaseFileContentSearch:
    """取应用级文件内容检索契约（依赖注入提供者）。

    Args:
        request: 请求对象。

    Returns:
        BaseFileContentSearch: 应用装配的文件内容检索实例。
    """
    settings = cast("Settings", request.app.state.settings)
    return cast(
        "BaseFileContentSearch",
        resolve_plugin(
            "file_content_search",
            settings.file_content_search.provider,
            expected_version=BaseFileContentSearch.contract_version,
        ),
    )
