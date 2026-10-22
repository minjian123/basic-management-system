"""默认平台租户引导（幂等；任务 `04_01`）。

- **语义**：平台超管就是「平台租户」里的 `sys_user`；平台租户（`sys_tenant.kind=platform`）与业务租户
  同构（同库结构、同登录 / 会话 / 权限链），只是类型不同且不参与业务租户列表与唯一启用兜底。
- **触发**：tenant 服务启动钩子（`[platform_tenant].auto_bootstrap`，dev / test 默认 true、prod 默认 false）；
  生产由 `ops.bootstrap_platform` 显式执行。
- **失败**：清理已建库与注册行、记 ERROR、不阻断启动（引导可重跑）。
"""

from fastapi import FastAPI

from bms_core.core.config import Settings
from bms_core.core.exceptions import ConfigError
from bms_core.core.logging import get_logger
from bms_core.db.keys import PLATFORM_DB_KEY
from bms_core.db.session import DbSession, session_scope
from bms_core.models.tenant.tenant import (
    TENANT_KIND_PLATFORM,
    TENANT_STATUS_ACTIVE,
    TENANT_STATUS_PROVISIONING,
    SysTenant,
)
from bms_core.outbox.base import BaseOutboxStore
from bms_core.tenant.provisioning import provision_infrastructure
from bms_tenant.repositories.tenant_registry import TenantRegistryRepository
from bms_tenant.services.tenant_admin import TenantAdminService
from bms_tenant.services.tenant_module import ModuleCatalog, TenantModuleService
from bms_tenant.services.tenant_quota import TenantQuotaService

__all__ = ["ensure_platform_tenant", "ensure_platform_tenant_row"]

_LOGGER = get_logger("bms.platform_tenant")


async def ensure_platform_tenant(app: FastAPI) -> None:
    """启动钩子：幂等引导默认平台租户。

    Args:
        app: 应用实例（取配置 / 引擎 / 会话工厂 / 服务客户端 / 缓存 / 发件箱）。

    Raises:
        ConfigError: 平台租户编码与既有业务租户冲突（配置错误，拒启）。
    """
    settings: Settings = app.state.settings
    if not settings.platform_tenant.auto_bootstrap:
        return
    async with session_scope(
        app.state.engine_registry, db_key=PLATFORM_DB_KEY, factory=app.state.session_factory
    ) as session:
        modules = TenantModuleService(
            session=session,
            catalog=ModuleCatalog(client=app.state.service_client, cache=app.state.cache),
            cache=app.state.cache,
        )
        admin = TenantAdminService(
            session=session,
            modules=modules,
            quotas=TenantQuotaService(session, settings),
            outbox=app.state.outbox_store,
        )
        try:
            created = await ensure_platform_tenant_row(
                session=session,
                settings=settings,
                modules=modules,
                admin=admin,
                outbox=app.state.outbox_store,
            )
        except ConfigError:
            raise
        except Exception as exc:  # 引导失败不阻断启动（可重跑）
            _LOGGER.error("platform_tenant_bootstrap_failed", error=type(exc).__name__, detail=str(exc))
            return
        if created:
            invalidate = getattr(app.state.tenant_source, "invalidate", None)
            if callable(invalidate):
                invalidate(settings.platform_tenant.code)
            bump = getattr(app.state.tenant_source, "bump_version", None)
            if callable(bump):
                bump()


async def ensure_platform_tenant_row(
    *,
    session: DbSession,
    settings: Settings,
    modules: TenantModuleService,
    admin: TenantAdminService,
    outbox: BaseOutboxStore,
) -> bool:
    """幂等创建 / 补齐平台租户（供启动钩子与 `ops.bootstrap_platform` 共用）。

    Args:
        session: 平台库会话（写）。
        settings: 应用配置（`[platform_tenant]`）。
        modules: 租户模块服务。
        admin: 租户管理服务（详情 / 事件）。
        outbox: 事务性发件箱（占位，事件经 `admin`）。

    Returns:
        bool: 本次是否完成引导（`False` 表示已就绪或失败）。

    Raises:
        ConfigError: 平台租户编码被业务租户占用（配置错误）。
    """
    del outbox
    code = settings.platform_tenant.code.strip().lower()
    repo = TenantRegistryRepository(session)
    row = await repo.by_code(code)
    if row is not None:
        if row.kind != TENANT_KIND_PLATFORM:
            raise ConfigError(f"平台租户编码已被业务租户占用：{code}")
        if row.status == TENANT_STATUS_ACTIVE:
            await _ensure_base_modules(modules, int(row.id))
            return False
        if row.status != TENANT_STATUS_PROVISIONING:
            # 已存在但非启用 / 开通中（如被误停用）：重新走库侧编排补齐
            row.status = TENANT_STATUS_PROVISIONING
            await session.flush()
    else:
        row = await repo.create(
            code=code,
            name=settings.platform_tenant.name,
            domain=None,
            kind=TENANT_KIND_PLATFORM,
            status=TENANT_STATUS_PROVISIONING,
        )
    await session.commit()
    tenant_id = int(row.id)
    try:
        await provision_infrastructure(db_basis=code, platform=True)
    except Exception as exc:
        _LOGGER.error("platform_tenant_provision_failed", code=code, error=type(exc).__name__)
        await _cleanup(repo, session, tenant_id)
        return False
    await _ensure_base_modules(modules, tenant_id)
    await _set_active(session, row)
    await admin.enqueue_event(row, "tenant.created")
    await session.commit()
    _LOGGER.info("platform_tenant_ready", code=code, tenant_id=tenant_id)
    return True


async def _ensure_base_modules(modules: TenantModuleService, tenant_id: int) -> None:
    """补齐基础模块清单（目录不可达时仅告警；基础模块门禁恒放行）。

    Args:
        modules: 租户模块服务。
        tenant_id: 租户主键。
    """
    try:
        await modules.open_base_modules(tenant_id)
    except Exception as exc:
        _LOGGER.warning("platform_tenant_base_modules_failed", tenant_id=tenant_id, error=type(exc).__name__)


async def _set_active(session: DbSession, row: SysTenant) -> None:
    """置平台租户为启用并落库。

    Args:
        session: 平台库会话。
        row: 注册行。
    """
    row.status = TENANT_STATUS_ACTIVE
    await session.flush()


async def _cleanup(repo: TenantRegistryRepository, session: DbSession, tenant_id: int) -> None:
    """失败清理：删除注册行与库名对照。

    Args:
        repo: 注册仓储。
        session: 平台库会话。
        tenant_id: 租户主键。
    """
    try:
        await repo.delete_provisioning(tenant_id)
        await session.commit()
    except Exception as exc:
        await session.rollback()
        _LOGGER.error("platform_tenant_cleanup_failed", tenant_id=tenant_id, error=type(exc).__name__)
