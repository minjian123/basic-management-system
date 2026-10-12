"""角色解析器注册表用例（`bms_core/permission/resolver.py`）：登记 / 按 `order` 取用 / 清空。"""

from __future__ import annotations

from typing import Any, cast

from bms_core.core.concurrent import ConcurrentStableSet
from bms_core.permission import resolver as resolver_module
from bms_core.permission.resolver import (
    BaseRoleResolver,
    register_role_resolver,
    registered_role_resolvers,
    reset_role_resolvers,
)


class _Resolver(BaseRoleResolver):
    """角色解析器替身（按 `order` 排序取用）。"""

    def __init__(self, key: str, order: int) -> None:
        """初始化。

        Args:
            key: 解析器标识。
            order: 排序位。
        """
        self.key = key
        self.order = order

    async def resolve(self, *, user_id: int) -> ConcurrentStableSet[int]:
        """返回空角色集合。

        Args:
            user_id: 用户主键（忽略）。

        Returns:
            ConcurrentStableSet[int]: 空集合。
        """
        del user_id
        return ConcurrentStableSet()


def test_resolver_registry_orders_and_resets() -> None:
    """登记两个解析器：按 `order` 升序取用；清空后为空链。"""
    reset_role_resolvers()
    register_role_resolver(_Resolver("late", 20))
    register_role_resolver(_Resolver("early", 10))
    assert [resolver.key for resolver in registered_role_resolvers()] == ["early", "late"]

    # 防御分支：注册表内出现空值时跳过（不经公开登记通道）。
    resolver_module._RESOLVERS.set("ghost", cast("Any", None))  # pyright: ignore[reportPrivateUsage]
    assert [resolver.key for resolver in registered_role_resolvers()] == ["early", "late"]

    reset_role_resolvers()
    assert registered_role_resolvers() == ()
