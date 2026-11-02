"""平台导入定义装配（服务根，`shared_paths`）：把 users / roles 定义与所有者域写服务接起来。

**为什么在服务根**：导入域不能直接 import 用户 / 角色域实现（D1）；定义本身在各自域内，写服务
由本装配面构造后注入。API 与作业 worker 共用同一装配函数。
"""

from __future__ import annotations

from bms_core.audit.base import AuditCapturer
from bms_core.config.base import BaseConfigSource
from bms_core.db.session import DbSession
from bms_core.db.unit_of_work import UnitOfWork
from bms_core.outbox.base import BaseOutboxStore
from bms_core.password.base import BasePasswordPolicy
from bms_core.security.base import BasePasswordHasher
from bms_core.servicecall.base import BaseServiceClient
from bms_core.transfer.definition import ImportDefinitionRegistry
from bms_platform.domains.role.imports import RoleImportDefinition
from bms_platform.domains.role.repositories.role import RoleRepository, UserRoleRepository
from bms_platform.domains.role.services.role import RoleService
from bms_platform.domains.user.imports import UserImportDefinition
from bms_platform.domains.user.repositories.account_lock import AccountLockRepository
from bms_platform.domains.user.repositories.user import UserRepository
from bms_platform.domains.user.services.user_sessions import UserSessionClient
from bms_platform.domains.user.services.users_admin import UserAdminService
from bms_platform.wiring import role_assignment, role_query

__all__ = ["build_import_definitions"]


def build_import_definitions(
    *,
    hasher: BasePasswordHasher,
    policy: BasePasswordPolicy,
    outbox: BaseOutboxStore,
    service_client: BaseServiceClient,
    audit: AuditCapturer | None,
    config: BaseConfigSource,
) -> ImportDefinitionRegistry:
    """构造平台首批导入定义（users / roles）。

    Args:
        hasher: 口令哈希器（用户建号）。
        policy: 密码策略（用户预检 / 建号）。
        outbox: 事务性发件箱（用户事件）。
        service_client: 服务间调用客户端（用户会话失效）。
        audit: 审计捕获器（None 表示不记录）。
        config: 系统参数取数（角色码格式）。

    Returns:
        ImportDefinitionRegistry: 已登记 users / roles 的注册表。
    """

    def user_service(session: DbSession, uow: UnitOfWork) -> UserAdminService:
        """构造用户完整域服务（与 `POST /users` 同口径）。"""
        return UserAdminService(
            session,
            uow,
            UserRepository(session),
            role_assignment(session),
            role_query(session),
            AccountLockRepository(session),
            hasher,
            policy,
            outbox,
            UserSessionClient(service_client),
        )

    def role_service(session: DbSession, uow: UnitOfWork) -> RoleService:
        """构造角色服务。"""
        return RoleService(RoleRepository(session), UserRoleRepository(session), uow, config)

    registry = ImportDefinitionRegistry()
    registry.register(UserImportDefinition(service_factory=user_service, policy=policy, audit=audit))
    registry.register(RoleImportDefinition(service_factory=role_service, audit=audit))
    return registry
