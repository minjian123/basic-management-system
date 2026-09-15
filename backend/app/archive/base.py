"""归档能力域：归档策略与查询路由契约（真实归档流转随归档管理阶段回补）。

- `ARCHIVE_LOCATIONS`：数据位置清单（`online` 在线库 / `archive` 归档库 `bms_archive`）。
- `ArchiveResult`：归档结果数据契约（frozen）——命中 / 已归档条数。
- `BaseArchivePolicy`：能力域中间层契约（`key = "archive_policy"`）——异步 `matches`（是否达条件）/ `archive`（搬迁）。
- `NullArchivePolicy`：占位实现——恒定不归档（**不搬数据**）。
- `BaseArchiveQueryRouter`：能力域中间层契约（`key = "archive_query_router"`）——同步 `resolve`（查询位置路由）。
- `NullArchiveQueryRouter`：占位实现——恒定在线库。
- 提供者 `get_archive_policy` / `get_archive_query_router`（应用级单例；公共依赖经 `app/api/deps.py` 统一导出）。

口径：归档前链完整性校验取 02-4-11 `BaseHashChain.verify`、冷化 / 归档文件存取取 02-4-1 `BaseObjectStorage`，
均归上层（归档管理阶段）；本域只落归档策略与在线 / 归档位置路由原语。
"""

from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import cast

from fastapi import Request

from app.core.base import BaseObject
from app.core.capability import BaseNullObject
from app.core.plugin import DEFAULT_CONTRACT_VERSION, NULL_PLUGIN_NAME, BasePluggable

__all__ = [
    "ARCHIVE_LOCATIONS",
    "ArchiveResult",
    "BaseArchivePolicy",
    "BaseArchiveQueryRouter",
    "NullArchivePolicy",
    "NullArchiveQueryRouter",
    "get_archive_policy",
    "get_archive_query_router",
]

ARCHIVE_LOCATIONS: tuple[str, ...] = ("online", "archive")
"""数据位置清单（在线库 / 归档库 `bms_archive`）；占位期仅登记不校验。"""


@dataclass(frozen=True)
class ArchiveResult(BaseObject):
    """归档结果。"""

    matched: int
    """命中归档条件的条数。"""

    archived: int
    """实际归档条数。"""

    detail: str | None = None
    """说明（可选）。"""


class BaseArchivePolicy(BasePluggable, ABC):
    """归档策略契约：条件判定 + 归档搬迁。"""

    key: str = "archive_policy"
    plugin_key: str = "archive_policy"
    plugin_name: str = NULL_PLUGIN_NAME
    contract_version: str = DEFAULT_CONTRACT_VERSION

    @abstractmethod
    async def matches(self, record: Mapping[str, object], *, now: datetime | None = None) -> bool:
        """判断记录是否达归档条件。

        Args:
            record: 记录数据。
            now: 当前时间（可注入，便于测试）；None 用系统时间。

        Returns:
            bool: 达归档条件为 True。
        """

    @abstractmethod
    async def archive(self, records: Sequence[Mapping[str, object]]) -> ArchiveResult:
        """执行归档搬迁（真实实现经链校验后迁 `bms_archive`）。

        Args:
            records: 待归档记录。

        Returns:
            ArchiveResult: 归档结果。
        """


class BaseArchiveQueryRouter(BasePluggable, ABC):
    """归档查询路由契约：解析查询位置。"""

    key: str = "archive_query_router"
    plugin_key: str = "archive_query_router"
    plugin_name: str = NULL_PLUGIN_NAME
    contract_version: str = DEFAULT_CONTRACT_VERSION

    @abstractmethod
    def resolve(self, *, table: str) -> str:
        """解析查询位置（在线库 / 归档库）。

        Args:
            table: 逻辑表名。

        Returns:
            str: 位置（取值见 `ARCHIVE_LOCATIONS`）。
        """


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


def get_archive_policy(request: Request) -> BaseArchivePolicy:
    """取应用级归档策略（依赖注入提供者）。

    Args:
        request: 请求对象。

    Returns:
        BaseArchivePolicy: 应用装配的归档策略实例。
    """
    return cast("BaseArchivePolicy", request.app.state.archive_policy)


def get_archive_query_router(request: Request) -> BaseArchiveQueryRouter:
    """取应用级归档查询路由（依赖注入提供者）。

    Args:
        request: 请求对象。

    Returns:
        BaseArchiveQueryRouter: 应用装配的查询路由实例。
    """
    return cast("BaseArchiveQueryRouter", request.app.state.archive_query_router)
