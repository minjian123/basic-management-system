"""关系数据源装配点：用户↔租户可达关系的读写契约与装配（照抄「租户源」范式，11_01）。

- 共享基座只保留**契约（`TenantMembershipStore`）与装配点**；实现按归属落服务：
  - `local`：租户服务直读自身平台服务库 `sys_user_tenant`（`bms_tenant/sources/membership.py`）；
  - `remote`：其他服务经租户服务内部端点读写（`tenant/membership_remote.py`）。
- 选源：`[tenant_membership].source` 显式指定；空串为**自动**——运行服务即租户服务 → `local`，否则 `remote`。
- `build_tenant_membership_store` 是应用装配（`application.py`）的唯一入口；未注册名快速失败。
- **免认证链路禁用**：关系数据只服务登录后链路（`my_tenants` / `switch`）——《安全开发规范》§3 禁止项，
  登录前不得经本数据源查询账号租户归属。
"""

from typing import TYPE_CHECKING, Annotated, Protocol

from pydantic import Field

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.config import Settings
from bms_core.core.exceptions import ConfigError
from bms_core.db.registry import EngineRegistry
from bms_core.db.session import SessionFactory
from bms_core.db.tenant_source import TENANT_SERVICE_KEY
from bms_core.schemas.base import CONTRACT_COLLECTION, CONTRACT_STABLE_LIST, BaseSchema

if TYPE_CHECKING:  # pragma: no cover - 仅类型检查用（避免与 servicecall 域循环导入）
    from bms_core.servicecall.base import BaseServiceClient

__all__ = [
    "DEFAULT_TENANT_MEMBERSHIP_STORE",
    "LOCAL_TENANT_MEMBERSHIP_STORE",
    "REMOTE_TENANT_MEMBERSHIP_STORE",
    "TENANT_MEMBERSHIP_INTERNAL_PATH",
    "TenantMembershipGrantRequest",
    "TenantMembershipListResponse",
    "TenantMembershipReport",
    "TenantMembershipStore",
    "TenantMembershipStoreFactory",
    "TenantMembershipTarget",
    "build_tenant_membership_store",
    "register_tenant_membership_store",
    "registered_tenant_membership_stores",
]

LOCAL_TENANT_MEMBERSHIP_STORE = "local"
"""本地关系数据源实现名（租户服务直读自身平台服务库）。"""

REMOTE_TENANT_MEMBERSHIP_STORE = "remote"
"""远端关系数据源实现名（其他服务经内部端点读写）。"""

DEFAULT_TENANT_MEMBERSHIP_STORE = "remote"
"""缺省关系数据源实现名（非租户服务）。"""

TENANT_MEMBERSHIP_INTERNAL_PATH = "/api/v1/tenant/internal/memberships"
"""关系读写内部端点路径（租户服务提供；服务 JWT 鉴权）。"""


class TenantMembershipTarget(BaseSchema):
    """可访问目标租户条目（关系 + 租户元信息）。"""

    tenant_id: int = Field(description="目标租户主键（雪花 id）")
    code: str = Field(description="目标租户编码")
    name: str = Field(description="目标租户名称")
    domain: str | None = Field(default=None, description="目标租户子域名")
    source: str = Field(default="", description="写入来源")
    status: str = Field(default="active", description="关系状态（active / disabled）")


class TenantMembershipListResponse(BaseSchema):
    """某用户当前有效可访问租户集合（内部端点统一响应）。"""

    targets: Annotated[ConcurrentStableList[TenantMembershipTarget], CONTRACT_COLLECTION] = Field(
        default_factory=CONTRACT_STABLE_LIST, description="有效可访问目标租户（status=active）"
    )


class TenantMembershipReport(BaseSchema):
    """用户↔租户可达关系对账巡检结果（缺行 / 悬空行，用户主键列表）。"""

    missing: Annotated[ConcurrentStableList[int], CONTRACT_COLLECTION] = Field(
        default_factory=CONTRACT_STABLE_LIST, description="缺行用户主键（用户清单中无自有租户关系者）"
    )
    dangling: Annotated[ConcurrentStableList[int], CONTRACT_COLLECTION] = Field(
        default_factory=CONTRACT_STABLE_LIST, description="悬空用户主键（关系表中有行但不在用户清单内者）"
    )


class TenantMembershipGrantRequest(BaseSchema):
    """建立 / 复活关系入参（全字段显式；`owner_tenant_id` 为用户归属租户）。"""

    owner_tenant_id: int = Field(description="归属租户主键（用户建号 / 登录所在租户）")
    user_id: int = Field(description="用户主键（org 服务 sys_user.id）")
    target_tenant_id: int = Field(description="目标租户主键")
    source: str = Field(min_length=1, description="写入来源（super_admin / admin_create / import / sso_jit / …）")


class TenantMembershipStore(Protocol):
    """关系数据源契约：读可访问目标集合 + 建 / 回收关系（实现分 `local` / `remote`）。"""

    async def list_targets(
        self, *, tenant_id: int, user_id: int, include_disabled: bool = False
    ) -> ConcurrentStableList[TenantMembershipTarget]:
        """取某用户可访问目标租户集合。

        Args:
            tenant_id: 归属租户主键。
            user_id: 用户主键。
            include_disabled: 是否含 `disabled` 行（缺省只取有效行；读路径自愈判据用）。

        Returns:
            ConcurrentStableList[TenantMembershipTarget]: 目标集合（缺省只含 status=active）。
        """
        ...

    async def ensure(
        self, *, tenant_id: int, user_id: int, target_tenant_id: int, source: str
    ) -> TenantMembershipTarget:
        """建立 / 复活关系（幂等：按唯一键命中即置有效）。

        Args:
            tenant_id: 归属租户主键。
            user_id: 用户主键。
            target_tenant_id: 目标租户主键。
            source: 写入来源（仅在首次建立时落库）。

        Returns:
            TenantMembershipTarget: 建立 / 复活后的目标条目。

        Raises:
            ServiceUnavailableError: 远端实现契约不可达或响应非法（10007）。
        """
        ...

    async def revoke(self, *, tenant_id: int, user_id: int, target_tenant_id: int) -> None:
        """回收单个目标租户关系（置 `disabled`，幂等）。

        Args:
            tenant_id: 归属租户主键。
            user_id: 用户主键。
            target_tenant_id: 目标租户主键。
        """
        ...

    async def revoke_all(self, *, tenant_id: int, user_id: int) -> None:
        """回收该用户全部目标租户关系（置 `disabled`，幂等）。

        Args:
            tenant_id: 归属租户主键。
            user_id: 用户主键。
        """
        ...


class TenantMembershipStoreFactory(Protocol):
    """关系数据源工厂契约：按应用装配产物构造 `TenantMembershipStore` 实现。"""

    def __call__(
        self,
        *,
        settings: Settings,
        registry: EngineRegistry,
        session_factory: SessionFactory | None,
        service_client: BaseServiceClient | None,
    ) -> TenantMembershipStore:
        """构造关系数据源实现。

        Args:
            settings: 应用配置。
            registry: 引擎注册表（本地实现用）。
            session_factory: 会话工厂（本地实现用）。
            service_client: 服务间调用客户端（远端实现用）。

        Returns:
            TenantMembershipStore: 关系数据源实现。
        """
        ...


_STORE_FACTORIES: ConcurrentStableDict[str, TenantMembershipStoreFactory] = ConcurrentStableDict()
"""已登记的关系数据源实现工厂（保序；同名后登记者为准）。"""


def register_tenant_membership_store(name: str, factory: TenantMembershipStoreFactory) -> None:
    """登记关系数据源实现（幂等：同名重复登记以后登记者为准）。

    Args:
        name: 实现名（`local` / `remote`）。
        factory: 工厂。

    Raises:
        ConfigError: 实现名为空。
    """
    if not name:
        raise ConfigError("关系数据源实现名不得为空")
    _STORE_FACTORIES.set(name, factory)


def registered_tenant_membership_stores() -> tuple[str, ...]:
    """已登记的关系数据源实现名（保序）。

    Returns:
        tuple[str, ...]: 实现名元组。
    """
    return tuple(_STORE_FACTORIES)


def build_tenant_membership_store(
    name: str,
    *,
    settings: Settings,
    registry: EngineRegistry,
    session_factory: SessionFactory | None,
    service_client: BaseServiceClient | None,
) -> TenantMembershipStore:
    """按名构造关系数据源实现（空名 → 自动选源）。

    Args:
        name: 实现名（`[tenant_membership].source`）；空串表示自动。
        settings: 应用配置。
        registry: 引擎注册表。
        session_factory: 会话工厂。
        service_client: 服务间调用客户端。

    Returns:
        TenantMembershipStore: 关系数据源实现。

    Raises:
        ConfigError: 实现名未登记或未提供必需依赖。
    """
    resolved = name or (
        LOCAL_TENANT_MEMBERSHIP_STORE if settings.app.service == TENANT_SERVICE_KEY else DEFAULT_TENANT_MEMBERSHIP_STORE
    )
    factory = _STORE_FACTORIES.get(resolved)
    if factory is None:
        known = " / ".join(registered_tenant_membership_stores()) or "（无）"
        raise ConfigError(f"关系数据源实现未登记：{resolved}（已登记 {known}）")
    return factory(
        settings=settings,
        registry=registry,
        session_factory=session_factory,
        service_client=service_client,
    )
