"""公告路由：`/api/v1/notices`（管理 / 全员 / 回执 / 统计）与内部过期端点。

- 管理写操作挂权限码；全员列表 / 详情（发布中）/ 回执只要求登录；
- 草稿 / 已下线的详情额外要求 `notice:update`（普通用户按不存在处理）；
- 静态路径（`/published`、`/internal/expire`）先于 `/{notice_id}` 登记，避免路径吞并；
- 语言优先级：显式 `locale` 参数 → `Accept-Language` 主语言 → 系统默认常量。
"""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, Header, Query

from bms_core.api.base import BaseRouter, page_query, require_auth, require_service
from bms_core.core.context import get_current_tenant_id
from bms_core.core.exceptions import ParamError
from bms_core.db.session import get_uow
from bms_core.db.unit_of_work import DbUnitOfWork
from bms_core.i18n.base import get_default_locale
from bms_core.optionset.base import BaseOptionSetRegistry, get_option_set_registry
from bms_core.permission.base import (
    BasePermissionChecker,
    get_permission_checker,
    prepare_permission_dependency,
    require_permission,
)
from bms_core.schemas.common import ApiResponse
from bms_core.schemas.pagination import BasePageQuery
from bms_core.servicecall.base import BaseServiceClient, get_service_client
from bms_notification.domains.notification.notice_constants import NOTICE_STATUSES
from bms_notification.domains.notification.schemas.notice import (
    NoticeCreateRequest,
    NoticeExpireRequest,
    NoticeExpireResult,
    NoticeUpdateRequest,
)
from bms_notification.domains.notification.services.notice import NoticeService
from bms_notification.domains.notification.services.notice_audience import NoticeAudienceReader

router = BaseRouter(
    key="notice",
    prefix="/notices",
    tags=["notice"],
    dependencies=[Depends(require_auth)],
)

internal_router = BaseRouter(
    key="notice_internal",
    prefix="/notices/internal",
    tags=["notice-internal"],
    dependencies=[Depends(require_service("platform"))],
)

UowDep = Annotated[DbUnitOfWork, Depends(get_uow)]
RegistryDep = Annotated[BaseOptionSetRegistry, Depends(get_option_set_registry)]
CheckerDep = Annotated[BasePermissionChecker, Depends(get_permission_checker)]
PageDep = Annotated[BasePageQuery, Depends(page_query)]
LocaleQuery = Annotated[str | None, Query(description="语言标识（缺省按 Accept-Language）")]
AcceptLanguage = Annotated[str | None, Header(alias="Accept-Language")]

_REQUIRE_QUERY = Depends(require_permission("notice:query"))
_REQUIRE_CREATE = Depends(require_permission("notice:create"))
_REQUIRE_UPDATE = Depends(require_permission("notice:update"))
_REQUIRE_DELETE = Depends(require_permission("notice:delete"))
_PREPARE_PERMISSION = Depends(prepare_permission_dependency())


def get_notice_audience_reader(
    client: Annotated[BaseServiceClient, Depends(get_service_client)],
) -> NoticeAudienceReader:
    """应读人数读取器依赖（测试可覆盖）。

    Args:
        client: 服务间调用客户端。

    Returns:
        NoticeAudienceReader: 读取器。
    """
    return NoticeAudienceReader(client)


AudienceDep = Annotated[NoticeAudienceReader, Depends(get_notice_audience_reader)]


def _service(uow: UowDep, registry: RegistryDep) -> NoticeService:
    """构造公告服务（当前租户库会话）。

    Args:
        uow: 请求级工作单元。
        registry: 选项集注册表。

    Returns:
        NoticeService: 公告服务。
    """
    return NoticeService(uow.session, option_sets=registry)


def _now() -> datetime:
    """当前 UTC naive 时间（与库内 `DATETIME` 口径一致）。

    Returns:
        datetime: 当前时间。
    """
    return datetime.now(UTC).replace(tzinfo=None)


def _resolve_locale(locale: str | None, accept_language: str | None) -> str:
    """解析请求语言：显式参数 → Accept-Language → 系统默认常量。

    Args:
        locale: 显式语言标识。
        accept_language: 请求头。

    Returns:
        str: 生效语言标识。
    """
    if locale and locale.strip():
        return locale.strip()
    if accept_language:
        primary = accept_language.split(",", 1)[0].split(";", 1)[0].strip()
        if primary:
            return primary
    return get_default_locale()


def _require_status(status: str | None) -> None:
    """校验状态筛选值。

    Args:
        status: 状态（可空）。

    Raises:
        ParamError: 未知状态（10001）。
    """
    if status is not None and status not in NOTICE_STATUSES:
        raise ParamError(f"公告状态非法：{status}")


@router.get("", dependencies=[_REQUIRE_QUERY])
async def list_notices(
    uow: UowDep,
    registry: RegistryDep,
    checker: CheckerDep,
    page: PageDep,
    locale: LocaleQuery = None,
    accept_language: AcceptLanguage = None,
    keyword: Annotated[str | None, Query(description="标题关键字")] = None,
    status: Annotated[str | None, Query(description="状态（draft/published/offline）")] = None,
    notice_type: Annotated[str | None, Query(alias="type", description="公告类型（选项集值）")] = None,
) -> ApiResponse:
    """管理列表（无 `notice:update` 时只看发布中）。

    Args:
        uow: 请求级工作单元。
        registry: 选项集注册表。
        checker: 权限检查器（判定是否可见管理态）。
        page: 分页契约。
        locale: 显式语言。
        accept_language: 请求头语言。
        keyword: 标题关键字。
        status: 状态筛选。
        notice_type: 类型筛选。

    Returns:
        ApiResponse: 统一响应，data 为分页列表。
    """
    _require_status(status)
    service = _service(uow, registry)
    async with uow.begin():
        result = await service.list_manage(
            page=page.page,
            size=page.size,
            now=_now(),
            locale=_resolve_locale(locale, accept_language),
            keyword=keyword,
            status=status,
            notice_type=notice_type,
            can_manage=checker.check("notice:update"),
        )
    return ApiResponse.ok(result)


@router.get("/published")
async def list_published_notices(
    uow: UowDep,
    registry: RegistryDep,
    page: PageDep,
    locale: LocaleQuery = None,
    accept_language: AcceptLanguage = None,
) -> ApiResponse:
    """全员发布中列表（置顶优先，登录即可）。

    Args:
        uow: 请求级工作单元。
        registry: 选项集注册表。
        page: 分页契约。
        locale: 显式语言。
        accept_language: 请求头语言。

    Returns:
        ApiResponse: 统一响应，data 为分页列表。
    """
    service = _service(uow, registry)
    async with uow.begin():
        result = await service.list_published(
            page=page.page,
            size=page.size,
            now=_now(),
            locale=_resolve_locale(locale, accept_language),
        )
    return ApiResponse.ok(result)


@router.post("", dependencies=[_REQUIRE_CREATE])
async def create_notice(
    uow: UowDep,
    registry: RegistryDep,
    req: NoticeCreateRequest,
    locale: LocaleQuery = None,
    accept_language: AcceptLanguage = None,
) -> ApiResponse:
    """新建公告（草稿或直接发布）。

    Args:
        uow: 请求级工作单元。
        registry: 选项集注册表。
        req: 新建请求。
        locale: 显式语言（必填语言口径）。
        accept_language: 请求头语言。

    Returns:
        ApiResponse: 统一响应，data 为公告详情。
    """
    service = _service(uow, registry)
    async with uow.begin():
        detail = await service.create(
            req,
            now=_now(),
            request_locale=_resolve_locale(locale, accept_language),
            tenant_id=get_current_tenant_id(),
        )
    return ApiResponse.ok(detail)


@router.put("/{notice_id}", dependencies=[_REQUIRE_UPDATE])
async def update_notice(
    uow: UowDep,
    registry: RegistryDep,
    notice_id: int,
    req: NoticeUpdateRequest,
    locale: LocaleQuery = None,
    accept_language: AcceptLanguage = None,
) -> ApiResponse:
    """编辑公告（含置顶、草稿发布、已发布重新发布）。

    Args:
        uow: 请求级工作单元。
        registry: 选项集注册表。
        notice_id: 公告主键。
        req: 编辑请求。
        locale: 显式语言。
        accept_language: 请求头语言。

    Returns:
        ApiResponse: 统一响应，data 为公告详情。
    """
    service = _service(uow, registry)
    async with uow.begin():
        detail = await service.update(
            notice_id,
            req,
            now=_now(),
            request_locale=_resolve_locale(locale, accept_language),
            tenant_id=get_current_tenant_id(),
            can_manage=True,
        )
    return ApiResponse.ok(detail)


@router.delete("/{notice_id}", dependencies=[_REQUIRE_DELETE])
async def delete_notice(uow: UowDep, registry: RegistryDep, notice_id: int) -> ApiResponse:
    """软删除公告（连带软删多语言附表）。

    Args:
        uow: 请求级工作单元。
        registry: 选项集注册表。
        notice_id: 公告主键。

    Returns:
        ApiResponse: 统一响应，data 为 `{deleted: true}`。
    """
    service = _service(uow, registry)
    async with uow.begin():
        deleted = await service.delete(notice_id)
    return ApiResponse.ok({"deleted": deleted})


@router.get("/{notice_id}", dependencies=[_PREPARE_PERMISSION])
async def get_notice_detail(
    uow: UowDep,
    registry: RegistryDep,
    checker: CheckerDep,
    notice_id: int,
    locale: LocaleQuery = None,
    accept_language: AcceptLanguage = None,
) -> ApiResponse:
    """公告详情（发布中对全员可见；草稿 / 下线仅 `notice:update` 可见）。

    Args:
        uow: 请求级工作单元。
        registry: 选项集注册表。
        checker: 权限检查器。
        notice_id: 公告主键。
        locale: 显式语言。
        accept_language: 请求头语言。

    Returns:
        ApiResponse: 统一响应，data 为公告详情。
    """
    service = _service(uow, registry)
    async with uow.begin():
        detail = await service.detail(
            notice_id,
            now=_now(),
            locale=_resolve_locale(locale, accept_language),
            can_manage=checker.check("notice:update"),
        )
    return ApiResponse.ok(detail)


@router.post("/{notice_id}/read")
async def mark_notice_read(
    uow: UowDep,
    registry: RegistryDep,
    notice_id: int,
) -> ApiResponse:
    """提交已读回执（幂等；仅发布中公告）。

    Args:
        uow: 请求级工作单元。
        registry: 选项集注册表。
        notice_id: 公告主键。

    Returns:
        ApiResponse: 统一响应，data 为回执。
    """
    service = _service(uow, registry)
    async with uow.begin():
        receipt = await service.mark_read(notice_id, now=_now())
    return ApiResponse.ok(receipt)


@router.get("/{notice_id}/read-stats", dependencies=[_REQUIRE_QUERY])
async def get_notice_read_stats(
    uow: UowDep,
    registry: RegistryDep,
    audience: AudienceDep,
    notice_id: int,
) -> ApiResponse:
    """已读统计（应读 / 已读 / 未读人数）。

    Args:
        uow: 请求级工作单元。
        registry: 选项集注册表。
        audience: 应读人数读取器。
        notice_id: 公告主键。

    Returns:
        ApiResponse: 统一响应，data 为统计结果。
    """
    service = _service(uow, registry)
    async with uow.begin():
        stats = await service.read_stats(notice_id, audience_reader=audience)
    return ApiResponse.ok(stats)


@internal_router.post("/expire")
async def expire_notices(
    uow: UowDep,
    registry: RegistryDep,
    req: NoticeExpireRequest,
) -> ApiResponse:
    """过期扫描：批量置下线并发布 `offline` 事件（服务间调用）。

    Args:
        uow: 请求级工作单元。
        registry: 选项集注册表。
        req: 扫描请求（单批上限 / 基准时间）。

    Returns:
        ApiResponse: 统一响应，data 为 `{expired}`。
    """
    service = _service(uow, registry)
    async with uow.begin():
        expired = await service.expire(
            now=req.now or _now(),
            limit=req.limit,
            tenant_id=get_current_tenant_id(),
        )
    return ApiResponse.ok(NoticeExpireResult(expired=expired))
