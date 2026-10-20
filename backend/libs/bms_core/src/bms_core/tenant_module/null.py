"""租户模块门禁缺省实现（Null Object）：全部放行（未接入真实实现时使用）。"""

from bms_core.core.capability import BaseNullObject
from bms_core.tenant_module.base import TENANT_MODULE_STATE_ENABLED, BaseTenantModuleGate

__all__ = ["NullTenantModuleGate"]


class NullTenantModuleGate(BaseTenantModuleGate, BaseNullObject):
    """占位门禁：任何模块均视为已开通（不做拦截）。"""

    async def state(self, *, tenant_id: int, tenant_code: str | None, module_key: str) -> str:
        """恒定已开通（占位不取数）。

        Args:
            tenant_id: 租户主键（占位不区分）。
            tenant_code: 租户编码（占位不区分）。
            module_key: 模块标识（占位不区分）。

        Returns:
            str: `enabled`。
        """
        return TENANT_MODULE_STATE_ENABLED
