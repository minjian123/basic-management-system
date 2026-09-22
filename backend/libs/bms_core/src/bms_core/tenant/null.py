"""tenant_self_service 能力域缺省实现（Null Object）：固定返回单租户，不落库、不签发令牌、不读租户配置。"""

from bms_core.core.capability import BaseNullObject
from bms_core.db.tenant import DEMO_TENANT
from bms_core.tenant.base import (
    TENANT_SWITCH_MODES,
    BaseTenantSelfService,
    TenantBrand,
    TenantSelfOverview,
    TenantSummary,
    TenantSwitchResult,
    build_tenant_db_key,
)

__all__ = ["NullTenantSelfService"]


class NullTenantSelfService(BaseTenantSelfService, BaseNullObject):
    """占位租户自助服务：我的租户固定单租户、切换恒定回显、品牌固定平台默认（零副作用）。"""

    async def my_tenants(self, *, current_code: str | None = None) -> TenantSelfOverview:
        """取「我加入的租户」概览（占位固定单租户）。

        Args:
            current_code: 当前租户编码（占位忽略，固定为演示租户）。

        Returns:
            TenantSelfOverview: 仅含演示租户的概览（非多租户）。
        """
        return TenantSelfOverview(
            tenants=[
                TenantSummary(
                    id=DEMO_TENANT.tenant_code,
                    name=DEMO_TENANT.name,
                    code=DEMO_TENANT.tenant_code,
                )
            ],
            current_code=DEMO_TENANT.tenant_code,
            multi_tenant=False,
        )

    async def switch(self, code: str) -> TenantSwitchResult:
        """切换到目标租户（占位恒定回显、不校验存在性、不改会话 / 令牌）。

        Args:
            code: 目标租户编码（原样回显）。

        Returns:
            TenantSwitchResult: 占位切换结果（`applied` 为真、不重发令牌、无令牌）。
        """
        return TenantSwitchResult(
            tenant_code=code,
            db_key=build_tenant_db_key(code),
            applied=True,
            mode=TENANT_SWITCH_MODES[0],
            reissue_token=False,
            token=None,
        )

    async def brand(self, *, code: str | None = None) -> TenantBrand:
        """取品牌信息（占位固定返回平台默认品牌，不区分租户编码）。

        Args:
            code: 租户编码（占位忽略）。

        Returns:
            TenantBrand: 平台默认品牌（主色 / 模式 / 开关取默认，标识类字段留空）。
        """
        return TenantBrand(name=DEMO_TENANT.name)
