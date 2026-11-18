"""角色层级命中规则：角色类型优先级 + 「取首个非空候选」（多角色视图共用，11_01 上移）。

**为什么单独成模块**：表单定制（10_01 角色视图）与首页工作台（11_01 角色模板）都要回答同一个问题
——「用户命中多个角色时，用哪一个角色的配置」。规则只能有一处定义，否则两套实现必然漂移；
本模块只依赖并发集合与纯函数，不含 IO 与框架类型。

口径（10_01 决策 5，11_01 沿用）：

- 优先级按角色类型固定序：`platform_admin` > `system` > `security` > `audit` > `custom`，
  未登记类型排在最后；
- 同类型按角色主键升序；
- 只取**非空**候选（空配置视为未命中，继续看下一个角色）。
"""

from collections.abc import Callable

from bms_core.core.concurrent import ConcurrentStableList

__all__ = ["ROLE_TYPE_PRIORITY", "pick_role_candidate", "role_rank"]

ROLE_TYPE_PRIORITY: ConcurrentStableList[str] = ConcurrentStableList(
    (
        "platform_admin",
        "system",
        "security",
        "audit",
        "custom",
    )
)
"""角色类型命中优先级（`sys_role` 无 `sort` 列，按内置类型 + 角色主键升序）。"""


def role_rank(role_type: str) -> int:
    """取角色类型的排序秩（越小越优先）。

    Args:
        role_type: 角色类型（`platform_admin` / `system` / `security` / `audit` / `custom`）。

    Returns:
        int: 排序秩；未登记类型返回优先级清单长度（排最后）。
    """
    return ROLE_TYPE_PRIORITY.index(role_type) if role_type in ROLE_TYPE_PRIORITY else len(ROLE_TYPE_PRIORITY)


def pick_role_candidate[PayloadT](
    candidates: ConcurrentStableList[tuple[str, int, PayloadT | None]],
    *,
    is_empty: Callable[[PayloadT], bool] | None = None,
) -> tuple[int | None, PayloadT | None]:
    """按角色类型优先级 + 角色主键升序，取首个非空候选。

    Args:
        candidates: 候选清单（`(role_type, role_id, payload)`；payload 为 None 表示该角色无配置）。
        is_empty: 空配置判定（None 表示只跳过 `None`；否则返回 True 的配置视为未命中）。

    Returns:
        tuple[int | None, PayloadT | None]: （选中角色主键, 配置）；无命中返回 `(None, None)`。
    """
    ordered: ConcurrentStableList[tuple[int, int, PayloadT | None]] = ConcurrentStableList()
    for role_type, role_id, payload in candidates:
        ordered.add((role_rank(role_type), role_id, payload))
    for _rank, role_id, payload in sorted(ordered, key=lambda item: (item[0], item[1])):
        if payload is None:
            continue
        if is_empty is not None and is_empty(payload):
            continue
        return role_id, payload
    return None, None
