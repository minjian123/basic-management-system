"""邮件路由：模板 CRUD / 预览测试 / 发送 / 发送记录。"""

from datetime import datetime
from typing import Annotated

from fastapi import Depends, Query

from bms_core.api.base import BaseRouter, page_query, require_auth
from bms_core.core.config import get_settings
from bms_core.db.session import get_uow
from bms_core.db.unit_of_work import DbUnitOfWork
from bms_core.permission.base import require_permission
from bms_core.schemas.common import ApiResponse
from bms_core.schemas.pagination import BasePageQuery, BasePageResponse
from bms_notification.domains.notification.api.support import (
    AcceptLanguage,
    IdempotencyKey,
    LocaleQuery,
    OutboundDep,
    resolve_locale,
)
from bms_notification.domains.notification.schemas.mail import (
    MailLogItem,
    MailSendRequest,
    MailSendResult,
    MailTemplateCreateRequest,
    MailTemplateDetail,
    MailTemplateListItem,
    MailTemplatePreviewRequest,
    MailTemplatePreviewResult,
    MailTemplateTestRequest,
    MailTemplateTestResult,
    MailTemplateUpdateRequest,
)
from bms_notification.domains.notification.services.mail import MailTemplateService

router = BaseRouter(
    key="mail",
    prefix="/mail",
    tags=["mail"],
    dependencies=[Depends(require_auth)],
)

UowDep = Annotated[DbUnitOfWork, Depends(get_uow)]
PageDep = Annotated[BasePageQuery, Depends(page_query)]
StartAt = Annotated[datetime | None, Query(description="创建时间下限（UTC）")]
EndAt = Annotated[datetime | None, Query(description="创建时间上限（UTC）")]

_REQUIRE_QUERY = Depends(require_permission("mail:query"))
_REQUIRE_SEND = Depends(require_permission("mail:send"))


def _service(uow: UowDep) -> MailTemplateService:
    """构造邮件模板服务。"""
    return MailTemplateService(uow.session, render_timeout_seconds=get_settings().mail.render_timeout_seconds)


@router.get("/templates", dependencies=[_REQUIRE_QUERY])
async def list_mail_templates(
    uow: UowDep,
    page: PageDep,
    locale: LocaleQuery = None,
    accept_language: AcceptLanguage = None,
    keyword: Annotated[str | None, Query(description="code / 名称关键字")] = None,
    status: Annotated[str | None, Query(description="状态（enabled/disabled）")] = None,
    source: Annotated[str | None, Query(description="来源（tenant/builtin）")] = None,
) -> ApiResponse[BasePageResponse[MailTemplateListItem]]:
    """邮件模板合并列表。"""
    service = _service(uow)
    async with uow.begin():
        result = await service.list(
            page=page.page,
            size=page.size,
            locale=resolve_locale(locale, accept_language),
            keyword=keyword,
            status=status,
            source=source,
        )
    return ApiResponse.ok(result)


@router.post("/templates/preview", dependencies=[_REQUIRE_SEND])
async def preview_mail_template(
    uow: UowDep,
    req: MailTemplatePreviewRequest,
    locale: LocaleQuery = None,
    accept_language: AcceptLanguage = None,
) -> ApiResponse[MailTemplatePreviewResult]:
    """按 code 沙箱渲染（含内置默认；不发送）。"""
    service = _service(uow)
    async with uow.begin():
        subject, content = await service.preview(
            req.code,
            params=req.params,
            locale=req.locale or resolve_locale(locale, accept_language),
        )
    return ApiResponse.ok(MailTemplatePreviewResult(code=req.code, subject=subject, content=content))


@router.post("/templates", dependencies=[_REQUIRE_SEND])
async def create_mail_template(
    uow: UowDep,
    req: MailTemplateCreateRequest,
    locale: LocaleQuery = None,
    accept_language: AcceptLanguage = None,
) -> ApiResponse[MailTemplateDetail]:
    """新建邮件模板（code 与内置默认相同即覆盖）。"""
    service = _service(uow)
    async with uow.begin():
        detail = await service.create(req, request_locale=resolve_locale(locale, accept_language))
    return ApiResponse.ok(detail)


@router.get("/logs", dependencies=[_REQUIRE_QUERY])
async def list_mail_logs(
    uow: UowDep,
    page: PageDep,
    status: Annotated[str | None, Query(description="状态")] = None,
    template_code: Annotated[str | None, Query(description="模板 code")] = None,
    recipient: Annotated[str | None, Query(description="收件地址（模糊）")] = None,
    user_id: Annotated[int | None, Query(description="收件用户主键")] = None,
    start_at: StartAt = None,
    end_at: EndAt = None,
) -> ApiResponse[BasePageResponse[MailLogItem]]:
    """邮件发送记录列表。"""
    service = _service(uow)
    async with uow.begin():
        result = await service.list_logs(
            page=page.page,
            size=page.size,
            status=status,
            template_code=template_code,
            recipient=recipient,
            user_id=user_id,
            start_at=start_at,
            end_at=end_at,
        )
    return ApiResponse.ok(result)


@router.post("/send", dependencies=[_REQUIRE_SEND])
async def send_mail(
    uow: UowDep,
    dispatcher: OutboundDep,
    req: MailSendRequest,
    idempotency_key: IdempotencyKey = None,
) -> ApiResponse[MailSendResult]:
    """发送邮件（异步：落日志 + 提交作业）。"""
    async with uow.begin():
        outcome = await dispatcher.dispatch(_dispatch_request(req, idempotency_key=idempotency_key))
    if outcome.log_id is None:
        raise RuntimeError("邮件发送未生成记录")
    return ApiResponse.ok(MailSendResult(log_id=outcome.log_id, status=outcome.status))


@router.get("/templates/{template_id}", dependencies=[_REQUIRE_QUERY])
async def get_mail_template(
    uow: UowDep,
    template_id: int,
    locale: LocaleQuery = None,
    accept_language: AcceptLanguage = None,
) -> ApiResponse[MailTemplateDetail]:
    """邮件模板详情。"""
    service = _service(uow)
    async with uow.begin():
        detail = await service.detail(template_id, locale=resolve_locale(locale, accept_language))
    return ApiResponse.ok(detail)


@router.put("/templates/{template_id}", dependencies=[_REQUIRE_SEND])
async def update_mail_template(
    uow: UowDep,
    template_id: int,
    req: MailTemplateUpdateRequest,
    locale: LocaleQuery = None,
    accept_language: AcceptLanguage = None,
) -> ApiResponse[MailTemplateDetail]:
    """编辑邮件模板（code 不可改）。"""
    service = _service(uow)
    async with uow.begin():
        detail = await service.update(template_id, req, request_locale=resolve_locale(locale, accept_language))
    return ApiResponse.ok(detail)


@router.delete("/templates/{template_id}", dependencies=[_REQUIRE_SEND])
async def delete_mail_template(uow: UowDep, template_id: int) -> ApiResponse:
    """软删除邮件模板（删除覆盖后回落内置默认）。"""
    service = _service(uow)
    async with uow.begin():
        deleted = await service.delete(template_id)
    return ApiResponse.ok({"deleted": deleted})


@router.post("/templates/{template_id}/test", dependencies=[_REQUIRE_SEND])
async def test_mail_template(
    uow: UowDep,
    template_id: int,
    req: MailTemplateTestRequest,
    locale: LocaleQuery = None,
    accept_language: AcceptLanguage = None,
) -> ApiResponse[MailTemplateTestResult]:
    """按 id 沙箱渲染（不发送）。"""
    service = _service(uow)
    async with uow.begin():
        subject, content = await service.test(
            template_id,
            params=req.params,
            locale=req.locale or resolve_locale(locale, accept_language),
        )
    return ApiResponse.ok(MailTemplateTestResult(subject=subject, content=content))


def _dispatch_request(req: MailSendRequest, *, idempotency_key: str | None):
    """邮件发送请求 → 外发调度请求。"""
    from bms_core.core.concurrent import ConcurrentStableFrozenDict
    from bms_notification.domains.notification.services.outbound import CHANNEL_EMAIL, DispatchRequest

    return DispatchRequest(
        channel=CHANNEL_EMAIL,
        template_code=req.template_code,
        params=ConcurrentStableFrozenDict(dict(req.params)),
        user_id=int(req.user_id) if req.user_id is not None else None,
        recipient=req.recipient,
        locale=req.locale,
        transactional=req.transactional,
        idempotency_key=idempotency_key,
        record_skipped_when_disabled=True,
        fail_on_missing_recipient=True,
    )
