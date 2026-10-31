"""系统参数管理接口：`/api/v1/configs`（分页 / 详情 / 新增 / 修改 / 重置 / 删除 / 恢复）。

- **鉴权**：模块级 `require_auth`；读挂 `config:query`，写挂 `config:manage`（权限码与
  `tenant/seed/menu.py` 的 `config` 业务动作一致）。
- **库**：参数在 platform 服务**租户库**（`get_uow`）；缓存域取应用级 `config_cache_region`。
- **写路径**：事务提交后由服务层失效参数缓存与 `config` 字典，并产生字段级审计事件（不投递）。
"""

from __future__ import annotations

from typing import Annotated, cast

from fastapi import Depends, Query

from bms_core.api.base import BaseRouter, page_query, require_auth
from bms_core.api.deps import get_audit_capturer, get_config_cache_region, get_uow
from bms_core.audit.base import AuditCapturer
from bms_core.config.base import ConfigCacheRegion
from bms_core.db.session import DbSession
from bms_core.db.unit_of_work import UnitOfWork
from bms_core.dict.invalidate import DictInvalidator, get_dict_invalidator
from bms_core.permission.base import require_permission
from bms_core.schemas.common import ApiResponse
from bms_core.schemas.pagination import BasePageQuery
from bms_platform.domains.platform_config.repositories.config import ConfigRepository
from bms_platform.domains.platform_config.schemas.config import (
    ConfigCreateRequest,
    ConfigItem,
    ConfigPage,
    ConfigUpdateRequest,
)
from bms_platform.domains.platform_config.services.config import ConfigAdminService

router = BaseRouter(
    key="config_admin",
    prefix="/configs",
    tags=["config"],
    dependencies=[Depends(require_auth)],
)

_REQUIRE_QUERY = Depends(require_permission("config:query"))
_REQUIRE_MANAGE = Depends(require_permission("config:manage"))

UowDep = Annotated[UnitOfWork, Depends(get_uow)]
PageDep = Annotated[BasePageQuery, Depends(page_query)]
CacheDep = Annotated[ConfigCacheRegion, Depends(get_config_cache_region)]
InvalidatorDep = Annotated[DictInvalidator, Depends(get_dict_invalidator)]
AuditDep = Annotated[AuditCapturer, Depends(get_audit_capturer)]
KeywordQuery = Annotated[str | None, Query(description="关键字（参数键 / 名称 / 备注模糊匹配）")]
GroupQuery = Annotated[str | None, Query(description="分组前缀（参数键首段，如 password）")]
StatusQuery = Annotated[str | None, Query(description="状态筛选（enabled/disabled）")]
IncludeDeletedQuery = Annotated[bool, Query(description="是否包含已软删行（回收站视图）")]


def _service(
    uow: UnitOfWork, cache: ConfigCacheRegion, invalidator: DictInvalidator, audit: AuditCapturer
) -> ConfigAdminService:
    """构造系统参数管理服务（请求级租户库会话 + 缓存域 + 失效器 + 审计捕获器）。

    Args:
        uow: 请求级工作单元（platform 服务租户库）。
        cache: 系统参数缓存域。
        invalidator: 字典版本化失效器。
        audit: 审计捕获器。

    Returns:
        ConfigAdminService: 管理服务实例。
    """
    session = cast("DbSession", uow.session)
    return ConfigAdminService(
        ConfigRepository(session),
        uow,
        cache=cache,
        invalidator=invalidator,
        audit=audit,
    )


@router.get("", dependencies=[_REQUIRE_QUERY])
async def list_configs(
    uow: UowDep,
    page: PageDep,
    cache: CacheDep,
    invalidator: InvalidatorDep,
    audit: AuditDep,
    keyword: KeywordQuery = None,
    group: GroupQuery = None,
    status: StatusQuery = None,
    include_deleted: IncludeDeletedQuery = False,
) -> ApiResponse[ConfigPage]:
    """参数分页（关键字 / 分组 / 状态筛选，可含回收站行）。

    Args:
        uow: 工作单元。
        page: 分页参数。
        cache: 系统参数缓存域。
        invalidator: 字典失效器。
        audit: 审计捕获器。
        keyword: 关键字。
        group: 分组前缀。
        status: 状态。
        include_deleted: 是否包含已软删行。

    Returns:
        ApiResponse: 统一响应，data 为分页结果。
    """
    service = _service(uow, cache, invalidator, audit)
    result = await service.page(
        page=page.page,
        size=page.size,
        keyword=keyword,
        group=group,
        status=status,
        include_deleted=include_deleted,
    )
    return ApiResponse.ok(result)


@router.get("/{config_key}", dependencies=[_REQUIRE_QUERY])
async def get_config(
    config_key: str, uow: UowDep, cache: CacheDep, invalidator: InvalidatorDep, audit: AuditDep
) -> ApiResponse[ConfigItem]:
    """按参数键取详情（页面回显）。

    Args:
        config_key: 参数键。
        uow: 工作单元。
        cache: 系统参数缓存域。
        invalidator: 字典失效器。
        audit: 审计捕获器。

    Returns:
        ApiResponse: 统一响应，data 为参数条目。
    """
    service = _service(uow, cache, invalidator, audit)
    return ApiResponse.ok(await service.detail(config_key))


@router.post("", dependencies=[_REQUIRE_MANAGE])
async def create_config(
    request: ConfigCreateRequest, uow: UowDep, cache: CacheDep, invalidator: InvalidatorDep, audit: AuditDep
) -> ApiResponse[ConfigItem]:
    """新增参数（键格式 / 重复 / 值类型 / 依赖校验）。

    Args:
        request: 新增请求。
        uow: 工作单元。
        cache: 系统参数缓存域。
        invalidator: 字典失效器。
        audit: 审计捕获器。

    Returns:
        ApiResponse: 统一响应，data 为新建条目。
    """
    service = _service(uow, cache, invalidator, audit)
    return ApiResponse.ok(await service.create(request))


@router.put("/{item_id}", dependencies=[_REQUIRE_MANAGE])
async def update_config(
    item_id: int,
    request: ConfigUpdateRequest,
    uow: UowDep,
    cache: CacheDep,
    invalidator: InvalidatorDep,
    audit: AuditDep,
) -> ApiResponse[ConfigItem]:
    """修改参数（乐观锁：`version` 不匹配即并发冲突）。

    Args:
        item_id: 参数主键。
        request: 修改请求。
        uow: 工作单元。
        cache: 系统参数缓存域。
        invalidator: 字典失效器。
        audit: 审计捕获器。

    Returns:
        ApiResponse: 统一响应，data 为修改后的条目。
    """
    service = _service(uow, cache, invalidator, audit)
    return ApiResponse.ok(await service.update(item_id, request))


@router.post("/{item_id}/reset", dependencies=[_REQUIRE_MANAGE])
async def reset_config(
    item_id: int, uow: UowDep, cache: CacheDep, invalidator: InvalidatorDep, audit: AuditDep
) -> ApiResponse[ConfigItem]:
    """重置为平台默认值（未覆盖项幂等返回）。

    Args:
        item_id: 参数主键。
        uow: 工作单元。
        cache: 系统参数缓存域。
        invalidator: 字典失效器。
        audit: 审计捕获器。

    Returns:
        ApiResponse: 统一响应，data 为重置后的条目。
    """
    service = _service(uow, cache, invalidator, audit)
    return ApiResponse.ok(await service.reset(item_id))


@router.delete("/{item_id}", dependencies=[_REQUIRE_MANAGE])
async def delete_config(
    item_id: int, uow: UowDep, cache: CacheDep, invalidator: InvalidatorDep, audit: AuditDep
) -> ApiResponse:
    """删除参数（覆盖项软删进回收站；平台默认项拒绝）。

    Args:
        item_id: 参数主键。
        uow: 工作单元。
        cache: 系统参数缓存域。
        invalidator: 字典失效器。
        audit: 审计捕获器。

    Returns:
        ApiResponse: 统一响应（data 为空）。
    """
    service = _service(uow, cache, invalidator, audit)
    await service.delete(item_id)
    return ApiResponse.ok()


@router.post("/{item_id}/restore", dependencies=[_REQUIRE_MANAGE])
async def restore_config(
    item_id: int, uow: UowDep, cache: CacheDep, invalidator: InvalidatorDep, audit: AuditDep
) -> ApiResponse[ConfigItem]:
    """从回收站恢复参数（同键已有活行则拒绝）。

    Args:
        item_id: 参数主键。
        uow: 工作单元。
        cache: 系统参数缓存域。
        invalidator: 字典失效器。
        audit: 审计捕获器。

    Returns:
        ApiResponse: 统一响应，data 为恢复后的条目。
    """
    service = _service(uow, cache, invalidator, audit)
    return ApiResponse.ok(await service.restore(item_id))
