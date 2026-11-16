"""内部发送端点：`BaseNotifier` 的 `http` 实现调用（服务间，能力 `notification.send`）。

- 邮件：接收已渲染正文（raw），可直接发送；
- 短信：必须带 `template_code` + `params`（云厂商只允许模板短信）；
- 事务性消息默认跳过渠道开关与免打扰；租户由服务 JWT 解析。
"""

from typing import Annotated

from fastapi import Depends

from bms_core.api.base import BaseRouter
from bms_core.api.capability import require_capability_or_service
from bms_core.core.concurrent import ConcurrentStableFrozenDict
from bms_core.core.exceptions import ParamError
from bms_core.db.session import get_uow
from bms_core.db.unit_of_work import DbUnitOfWork
from bms_core.schemas.common import ApiResponse
from bms_notification.domains.notification.api.support import OutboundDep
from bms_notification.domains.notification.schemas.internal_send import InternalSendRequest, InternalSendResult
from bms_notification.domains.notification.services.outbound import CHANNEL_EMAIL, CHANNEL_SMS, DispatchRequest

router = BaseRouter(
    key="mail_internal",
    prefix="/mail/internal",
    tags=["mail-internal"],
    dependencies=[Depends(require_capability_or_service("notification.send", "identity"))],
)

UowDep = Annotated[DbUnitOfWork, Depends(get_uow)]


@router.post("/send")
async def internal_send(
    uow: UowDep, dispatcher: OutboundDep, req: InternalSendRequest
) -> ApiResponse[InternalSendResult]:
    """内部发送（邮件 raw / 短信模板）。

    Args:
        uow: 请求级工作单元。
        dispatcher: 外发调度服务。
        req: 内部发送请求。

    Returns:
        ApiResponse: 受理结果。

    Raises:
        ParamError: 短信缺模板 / 邮件正文为空（10001）。
    """
    if req.channel == CHANNEL_SMS and not req.template_code:
        raise ParamError("短信发送必须提供 template_code")
    if req.channel == CHANNEL_EMAIL and not req.content.strip():
        raise ParamError("邮件正文不得为空")
    dispatch_request = DispatchRequest(
        channel=req.channel,
        template_code=req.template_code,
        params=ConcurrentStableFrozenDict(dict(req.params)),
        user_id=int(req.user_id) if req.user_id is not None else None,
        recipient=req.recipient,
        transactional=req.transactional,
        title=req.title,
        content=req.content,
        html=req.html,
        idempotency_key=req.idempotency_key,
        record_skipped_when_disabled=False,
        fail_on_missing_recipient=True,
    )
    async with uow.begin():
        outcome = await dispatcher.dispatch(dispatch_request)
    if outcome.log_id is None:
        raise ParamError("内部发送未生成记录")
    return ApiResponse.ok(InternalSendResult(log_id=outcome.log_id, status=outcome.status))
