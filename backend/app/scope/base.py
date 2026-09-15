"""数据范围能力域：数据范围注入基座契约（规则由 RBAC 提供，阶段五回补）。"""

from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.core.base import BaseObject
from app.core.plugin import DEFAULT_CONTRACT_VERSION, NULL_PLUGIN_NAME, BasePluggable

SCOPE_OPERATORS: tuple[str, ...] = (
    "eq",
    "ne",
    "in",
    "like",
    "gt",
    "gte",
    "lt",
    "lte",
    "between",
    "is_null",
    "is_not_null",
)


@dataclass(frozen=True)
class ScopeCondition(BaseObject):
    """作用域过滤条件：字段 + 操作符 + 值（跨实现统一表示）。

    内存基线按操作符过滤；DB 实现回补时拼 WHERE。
    """

    field: str
    operator: str = "eq"
    value: object = None


class DataScope(BasePluggable, ABC):
    """数据范围契约：读过滤条件 + 写校验（写读双向）。"""

    key: str = "data_scope"
    plugin_key: str = "data_scope"
    plugin_name: str = NULL_PLUGIN_NAME
    contract_version: str = DEFAULT_CONTRACT_VERSION

    @abstractmethod
    def read_predicate(self) -> object:
        """读过滤条件（`ScopeCondition` 或条件列表；None 表示不过滤）。"""

    @abstractmethod
    def allow_write(self, values: dict[str, object]) -> bool:
        """写校验：数据是否落在授权范围内。

        Args:
            values: 待写入字段值。

        Returns:
            bool: 允许为 True。
        """
