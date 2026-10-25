"""租户开通编排服务（注册行 + 库侧编排 + 种子 + 模块清单 + 事件；任务 `04_01`）。

- **状态机**：先落 `provisioning` 注册行（code / domain 唯一约束占位）→ 建库 / 建表 / 种子 → 置 `active` + 事件；
  任一步失败：清理已建库（`ops.tenant_provisioning` 内完成）→ 删除注册行 → `82006`。
- **模块清单**：基础能力（恒开通）自动写行；产品模块按开通向导勾选写入（未勾选不写）。
- **配额**：按 `[tenant_quota]` 播种默认值（平台租户不播种）。
"""

from bms_core.core.config import Settings
from bms_core.core.exceptions import (
    TenantCodeExistsError,
    TenantDomainConflictError,
    TenantProvisionFailedError,
)
from bms_core.core.logging import get_logger
from bms_core.core.objects import BaseFrameworkObject
from bms_core.db.session import DbSession
from bms_core.models.tenant.tenant import TENANT_STATUS_ACTIVE, TENANT_STATUS_PROVISIONING, SysTenant
from bms_core.outbox.base import BaseOutboxStore
from bms_core.tenant.provisioning import ProvisionOutcome, provision_infrastructure
from bms_tenant.domains.tenant.repositories.tenant_registry import TenantRegistryRepository
from bms_tenant.domains.tenant.schemas.tenant_admin import TenantCreateRequest, TenantProvisionResult
from bms_tenant.domains.tenant.services.tenant_admin import TenantAdminService
from bms_tenant.domains.tenant.services.tenant_module import TenantModuleService
from bms_tenant.domains.tenant.services.tenant_quota import TenantQuotaService

__all__ = ["TenantProvisionService"]

_LOGGER = get_logger("bms.tenant_provisioning")


class TenantProvisionService(BaseFrameworkObject):
    """租户开通服务（会话绑定；调用方负责提交 / 回滚）。"""

    def __init__(
        self,
        *,
        session: DbSession,
        settings: Settings,
        modules: TenantModuleService,
        quotas: TenantQuotaService,
        outbox: BaseOutboxStore,
        admin: TenantAdminService,
    ) -> None:
        """初始化。

        Args:
            session: 平台库会话（写）。
            settings: 应用配置（开通参数扩展位）。
            modules: 租户模块服务。
            quotas: 租户配额服务。
            outbox: 事务性发件箱（事件发布位）。
            admin: 租户管理服务（详情 / 事件构造复用）。
        """
        del settings, outbox
        self._session = session
        self._repo = TenantRegistryRepository(session)
        self._modules = modules
        self._quotas = quotas
        self._admin = admin

    async def create(self, req: TenantCreateRequest, *, actor_id: int | None = None) -> TenantProvisionResult:
        """开通租户（同步全流程）。

        Args:
            req: 开通请求。
            actor_id: 操作人（平台租户用户主键）。

        Returns:
            TenantProvisionResult: 开通结果（初始口令仅本次返回）。

        Raises:
            TenantCodeExistsError: 编码已存在（82001 / 409）。
            TenantDomainConflictError: 域名冲突（82004 / 409）。
            TenantModuleUnavailableError: 模块未注册 / 未启用（82007 / 400）。
            TenantProvisionFailedError: 建库 / 建表 / 种子失败（82006 / 500）。
        """
        code = req.code.strip().lower()
        if await self._repo.by_code(code) is not None:
            raise TenantCodeExistsError(f"租户编码已存在：{code}")
        domain = req.domain.strip().lower() if req.domain else None
        if domain and await self._repo.domain_taken(domain):
            raise TenantDomainConflictError(f"租户域名已被占用：{domain}")
        await self._modules.validate_optional(req.modules)
        row = await self._repo.create(
            code=code,
            name=req.name,
            domain=domain,
            expire_at=req.expire_at,
            status=TENANT_STATUS_PROVISIONING,
        )
        await self._session.commit()
        tenant_id = int(row.id)
        try:
            outcome = await provision_infrastructure(db_basis=code)
        except Exception as exc:
            _LOGGER.error("tenant_provision_failed", tenant_id=tenant_id, code=code, error=type(exc).__name__)
            await self._cleanup_failed(tenant_id)
            raise TenantProvisionFailedError(f"租户开通失败（已清理已建库）：{code}") from exc
        await self._finish(row, req, outcome=outcome, actor_id=actor_id)
        detail = await self._admin.detail(tenant_id)
        return TenantProvisionResult(
            tenant=detail,
            admin_username=outcome.admin_username,
            initial_password=outcome.initial_password,
        )

    async def _finish(
        self,
        row: SysTenant,
        req: TenantCreateRequest,
        *,
        outcome: ProvisionOutcome,
        actor_id: int | None,
    ) -> None:
        """开通收尾：模块清单 + 默认配额 + 置 active + 事件（同事务）。

        Args:
            row: 注册行（`provisioning`）。
            req: 开通请求。
            outcome: 库侧编排结果。
            actor_id: 操作人。
        """
        del outcome
        tenant_id = int(row.id)
        await self._modules.open_base_modules(tenant_id, opened_by=actor_id)
        await self._modules.open_modules(tenant_id, req.modules, opened_by=actor_id)
        await self._quotas.seed_defaults(tenant_id)
        row.status = TENANT_STATUS_ACTIVE
        await self._session.flush()
        await self._admin.enqueue_event(row, "tenant.created")
        await self._session.commit()

    async def _cleanup_failed(self, tenant_id: int) -> None:
        """失败清理：删除注册行与库名对照（库侧已由编排内核清理）。

        Args:
            tenant_id: 租户主键。
        """
        try:
            await self._repo.delete_provisioning(tenant_id)
            await self._session.commit()
        except Exception as exc:  # 清理失败仅告警（不掩盖原始失败）
            await self._session.rollback()
            _LOGGER.error("tenant_provision_cleanup_failed", tenant_id=tenant_id, error=type(exc).__name__)
