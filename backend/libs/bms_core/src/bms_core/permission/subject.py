"""主体链收敛服务（域 `permission`）。

主体链 = 用户经**任意来源**获得的角色并集：主流程只做「解析器并集去重」，来源增减一律经
`permission/resolver.py` 的注册表登记，**不改主流程**（《02_04 详细设计》§11.2 接缝 1）。

本服务是纯算法件：只调用解析器契约、不做任何数据访问——故可随引擎一并下沉共享基座。
基础版解析器（直接角色 `sys_user_role`、岗位 / 部门链角色 mdm 只读出口）由服务侧装配时构造注入。
"""

from __future__ import annotations

from bms_core.core.concurrent import ConcurrentStableSet
from bms_core.core.objects import BaseFrameworkObject
from bms_core.permission.resolver import BaseRoleResolver, registered_role_resolvers


class PermissionSubjectService(BaseFrameworkObject):
    """主体链收敛服务：按注册顺序执行解析器并做并集去重。"""

    def __init__(self, resolvers: tuple[BaseRoleResolver, ...]) -> None:
        """初始化。

        Args:
            resolvers: 解析器有序元组（装配期经基座注册表取用，便于测试注入）。
        """
        self._resolvers = resolvers

    @classmethod
    def from_registry(cls) -> PermissionSubjectService:
        """按基座注册表构造（装配期缺省路径）。

        Returns:
            PermissionSubjectService: 服务实例。
        """
        return cls(registered_role_resolvers())

    async def resolve_role_ids(self, user_id: int) -> ConcurrentStableSet[int]:
        """收敛用户角色集合（各来源并集去重）。

        Args:
            user_id: 用户主键。

        Returns:
            ConcurrentStableSet[int]: 角色主键集合（插入序稳定）。
        """
        merged: ConcurrentStableSet[int] = ConcurrentStableSet()
        for resolver in self._resolvers:
            resolved = await resolver.resolve(user_id=user_id)
            for role_id in resolved:
                merged.add(role_id)
        return merged
