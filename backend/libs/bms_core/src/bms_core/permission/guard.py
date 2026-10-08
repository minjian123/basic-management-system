"""权限校验链（guard，域 `permission`）。

`check(code)` 的判定分两段：

1. **基础判定**（引擎内建）：快照 `tier` 豁免 → 业务码 / 动作码命中；
2. **校验链**（本模块）：逐个 guard 的 `allow(ctx)` **全通过**才放行——基础版为**空链**（恒通过）。

后代（`enterprise` / `enterprise_hr`）追加「业务条件 / 人事关系」等 guard 即接入，
**校验入口签名（基座 `BasePermissionChecker.check`）不变**（见《02_04 详细设计》§11.2 接缝 3）。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.objects import BaseDataContract, BaseFrameworkObject
from bms_core.permission.snapshot import PermissionSnapshot

DEFAULT_GUARD_ORDER = 100
"""校验链环节缺省次序。"""


@dataclass
class PermissionGuardContext(BaseDataContract):
    """校验上下文（guard 输入：权限码 + 请求态 + 快照）。"""

    code: str
    """待校验权限码（业务码或 `业务:动作`）。"""
    user_id: int | None = None
    """请求用户主键（未登录 / 服务身份为 None）。"""
    tenant_id: str | None = None
    """租户标识。"""
    snapshot: PermissionSnapshot | None = None
    """当前用户权限快照（未计算为 None）。"""


class BasePermissionGuard(BaseFrameworkObject, ABC):
    """校验链环节契约（在码集命中基础上追加条件判定）。"""

    key: str = "permission_guard"
    """环节标识（注册表键）。"""
    order: int = DEFAULT_GUARD_ORDER
    """执行次序（小者先；同序按登记序）。"""

    @abstractmethod
    def allow(self, context: PermissionGuardContext) -> bool:
        """是否放行（返回 False 即拒，从严）。

        Args:
            context: 校验上下文。

        Returns:
            bool: 放行为 True。
        """


_GUARDS: ConcurrentStableDict[str, BasePermissionGuard] = ConcurrentStableDict()
"""校验链注册表（key → 实例；登记顺序用于同序稳定排序）。"""


def register_permission_guard(guard: BasePermissionGuard) -> None:
    """登记校验链环节（同 key 覆盖；装配期调用）。

    Args:
        guard: 环节实例。
    """
    _GUARDS.set(guard.key, guard)


def registered_permission_guards() -> tuple[BasePermissionGuard, ...]:
    """已登记校验链环节（按 `order` 升序、同序保持登记序）。

    Returns:
        tuple[BasePermissionGuard, ...]: 环节元组（基础版为空链）。
    """
    collected: ConcurrentStableList[BasePermissionGuard] = ConcurrentStableList()
    for key in _GUARDS:
        guard = _GUARDS.get(key)
        if guard is not None:
            collected.add(guard)
    return tuple(sorted(collected, key=lambda item: item.order))


def guards_allow(context: PermissionGuardContext) -> bool:
    """逐个环节判定（空链恒通过）。

    Args:
        context: 校验上下文。

    Returns:
        bool: 全通过为 True。
    """
    return all(guard.allow(context) for guard in registered_permission_guards())


def reset_permission_guards() -> None:
    """清空校验链注册表（用例隔离用）。"""
    for key in tuple(_GUARDS):
        _GUARDS.delete(key)
