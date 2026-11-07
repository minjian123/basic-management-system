"""resource_scope 能力域缺省实现（Null Object）。

`scope_resolver`：**调用即 `ConfigError`**（fail-closed）——作用域解析未启用时宁可报错，
也不静默放行；占位恒放行会让「provider 写错 / 留空」变成「作用域校验全放行」，
与 `NullTenantGuard` 同口径（07D `01_2`）。
"""

from bms_core.core.capability import BaseNullObject
from bms_core.core.exceptions import ConfigError
from bms_core.resource_scope.resolver import BaseScopeResolver, ResolvedScope
from bms_core.tenant.guard import TenantTarget

__all__ = ["NullScopeResolver"]


class NullScopeResolver(BaseScopeResolver, BaseNullObject):
    """占位解析器：任何解析调用即 `ConfigError`（不放行、不静默）。"""

    async def resolve(
        self,
        target: TenantTarget | None = None,
        *,
        module_key: str,
        resource_type: str | None = None,
        resource_key: str | None = None,
        owner_tenant_id: int | None = None,
    ) -> ResolvedScope:
        """拒绝解析（占位不判定、不放行）。

        Args:
            target: 租户定位（仅用于错误消息）。
            module_key: 模块注册键（仅用于错误消息）。
            resource_type: 资源类型标识（仅用于错误消息）。
            resource_key: 资源标识（仅用于错误消息）。
            owner_tenant_id: 资源归属租户（仅用于错误消息）。

        Returns:
            ResolvedScope: 不返回（恒定抛错）。

        Raises:
            ConfigError: 作用域解析未启用（恒定）。
        """
        raise ConfigError(
            "作用域解析未启用（scope_resolver 配置为占位实现）："
            f"module_key={module_key} resource_type={resource_type} resource_key={resource_key} "
            f"owner_tenant_id={owner_tenant_id} tenant={getattr(target, 'label', None)}"
        )
