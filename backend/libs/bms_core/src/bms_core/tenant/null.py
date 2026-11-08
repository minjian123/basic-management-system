"""tenant 能力域缺省实现（Null Object）。

- `tenant_self_service`：固定返回单租户，不落库、不签发令牌、不读租户配置；
- `tenant_guard`：**调用即 `ConfigError`**（fail-closed）——守卫未启用时宁可报错，也不静默放行。
"""

from bms_core.core.capability import BaseNullObject
from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.exceptions import ConfigError
from bms_core.core.logging import get_logger
from bms_core.db.tenant import DEMO_TENANT, TenantContext
from bms_core.tenant.base import (
    TENANT_SWITCH_MODES,
    BaseTenantSelfService,
    TenantBrand,
    TenantSelfOverview,
    TenantSummary,
    TenantSwitchResult,
    build_tenant_db_key,
)
from bms_core.tenant.guard import BaseTenantGuard, TenantTarget
from bms_core.tenant.lifecycle import BaseTenantResourceHandler, TenantLifecycleContext

__all__ = ["NullTenantGuard", "NullTenantResourceHandler", "NullTenantSelfService"]


class NullTenantSelfService(BaseTenantSelfService, BaseNullObject):
    """占位租户自助服务：我的租户固定单租户、切换恒定回显、品牌固定平台默认（零副作用）。"""

    async def my_tenants(
        self,
        *,
        current_code: str | None = None,
        tenant_id: int | None = None,
        user_id: int | None = None,
    ) -> TenantSelfOverview:
        """取「我加入的租户」概览（占位固定单租户）。

        Args:
            current_code: 当前租户编码（占位忽略，固定为演示租户）。
            tenant_id: 当前租户主键（占位忽略）。
            user_id: 当前登录用户主键（占位忽略）。

        Returns:
            TenantSelfOverview: 仅含演示租户的概览（非多租户）。
        """
        return TenantSelfOverview(
            tenants=ConcurrentStableList(
                [
                    TenantSummary(
                        id=DEMO_TENANT.code,
                        name=DEMO_TENANT.name,
                        code=DEMO_TENANT.code,
                    )
                ]
            ),
            current_code=DEMO_TENANT.code,
            multi_tenant=False,
        )

    async def switch(
        self, code: str, *, tenant_id: int | None = None, user_id: int | None = None
    ) -> TenantSwitchResult:
        """切换到目标租户（占位恒定回显、不校验存在性、不改会话 / 令牌）。

        Args:
            code: 目标租户编码（原样回显）。
            tenant_id: 当前租户主键（占位忽略）。
            user_id: 当前登录用户主键（占位忽略）。

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


class NullTenantGuard(BaseTenantGuard, BaseNullObject):
    """占位守卫：任何校验调用即 `ConfigError`（fail-closed，不放行、不静默）。

    插件装配对每条接线无条件解析 `provider or null`，占位实现必然存在；若照抄模块门禁的恒放行，
    「provider 写错 / 留空」就会让异步路径全部放行——与本能力域「不静默放行」的口径相反。
    """

    async def resolve(self, target: TenantTarget, *, readonly: bool = False) -> TenantContext:
        """拒绝校验（占位不取数、不放行；只读通道同样拒绝——未启用就无从判定状态）。

        Args:
            target: 租户定位（仅用于错误消息）。
            readonly: 只读通道（占位实现不区分：一律 `ConfigError`，fail-closed）。

        Returns:
            TenantContext: 不返回（恒定抛错）。

        Raises:
            ConfigError: 守卫未启用（恒定）。
        """
        raise ConfigError(
            '租户可用性守卫未启用：请设置 [tenant_guard].provider = "source"（或产品实现的登记名）；'
            f"拒绝校验租户 {target.label}"
        )


_LOGGER = get_logger("bms.tenant_resources")


class NullTenantResourceHandler(BaseTenantResourceHandler, BaseNullObject):
    """占位实现：四动作 no-op，账本为进程内字典（开发期 / 用例专用）。

    生产装配必须显式选产品实现——占位不动资源，删除事件会被「处理成功」而不清理，
    因此每次动作记一条 WARNING（`tenant_resource_action_skipped`）便于发现漏配。
    """

    def __init__(self) -> None:
        """初始化进程内账本。"""
        self._applied: ConcurrentStableDict[tuple[int, str], int] = ConcurrentStableDict()

    async def applied_version(self, *, tenant_id: int, action: str) -> int:
        """读取进程内账本。

        Args:
            tenant_id: 租户主键。
            action: 动作名。

        Returns:
            int: 已处理版本；无记录 `-1`。
        """
        return self._applied.get((tenant_id, action), -1)

    async def mark_applied(self, *, tenant_id: int, action: str, version: int) -> None:
        """写入进程内账本。

        Args:
            tenant_id: 租户主键。
            action: 动作名。
            version: 已处理版本。
        """
        self._applied.set((tenant_id, action), int(version))

    async def on_created(self, context: TenantLifecycleContext) -> None:
        """占位：记录漏配告警。

        Args:
            context: 生命周期上下文。
        """
        self._warn(context)

    async def on_suspended(self, context: TenantLifecycleContext) -> None:
        """占位：记录漏配告警。

        Args:
            context: 生命周期上下文。
        """
        self._warn(context)

    async def on_activated(self, context: TenantLifecycleContext) -> None:
        """占位：记录漏配告警。

        Args:
            context: 生命周期上下文。
        """
        self._warn(context)

    async def on_deleted(self, context: TenantLifecycleContext) -> None:
        """占位：记录漏配告警（资源未清理）。

        Args:
            context: 生命周期上下文。
        """
        self._warn(context)

    def _warn(self, context: TenantLifecycleContext) -> None:
        """记录「未配置产品资源实现」告警。

        Args:
            context: 生命周期上下文。
        """
        _LOGGER.warning(
            "tenant_resource_action_skipped",
            tenant_id=context.tenant_id,
            action=context.action,
            version=context.version,
            detail="tenant_resources 配置为占位实现，资源动作未执行",
        )
