"""语言清单管理接口：`/api/v1/i18n/locales`（分页 / 启用清单 / 新增 / 修改 / 删除）。

- **鉴权**：模块级 `require_auth`；查询挂 `i18n:query`，维护挂 `i18n:manage`；
  启用语言清单（`/enabled`）登录即可（多语言文案字段渲染语言格要用）。
- **库**：语言清单在 platform 服务**租户库**（`get_uow`）；启用清单走能力域缓存。
- **写路径**：事务提交后由服务层连带失效「清单 + 全部语言包」缓存并刷新快照，并产生字段级审计事件。
"""

from __future__ import annotations

from typing import Annotated, cast

from fastapi import Depends, Query

from bms_core.api.base import BaseRouter, page_query, require_auth
from bms_core.api.deps import get_audit_capturer, get_locale_registry, get_uow
from bms_core.audit.base import AuditCapturer
from bms_core.db.session import DbSession
from bms_core.db.unit_of_work import UnitOfWork
from bms_core.i18n.invalidate import I18nInvalidator, get_i18n_invalidator
from bms_core.i18n.registry import BaseLocaleRegistry
from bms_core.permission.base import require_permission
from bms_core.schemas.common import ApiResponse
from bms_core.schemas.pagination import BasePageQuery
from bms_platform.domains.i18n.repositories.locale import LocaleRepository
from bms_platform.domains.i18n.schemas.i18n import (
    LocaleCreateRequest,
    LocaleDeleteResult,
    LocaleItem,
    LocaleListPayload,
    LocalePage,
    LocaleUpdateRequest,
)
from bms_platform.domains.i18n.services.locale import LocaleAdminService

router = BaseRouter(
    key="i18n_locales",
    prefix="/i18n/locales",
    tags=["i18n"],
    dependencies=[Depends(require_auth)],
)

_REQUIRE_QUERY = Depends(require_permission("i18n:query"))
_REQUIRE_MANAGE = Depends(require_permission("i18n:manage"))

UowDep = Annotated[UnitOfWork, Depends(get_uow)]
PageDep = Annotated[BasePageQuery, Depends(page_query)]
RegistryDep = Annotated[BaseLocaleRegistry, Depends(get_locale_registry)]
InvalidatorDep = Annotated[I18nInvalidator, Depends(get_i18n_invalidator)]
AuditDep = Annotated[AuditCapturer, Depends(get_audit_capturer)]
KeywordQuery = Annotated[str | None, Query(description="关键字（语言标识 / 名称模糊匹配）")]
StatusQuery = Annotated[str | None, Query(description="状态筛选（enabled/disabled）")]
IncludeDeletedQuery = Annotated[bool, Query(description="是否包含已软删行（回收站视图）")]


def _service(
    uow: UnitOfWork, registry: BaseLocaleRegistry, invalidator: I18nInvalidator, audit: AuditCapturer
) -> LocaleAdminService:
    """构造语言清单管理服务（请求级租户库会话 + 能力域 + 失效器 + 审计捕获器）。

    Args:
        uow: 请求级工作单元（platform 服务租户库）。
        registry: 语言清单能力域。
        invalidator: 国际化缓存失效器。
        audit: 审计捕获器。

    Returns:
        LocaleAdminService: 管理服务实例。
    """
    session = cast("DbSession", uow.session)
    return LocaleAdminService(
        LocaleRepository(session),
        uow,
        registry=registry,
        invalidator=invalidator,
        audit=audit,
    )


@router.get("", dependencies=[_REQUIRE_QUERY])
async def list_locales(
    uow: UowDep,
    page: PageDep,
    registry: RegistryDep,
    invalidator: InvalidatorDep,
    audit: AuditDep,
    keyword: KeywordQuery = None,
    status: StatusQuery = None,
    include_deleted: IncludeDeletedQuery = False,
) -> ApiResponse[LocalePage]:
    """语言清单分页查询。

    需要 i18n:query 权限；支持按语言标识 / 名称关键字与状态筛选，可含回收站行。
    """
    service = _service(uow, registry, invalidator, audit)
    result = await service.page(
        page=page.page, size=page.size, keyword=keyword, status=status, include_deleted=include_deleted
    )
    return ApiResponse[LocalePage](data=result)


@router.get("/enabled")
async def list_enabled_locales(
    uow: UowDep,
    registry: RegistryDep,
    invalidator: InvalidatorDep,
    audit: AuditDep,
) -> ApiResponse[LocaleListPayload]:
    """启用语言清单（登录即可访问）。

    返回 `code` / `name` / `rtl` / 默认标记 / 排序，供各模块多语言文案字段渲染语言格；
    走能力域缓存，新增语言后下一次请求即可见。
    """
    service = _service(uow, registry, invalidator, audit)
    items = await service.list_enabled()
    return ApiResponse[LocaleListPayload](data=LocaleListPayload(items=items))


@router.post("", dependencies=[_REQUIRE_MANAGE])
async def create_locale(
    uow: UowDep,
    registry: RegistryDep,
    invalidator: InvalidatorDep,
    audit: AuditDep,
    request: LocaleCreateRequest,
) -> ApiResponse[LocaleItem]:
    """新增语言（需要 i18n:manage）。

    语言标识为 IETF 语言标签（如 ar-SA），大小写不敏感判重；`isDefault=true` 时同事务切换默认语言。
    """
    service = _service(uow, registry, invalidator, audit)
    return ApiResponse[LocaleItem](data=await service.create(request))


@router.put("/{code}", dependencies=[_REQUIRE_MANAGE])
async def update_locale(
    uow: UowDep,
    registry: RegistryDep,
    invalidator: InvalidatorDep,
    audit: AuditDep,
    code: str,
    request: LocaleUpdateRequest,
) -> ApiResponse[LocaleItem]:
    """修改语言（需要 i18n:manage，乐观锁）。

    默认语言不可停用（44005）；停用后须仍有启用语言（44004）；默认标记不可取消（44006）。
    """
    service = _service(uow, registry, invalidator, audit)
    return ApiResponse[LocaleItem](data=await service.update(code, request))


@router.delete("/{code}", dependencies=[_REQUIRE_MANAGE])
async def delete_locale(
    uow: UowDep,
    registry: RegistryDep,
    invalidator: InvalidatorDep,
    audit: AuditDep,
    code: str,
) -> ApiResponse[LocaleDeleteResult]:
    """删除语言（需要 i18n:manage）。

    默认语言不可删除（44005）；仍有语言包数据的语言只能停用（44002）。
    """
    service = _service(uow, registry, invalidator, audit)
    await service.delete(code)
    return ApiResponse[LocaleDeleteResult](data=LocaleDeleteResult(deleted=True))
