"""短信路由：模板 CRUD / 渲染测试 / 发送 / 发送记录。"""

from datetime import datetime
from typing import Annotated

from fastapi import Depends, Query

from bms_core.api.base import BaseRouter, page_query, require_auth
from bms_core.core.config import get_settings
from bms_core.db.session import get_uow
from bms_core.db.unit_of_work import DbUnitOfWork
from bms_core.optionset.base import BaseOptionSetRegistry, get_option_set_registry
from bms_core.permission.base import require_permission
from bms_core.schemas.common import ApiResponse
from bms_core.schemas.pagination import BasePageQuery, BasePageResponse
from bms_notification.domains.notification.api.support import IdempotencyKey, OutboundDep
from bms_notification.domains.notification.schemas.sms import (
    SmsLogItem,
    SmsSendRequest,
    SmsSendResult,
    SmsTemplateCreateRequest,
    SmsTemplateDetail,
    SmsTemplateListItem,
    SmsTemplateTestRequest,
    SmsTemplateTestResult,
    SmsTemplateUpdateRequest,
)
from bms_notification.domains.notification.services.sms import SmsTemplateService

router = BaseRouter(
    key="sms",
    prefix="/sms",
    tags=["sms"],
    dependencies=[Depends(require_auth)],
)

UowDep = Annotated[DbUnitOfWork, Depends(get_uow)]
RegistryDep = Annotated[BaseOptionSetRegistry, Depends(get_option_set_registry)]
PageDep = Annotated[BasePageQuery, Depends(page_query)]
StartAt = Annotated[datetime | None, Query(description="创建时间下限（UTC）")]
EndAt = Annotated[datetime | None, Query(description="创建时间上限（UTC）")]

_REQUIRE_QUERY = Depends(require_permission("mail:query"))
_REQUIRE_SEND = Depends(require_permission("mail:send"))


def _service(uow: UowDep, registry: RegistryDep) -> SmsTemplateService:
    """构造短信模板服务。"""
    settings = get_settings()
    return SmsTemplateService(
        uow.session,
        option_sets=registry,
        sms_settings=settings.sms,
        render_timeout_seconds=settings.mail.render_timeout_seconds,
    )


@router.get("/templates", dependencies=[_REQUIRE_QUERY])
async def list_sms_templates(
    uow: UowDep,
    registry: RegistryDep,
    page: PageDep,
    keyword: Annotated[str | None, Query(description="code / 名称关键字")] = None,
    status: Annotated[str | None, Query(description="状态（enabled/disabled）")] = None,
    channel: Annotated[str | None, Query(description="渠道（aliyun/tencent）")] = None,
    scene: Annotated[str | None, Query(description="场景（选项集值）")] = None,
    source: Annotated[str | None, Query(description="来源（tenant/builtin）")] = None,
) -> ApiResponse[BasePageResponse[SmsTemplateListItem]]:
    """短信模板合并列表。"""
    service = _service(uow, registry)
    async with uow.begin():
        result = await service.list(
            page=page.page,
            size=page.size,
            keyword=keyword,
            status=status,
            channel=channel,
            scene=scene,
            source=source,
        )
    return ApiResponse.ok(result)


@router.post("/templates", dependencies=[_REQUIRE_SEND])
async def create_sms_template(
    uow: UowDep, registry: RegistryDep, req: SmsTemplateCreateRequest
) -> ApiResponse[SmsTemplateDetail]:
    """新建短信模板。"""
    service = _service(uow, registry)
    async with uow.begin():
        detail = await service.create(req)
    return ApiResponse.ok(detail)


@router.get("/logs", dependencies=[_REQUIRE_QUERY])
async def list_sms_logs(
    uow: UowDep,
    registry: RegistryDep,
    page: PageDep,
    status: Annotated[str | None, Query(description="状态")] = None,
    channel: Annotated[str | None, Query(description="渠道")] = None,
    scene: Annotated[str | None, Query(description="场景")] = None,
    template_code: Annotated[str | None, Query(description="模板 code")] = None,
    recipient: Annotated[str | None, Query(description="收件手机号（模糊）")] = None,
    user_id: Annotated[int | None, Query(description="收件用户主键")] = None,
    start_at: StartAt = None,
    end_at: EndAt = None,
) -> ApiResponse[BasePageResponse[SmsLogItem]]:
    """短信发送记录列表。"""
    service = _service(uow, registry)
    async with uow.begin():
        result = await service.list_logs(
            page=page.page,
            size=page.size,
            status=status,
            channel=channel,
            scene=scene,
            template_code=template_code,
            recipient=recipient,
            user_id=user_id,
            start_at=start_at,
            end_at=end_at,
        )
    return ApiResponse.ok(result)


@router.post("/send", dependencies=[_REQUIRE_SEND])
async def send_sms(
    uow: UowDep,
    dispatcher: OutboundDep,
    req: SmsSendRequest,
    idempotency_key: IdempotencyKey = None,
) -> ApiResponse[SmsSendResult]:
    """发送短信（异步：落日志 + 提交作业；渠道取配置）。"""
    async with uow.begin():
        outcome = await dispatcher.dispatch(_dispatch_request(req, idempotency_key=idempotency_key))
    if outcome.log_id is None:
        raise RuntimeError("短信发送未生成记录")
    return ApiResponse.ok(SmsSendResult(log_id=outcome.log_id, status=outcome.status))


@router.get("/templates/{template_id}", dependencies=[_REQUIRE_QUERY])
async def get_sms_template(uow: UowDep, registry: RegistryDep, template_id: int) -> ApiResponse[SmsTemplateDetail]:
    """短信模板详情。"""
    service = _service(uow, registry)
    async with uow.begin():
        detail = await service.detail(template_id)
    return ApiResponse.ok(detail)


@router.put("/templates/{template_id}", dependencies=[_REQUIRE_SEND])
async def update_sms_template(
    uow: UowDep, registry: RegistryDep, template_id: int, req: SmsTemplateUpdateRequest
) -> ApiResponse[SmsTemplateDetail]:
    """编辑短信模板（code / 渠道不可改）。"""
    service = _service(uow, registry)
    async with uow.begin():
        detail = await service.update(template_id, req)
    return ApiResponse.ok(detail)


@router.delete("/templates/{template_id}", dependencies=[_REQUIRE_SEND])
async def delete_sms_template(uow: UowDep, registry: RegistryDep, template_id: int) -> ApiResponse:
    """软删除短信模板。"""
    service = _service(uow, registry)
    async with uow.begin():
        deleted = await service.delete(template_id)
    return ApiResponse.ok({"deleted": deleted})


@router.post("/templates/{template_id}/test", dependencies=[_REQUIRE_SEND])
async def test_sms_template(
    uow: UowDep, registry: RegistryDep, template_id: int, req: SmsTemplateTestRequest
) -> ApiResponse[SmsTemplateTestResult]:
    """按 id 沙箱渲染（不发送）。"""
    service = _service(uow, registry)
    async with uow.begin():
        code, content = await service.test(template_id, params=req.params)
    return ApiResponse.ok(SmsTemplateTestResult(code=code, content=content))


def _dispatch_request(req: SmsSendRequest, *, idempotency_key: str | None):
    """短信发送请求 → 外发调度请求。"""
    from bms_core.core.concurrent import ConcurrentStableFrozenDict
    from bms_notification.domains.notification.services.outbound import CHANNEL_SMS, DispatchRequest

    return DispatchRequest(
        channel=CHANNEL_SMS,
        template_code=req.template_code,
        params=ConcurrentStableFrozenDict(dict(req.params)),
        user_id=int(req.user_id) if req.user_id is not None else None,
        recipient=req.recipient,
        transactional=req.transactional,
        idempotency_key=idempotency_key,
        record_skipped_when_disabled=True,
        fail_on_missing_recipient=True,
    )
