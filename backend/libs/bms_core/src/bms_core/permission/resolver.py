"""角色解析器链（域 `permission`）。

主体链收敛 = **多个解析器的并集去重**：解析器各自回答「该用户经本来源获得哪些角色 id」，
主流程只做并集与去重——来源增减一律经本注册表，**不改主流程**。

基础版（`smb` 档）注册两个解析器（platform 侧实现）：

- 直接角色（`sys_user_role`）；
- 岗位 / 部门链角色（mdm 只读出口 `/api/v1/org/user-roles`，含不可达降级与严格模式）。

后代（`enterprise` / `enterprise_hr`）追加解析器（条件化 / 组织继承 / 人事关系）即接入
（见《02_04 详细设计》§11.2 接缝 1）。
"""

from abc import ABC, abstractmethod

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList, ConcurrentStableSet
from bms_core.core.objects import BaseFrameworkObject

DEFAULT_RESOLVER_ORDER = 100
"""解析器缺省执行次序。"""


class BaseRoleResolver(BaseFrameworkObject, ABC):
    """角色解析器契约（按用户解析其经本来源获得的角色 id）。"""

    key: str = "role_resolver"
    """解析器标识（注册表键）。"""
    order: int = DEFAULT_RESOLVER_ORDER
    """执行次序（小者先；同序按登记序），仅影响执行顺序与排障，不影响并集语义。"""

    @abstractmethod
    async def resolve(self, *, user_id: int) -> ConcurrentStableSet[int]:
        """解析用户角色 id 集合（本来源）。

        实现约定：**失败应抛异常**（不静默吞错），由引擎按档位口径决定降级（如跨服务不可达即
        仅直接角色生效）或严格拒绝。

        Args:
            user_id: 用户主键。

        Returns:
            ConcurrentStableSet[int]: 角色 id 集合（本来源，未去重由主流程统一处理）。
        """


_RESOLVERS: ConcurrentStableDict[str, BaseRoleResolver] = ConcurrentStableDict()
"""解析器注册表（key → 实例；登记顺序用于同序稳定排序）。"""


def register_role_resolver(resolver: BaseRoleResolver) -> None:
    """登记角色解析器（同 key 覆盖；装配期调用）。

    Args:
        resolver: 解析器实例。
    """
    _RESOLVERS.set(resolver.key, resolver)


def registered_role_resolvers() -> tuple[BaseRoleResolver, ...]:
    """已登记解析器（按 `order` 升序、同序保持登记序）。

    Returns:
        tuple[BaseRoleResolver, ...]: 解析器元组（可能为空——空链即「无角色」）。
    """
    collected: ConcurrentStableList[BaseRoleResolver] = ConcurrentStableList()
    for key in _RESOLVERS:
        resolver = _RESOLVERS.get(key)
        if resolver is not None:
            collected.add(resolver)
    return tuple(sorted(collected, key=lambda item: item.order))


def reset_role_resolvers() -> None:
    """清空解析器注册表（用例隔离用）。"""
    for key in tuple(_RESOLVERS):
        _RESOLVERS.delete(key)
