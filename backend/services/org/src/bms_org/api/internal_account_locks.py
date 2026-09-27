"""组织主数据服务内部端点：`/api/v1/org/internal/account-locks/*`（服务间调用，不经网关）。

- **鉴权**：模块级 `require_service("identity", "platform")`——仅接受 `sub=identity` 或 `sub=platform`
  的有效服务 JWT（`aud=service`）；用户票据与网关服务票据（`sub=gateway`）一律拒。
- **租户**：由服务 JWT `tenant` claim 经全局租户中间件解析租户库（操作当前租户）。
- **契约**：计入 org 公开契约（`deploy/contracts/org.json`）；新增端点属非破坏性变更。
- **手动触发**：180 天不活跃扫描的定时调度（Celery）归阶段八，本端点供手动 / 运维触发。
"""

from typing import Annotated, cast

from fastapi import Depends

from bms_core.api.base import BaseRouter, require_service
from bms_core.api.deps import get_config_source, get_uow
from bms_core.config.base import BaseConfigSource
from bms_core.db.session import DbSession
from bms_core.db.unit_of_work import UnitOfWork
from bms_core.schemas.common import ApiResponse
from bms_org.repositories.account_lock import AccountLockRepository
from bms_org.repositories.user import UserRepository
from bms_org.schemas.account_lock import InactiveScanRequest, InactiveScanResult
from bms_org.services.account_lock import AccountLockService

router = BaseRouter(
    key="org_internal_account_locks",
    prefix="/org/internal/account-locks",
    tags=["org-internal"],
    dependencies=[Depends(require_service("identity", "platform"))],
)

UowDep = Annotated[UnitOfWork, Depends(get_uow)]
ConfigDep = Annotated[BaseConfigSource, Depends(get_config_source)]


@router.post("/scan-inactive")
async def scan_inactive(req: InactiveScanRequest, uow: UowDep, config: ConfigDep) -> ApiResponse[InactiveScanResult]:
    """扫描并锁定长期未登录账号（幂等；含从未登录账号）。

    Args:
        req: 扫描请求（空体）。
        uow: 请求级工作单元。
        config: 系统参数取数（读 `account.inactive_lock_days`）。

    Returns:
        ApiResponse: 统一响应，data 为扫描概要（`InactiveScanResult`）。
    """
    session = cast("DbSession", uow.session)
    service = AccountLockService(UserRepository(session), AccountLockRepository(session), uow, config)
    return ApiResponse.ok(await service.scan_inactive())
