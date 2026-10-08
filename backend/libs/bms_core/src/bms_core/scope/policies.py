"""数据范围策略注册表（域 `data_scope`）。

数据范围配置（`sys_data_scope.config`）按 `policy_type` 分结构；**核心不判策略类型**——
把 `config` 求值为 `ScopeCondition` 的责任归**策略求值器**（各业务 / 档位登记），
核心只做「查表 + 求值 + 兜底」：

- 未登记的策略 → 调用方按「该条不产生放行（永假）+ 上报」处置（从严，不因策略缺失而放开范围）；
- 四策略（`select` / `region` / `match` / `extension`）由各实现侧登记（见《02_04 详细设计》§5.6）。
"""

from collections.abc import Callable

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.scope.base import ScopeCondition

ScopePolicy = Callable[
    [ConcurrentStableList[ConcurrentStableDict[str, object]]],
    ConcurrentStableList[ScopeCondition],
]
"""策略求值器：`config`（该条规则的 JSON 行）→ 作用域条件列表。"""


_POLICIES: ConcurrentStableDict[str, ScopePolicy] = ConcurrentStableDict()
"""策略求值器注册表（`policy_type` → 求值器；登记顺序即输出顺序）。"""


def register_scope_policy(policy_type: str, policy: ScopePolicy) -> None:
    """登记策略求值器（同 key 覆盖；装配 / 导入期调用）。

    Args:
        policy_type: 策略类型（`select` / `region` / `match` / `extension` 或业务自有）。
        policy: 求值器。
    """
    _POLICIES.set(policy_type, policy)


def scope_policy(policy_type: str) -> ScopePolicy | None:
    """取策略求值器（未登记返回 None）。

    Args:
        policy_type: 策略类型。

    Returns:
        ScopePolicy | None: 求值器；未登记为 None。
    """
    return _POLICIES.get(policy_type)


def registered_scope_policy_types() -> tuple[str, ...]:
    """已登记策略类型清单（保序）。

    Returns:
        tuple[str, ...]: 策略类型元组。
    """
    return tuple(_POLICIES)


def reset_scope_policies() -> None:
    """清空策略求值器注册表（用例隔离用）。"""
    for policy_type in tuple(_POLICIES):
        _POLICIES.delete(policy_type)
