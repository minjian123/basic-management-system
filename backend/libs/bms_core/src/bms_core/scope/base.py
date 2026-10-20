"""数据范围能力域：数据范围注入基座契约（规则由 RBAC 提供，阶段五回补）。

**条件的两类维度**（`04-4` 口径收口）：

- **实体列维度**：`field` 直接是消费方实体列名（软删 / 租户 / `extension` 自有条件）；
- **数据源维度**：`data_source_key` 非空——条件描述的是「某个数据源上的可见集合」，`field` 留空
  （`match` 仍带白名单字段）；消费方按自身声明的「数据源 → 实体列」映射翻译成列条件。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass

from bms_core.core.concurrent import ConcurrentStableDict
from bms_core.core.objects import BaseFieldRuleContract
from bms_core.core.plugin import DEFAULT_CONTRACT_VERSION, NULL_PLUGIN_NAME, BasePluggable

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
class ScopeCondition(BaseFieldRuleContract):
    """作用域过滤条件：字段 + 操作符 + 值（跨实现统一表示）。

    内存基线按操作符过滤；DB 实现把条件拼入 WHERE。

    `data_source_key` 非空表示**数据源维度条件**（`select` / `region` 的 `field` 为空、`match`
    带白名单字段）：消费方按自身声明的「数据源 → 实体列」映射翻译，未声明即该条件不产生放行。
    """

    field: str
    operator: str = "eq"
    value: object = None
    data_source_key: str | None = None


DENY_ALL_CONDITION = ScopeCondition("id", "in", [])
"""永假条件（「该条不产生放行」的载体：`id ∈ ∅`）。"""


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
    def allow_write(
        self,
        values: ConcurrentStableDict[str, object],
        *,
        scope_columns: ConcurrentStableDict[str, str] | None = None,
    ) -> bool:
        """写校验：数据是否落在授权范围内。

        Args:
            values: 待写入字段值（实体列名 → 值）。
            scope_columns: 数据源标识 → 实体列名（写入口自身声明；数据源维度条件靠它落到列，
                None 表示未声明——此时数据源维度条件一律按「不产生放行」处置，从严不越权）。

        Returns:
            bool: 允许为 True。
        """
