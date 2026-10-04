"""租户自助真实实现：`my_tenants` / `switch` 经关系数据源 + 租户源取数（11_01）。

- 取数：关系数据源（`app.state.tenant_membership`）→ 可访问目标租户集合；租户源
  （`app.state.tenant_source`）→ 目标租户元信息（编码 / 名称 / 库键）。
- 越权校验：`switch` 的目标租户必须 ∈ 当前用户可访问集合，否则 `TenantAccessDeniedError`（80003 / 403）。
- 读路径自愈：`my_tenants` 在「自有租户行不存在（无行或已软删）」时幂等补建自有关系
  （来源 `self_heal`）；专属行已存在（含 `disabled`）则不自愈——回收优先。
- 品牌：本任务不做品牌取数（维持平台默认；品牌来源归品牌来源 / 租户管理阶段）。
- **不读请求上下文**：当前租户编码 / 主键与用户主键一律由调用方经入参传入（解析链为唯一权威）。
"""

from typing import cast

from fastapi import FastAPI

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.exceptions import TenantAccessDeniedError
from bms_core.core.factory import BasePluginFactory
from bms_core.core.plugin import register_plugin
from bms_core.db.tenant import DEMO_TENANT, TenantLookup
from bms_core.tenant.base import (
    TENANT_MEMBERSHIP_SELF_HEAL_SOURCE,
    TENANT_SELF_SERVICE_DB_PROVIDER,
    TENANT_SWITCH_MODES,
    BaseTenantSelfService,
    TenantBrand,
    TenantSelfOverview,
    TenantSummary,
    TenantSwitchResult,
)
from bms_core.tenant.membership import TenantMembershipStore

__all__ = ["DbTenantSelfService", "DbTenantSelfServiceFactory", "register_db_tenant_self_service"]


class DbTenantSelfService(BaseTenantSelfService):
    """租户自助真实实现（关系数据源 + 租户源取数）。"""

    plugin_name: str = TENANT_SELF_SERVICE_DB_PROVIDER

    def __init__(self, *, membership: TenantMembershipStore, tenants: TenantLookup) -> None:
        """初始化。

        Args:
            membership: 关系数据源（本服务为 `local`：直读自身平台服务库）。
            tenants: 租户源（按编码取租户上下文）。
        """
        self._membership = membership
        self._tenants = tenants

    async def my_tenants(
        self,
        *,
        current_code: str | None = None,
        tenant_id: int | None = None,
        user_id: int | None = None,
    ) -> TenantSelfOverview:
        """取「我加入的租户」概览（含读路径自愈）。

        Args:
            current_code: 当前租户编码（由调用方从解析链上下文传入）。
            tenant_id: 当前租户主键（即用户归属租户）。
            user_id: 当前登录用户主键。

        Returns:
            TenantSelfOverview: 租户列表 + 当前租户编码 + 是否多租户。

        Raises:
            ServiceUnavailableError: 远端关系数据源契约不可达（10007）。
            TenantNotFoundError: 回落路径按编码解析租户未命中（404 / 80001）。
        """
        if tenant_id is None or user_id is None:
            return await self._fallback_overview(current_code)
        await self._ensure_self_membership(tenant_id=tenant_id, user_id=user_id)
        targets = await self._membership.list_targets(tenant_id=tenant_id, user_id=user_id)
        tenants: ConcurrentStableList[TenantSummary] = ConcurrentStableList(
            TenantSummary(id=str(item.tenant_id), name=item.name, code=item.code) for item in targets
        )
        return TenantSelfOverview(
            tenants=tenants,
            current_code=current_code,
            multi_tenant=len(tenants) > 1,
        )

    async def switch(
        self, code: str, *, tenant_id: int | None = None, user_id: int | None = None
    ) -> TenantSwitchResult:
        """切换到目标租户（越权校验 + 生效语义返回）。

        Args:
            code: 目标租户编码。
            tenant_id: 当前租户主键（即用户归属租户）。
            user_id: 当前登录用户主键。

        Returns:
            TenantSwitchResult: 切换结果（`reissue_token=True`；令牌换发归认证阶段）。

        Raises:
            TenantNotFoundError: 目标租户不存在（404 / 80001）。
            TenantSuspendedError: 目标租户停用（403 / 80002）。
            TenantAccessDeniedError: 目标租户不在可访问集合或缺少登录主体（403 / 80003）。
        """
        target = await self._tenants.by_code(code)
        if tenant_id is None or user_id is None:
            raise TenantAccessDeniedError("缺少登录主体，无法校验目标租户可访问性")
        targets = await self._membership.list_targets(tenant_id=tenant_id, user_id=user_id)
        if not any(item.tenant_id == target.tenant_id for item in targets):
            raise TenantAccessDeniedError(f"目标租户不可访问：{code}")
        return TenantSwitchResult(
            tenant_code=target.code,
            db_key=target.db_key,
            applied=True,
            mode=TENANT_SWITCH_MODES[0],
            reissue_token=True,
            token=None,
        )

    async def brand(self, *, code: str | None = None) -> TenantBrand:
        """取品牌信息（本任务不做品牌取数，维持平台默认品牌）。

        Args:
            code: 租户编码（本实现忽略）。

        Returns:
            TenantBrand: 平台默认品牌（名称沿用演示租户名，其余取默认）。
        """
        return TenantBrand(name=DEMO_TENANT.name)

    async def _ensure_self_membership(self, *, tenant_id: int, user_id: int) -> None:
        """读路径自愈：自有租户行不存在时幂等补建（存在含 `disabled` 则不自愈）。

        Args:
            tenant_id: 当前租户主键（即用户归属租户）。
            user_id: 当前登录用户主键。
        """
        rows = await self._membership.list_targets(tenant_id=tenant_id, user_id=user_id, include_disabled=True)
        if any(item.tenant_id == tenant_id for item in rows):
            return
        await self._membership.ensure(
            tenant_id=tenant_id,
            user_id=user_id,
            target_tenant_id=tenant_id,
            source=TENANT_MEMBERSHIP_SELF_HEAL_SOURCE,
        )

    async def _fallback_overview(self, current_code: str | None) -> TenantSelfOverview:
        """无登录主体时的回落概览（按当前编码解析单租户；无编码返回空概览）。

        Args:
            current_code: 当前租户编码。

        Returns:
            TenantSelfOverview: 单租户概览或空概览。
        """
        if not current_code:
            return TenantSelfOverview(current_code=None, multi_tenant=False)
        context = await self._tenants.by_code(current_code)
        return TenantSelfOverview(
            tenants=ConcurrentStableList(
                [TenantSummary(id=str(context.tenant_id), name=context.name, code=context.code)]
            ),
            current_code=current_code,
            multi_tenant=False,
        )


class DbTenantSelfServiceFactory(BasePluginFactory[DbTenantSelfService]):
    """租户自助真实实现工厂（从应用 state 取关系数据源与租户源）。"""

    plugin_key: str = "tenant_self_service"
    plugin_name: str = TENANT_SELF_SERVICE_DB_PROVIDER

    def __init__(self, app: FastAPI) -> None:
        """初始化。

        Args:
            app: 应用实例（装配期取 `app.state` 中的关系数据源与租户源）。
        """
        self._app = app

    def bind(self, app: FastAPI) -> None:
        """按应用装配刷新持有的应用实例。

        插件注册表按**进程单次**登记工厂（框架口径），工厂持有的应用实例须随每次应用装配刷新
        ——生产为单进程单应用、语义等价；多应用进程（测试）下亦取到当前应用的关系数据源与租户源。

        Args:
            app: 当前应用实例。
        """
        self._app = app

    def create(self, options: None = None) -> DbTenantSelfService:
        """构造租户自助真实实现。

        Args:
            options: 未使用（零参口径）。

        Returns:
            DbTenantSelfService: 真实实现实例。
        """
        del options
        return DbTenantSelfService(
            membership=cast("TenantMembershipStore", self._app.state.tenant_membership),
            tenants=cast("TenantLookup", self._app.state.tenant_source),
        )


_FACTORY_SLOT = "factory"
"""工厂持有槽位（插件注册表按进程单次登记工厂，故以本槽按应用刷新其绑定）。"""

_FACTORY: ConcurrentStableDict[str, DbTenantSelfServiceFactory] = ConcurrentStableDict()
"""租户自助真实实现工厂持有（首次登记创建，其后按应用刷新其持有的应用实例）。"""


def register_db_tenant_self_service(app: FastAPI) -> None:
    """登记 / 刷新租户自助真实实现（首次登记工厂，其后按应用刷新其绑定）。

    Args:
        app: 当前应用实例。
    """
    factory = _FACTORY.get(_FACTORY_SLOT)
    if factory is None:
        factory = DbTenantSelfServiceFactory(app)
        _FACTORY.set(_FACTORY_SLOT, factory)
        register_plugin("tenant_self_service", TENANT_SELF_SERVICE_DB_PROVIDER, factory)
        return
    factory.bind(app)
