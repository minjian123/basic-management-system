"""语言包接口：`/api/v1/i18n/messages`（运行时下发 / 维护列表 / 批量保存）与缓存失效。

- **鉴权**：模块级 `require_auth`；下发接口登录即可（前端初始化必须），维护列表挂 `i18n:query`，
  批量保存与缓存失效挂 `i18n:manage`。
- **下发**：`?locale=` 优先、缺省按 `Accept-Language`；默认语言包打底 + 请求语言覆盖（前端零配置兜底）。
- **批量保存**：差异三段（`adds` / `updates` / `deletes`）+ `Idempotency-Key` 幂等 + 行级乐观锁。
- **失效**：保存内部已失效；`PUT /i18n/cache/invalidate` 供运维 / 前端在异常场景手动触发。
"""

from __future__ import annotations

from typing import Annotated, cast

from fastapi import Depends, Header, Query

from bms_core.api.base import BaseRouter, page_query, require_auth
from bms_core.api.deps import (
    get_audit_capturer,
    get_i18n_cache_region,
    get_i18n_invalidator,
    get_idempotency_store,
    get_locale_registry,
    get_translator,
    get_uow,
)
from bms_core.audit.base import AuditCapturer
from bms_core.db.session import DbSession
from bms_core.db.unit_of_work import UnitOfWork
from bms_core.i18n.base import BaseTranslator
from bms_core.i18n.cache import I18nCacheRegion
from bms_core.i18n.invalidate import I18nInvalidator
from bms_core.i18n.registry import BaseLocaleRegistry
from bms_core.idempotency.base import IDEMPOTENCY_HEADER, IdempotencyStore
from bms_core.permission.base import require_permission
from bms_core.schemas.common import ApiResponse
from bms_core.schemas.pagination import BasePageQuery
from bms_platform.domains.i18n.repositories.locale import LocaleRepository
from bms_platform.domains.i18n.repositories.message import MessageRepository
from bms_platform.domains.i18n.schemas.i18n import (
    CacheInvalidateResult,
    MessagePage,
    MessageSaveRequest,
    MessageSaveResult,
    MessagesPayload,
)
from bms_platform.domains.i18n.services.message import MessageAdminService

router = BaseRouter(
    key="i18n_messages",
    prefix="/i18n",
    tags=["i18n"],
    dependencies=[Depends(require_auth)],
)

_REQUIRE_QUERY = Depends(require_permission("i18n:query"))
_REQUIRE_MANAGE = Depends(require_permission("i18n:manage"))

UowDep = Annotated[UnitOfWork, Depends(get_uow)]
PageDep = Annotated[BasePageQuery, Depends(page_query)]
TranslatorDep = Annotated[BaseTranslator, Depends(get_translator)]
RegistryDep = Annotated[BaseLocaleRegistry, Depends(get_locale_registry)]
CacheDep = Annotated[I18nCacheRegion, Depends(get_i18n_cache_region)]
InvalidatorDep = Annotated[I18nInvalidator, Depends(get_i18n_invalidator)]
AuditDep = Annotated[AuditCapturer, Depends(get_audit_capturer)]
IdempotencyDep = Annotated[IdempotencyStore, Depends(get_idempotency_store)]
LocaleQuery = Annotated[str | None, Query(description="语言标识（缺省按 Accept-Language 解析）")]
AcceptLanguageHeader = Annotated[str | None, Header(alias="Accept-Language", description="请求语言")]
IdempotencyHeader = Annotated[str | None, Header(alias=IDEMPOTENCY_HEADER, description="幂等键（缺省按变更集派生）")]
KeywordQuery = Annotated[str | None, Query(description="关键字（文案 key 模糊匹配）")]
ModuleQuery = Annotated[str | None, Query(description="模块前缀（key 首段，如 common）")]
LocaleFilterQuery = Annotated[str | None, Query(description="语言精确匹配")]
MissingOnlyQuery = Annotated[bool, Query(description="只看缺失（该语言无文案）")]


def _service(
    uow: UnitOfWork,
    translator: BaseTranslator,
    registry: BaseLocaleRegistry,
    cache: I18nCacheRegion,
    invalidator: I18nInvalidator,
    audit: AuditCapturer,
    idempotency: IdempotencyStore,
) -> MessageAdminService:
    """构造语言包管理服务（请求级租户库会话 + 能力域 + 失效器 + 审计 + 幂等）。

    Args:
        uow: 请求级工作单元（platform 服务租户库）。
        translator: 翻译能力域。
        registry: 语言清单能力域。
        cache: 国际化缓存域。
        invalidator: 国际化缓存失效器。
        audit: 审计捕获器。
        idempotency: 幂等存储。

    Returns:
        MessageAdminService: 管理服务实例。
    """
    session = cast("DbSession", uow.session)
    return MessageAdminService(
        MessageRepository(session),
        LocaleRepository(session),
        uow,
        translator=translator,
        registry=registry,
        cache=cache,
        invalidator=invalidator,
        audit=audit,
        idempotency=idempotency,
    )


@router.get("/messages")
async def get_messages(
    uow: UowDep,
    translator: TranslatorDep,
    registry: RegistryDep,
    cache: CacheDep,
    invalidator: InvalidatorDep,
    audit: AuditDep,
    idempotency: IdempotencyDep,
    locale: LocaleQuery = None,
    accept_language: AcceptLanguageHeader = None,
) -> ApiResponse[MessagesPayload]:
    """语言包运行时下发（登录即可访问）。

    `locale` 显式指定优先、缺省按 `Accept-Language` 解析；默认语言包打底、请求语言覆盖，
    因此缺翻译时不会返回 key 原文。响应含 `locale` / `fallback` / `version` / `messages`。
    """
    service = _service(uow, translator, registry, cache, invalidator, audit, idempotency)
    return ApiResponse[MessagesPayload](data=await service.payload(locale=locale, accept_language=accept_language))


@router.get("/messages/manage", dependencies=[_REQUIRE_QUERY])
async def list_messages(
    uow: UowDep,
    page: PageDep,
    translator: TranslatorDep,
    registry: RegistryDep,
    cache: CacheDep,
    invalidator: InvalidatorDep,
    audit: AuditDep,
    idempotency: IdempotencyDep,
    keyword: KeywordQuery = None,
    module: ModuleQuery = None,
    locale: LocaleFilterQuery = None,
    missing_only: MissingOnlyQuery = False,
) -> ApiResponse[MessagePage]:
    """语言包维护列表（需要 i18n:query）。

    支持按文案 key 关键字、模块前缀、语言与「只看缺失」筛选；`module` 由 key 首段派生。
    """
    service = _service(uow, translator, registry, cache, invalidator, audit, idempotency)
    result = await service.page(
        page=page.page,
        size=page.size,
        keyword=keyword,
        module=module,
        locale=locale,
        missing_only=missing_only,
    )
    return ApiResponse[MessagePage](data=result)


@router.put("/messages", dependencies=[_REQUIRE_MANAGE])
async def save_messages(
    uow: UowDep,
    translator: TranslatorDep,
    registry: RegistryDep,
    cache: CacheDep,
    invalidator: InvalidatorDep,
    audit: AuditDep,
    idempotency: IdempotencyDep,
    request: MessageSaveRequest,
    idempotency_key: IdempotencyHeader = None,
) -> ApiResponse[MessageSaveResult]:
    """语言包批量保存（需要 i18n:manage）。

    差异三段：`adds` 命中已存在 `(key, locale)` 转更新；`updates` 必须带行 `version`；
    `deletes` 仅允许删租户自建行。保存后按受影响语言失效缓存，响应含失效后的版本号。
    """
    service = _service(uow, translator, registry, cache, invalidator, audit, idempotency)
    return ApiResponse[MessageSaveResult](data=await service.save(request, idempotency_key=idempotency_key))


@router.put("/cache/invalidate", dependencies=[_REQUIRE_MANAGE])
async def invalidate_cache(
    uow: UowDep,
    translator: TranslatorDep,
    registry: RegistryDep,
    cache: CacheDep,
    invalidator: InvalidatorDep,
    audit: AuditDep,
    idempotency: IdempotencyDep,
) -> ApiResponse[CacheInvalidateResult]:
    """语言包缓存主动失效（需要 i18n:manage）。

    失效「清单键 + 全部语言包键」并递增版本、刷新进程内快照；Redis 不可用时 `degraded=true` 且仍返回 200。
    """
    service = _service(uow, translator, registry, cache, invalidator, audit, idempotency)
    return ApiResponse[CacheInvalidateResult](data=await service.invalidate_cache())
