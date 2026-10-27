"""内部授权视图（07B `02_04`）：`/api/v1/platform/internal/capability-grants`（服务间读取）。

- **用途**：提供方取「谁能调我」（`provider=<业务域>`）、消费方取出站授权（`consumer=<服务键>`），
  二者**二选一**；授权表只建在平台库，其他进程经本端点拉取并缓存（基座 `ensure_grant_view`）；
- **鉴权**：双模 `require_auth_or_service`——服务身份只许读「本服务承载的业务域」或「本服务作为消费方」
  的记录（越界 403）；登录态需 `capability-grant:query` 权限码（运维排障）；
- **暴露面**：只回「能力 × 消费方 + 提供方业务域 / 访问面类别 + 有效期」，不含 `note` / `granted_by`
  等运营字段（运营面走 `/api/v1/capability-grants`）；
- 不是目录出口：目录出口面向服务与前端取址，本端点面向「授权判定」，判据不同（架构 38 §9）。
"""

from typing import Annotated

from fastapi import Depends, Query, Request

from bms_core.api.base import AuthContext, BaseRouter, require_auth_or_service
from bms_core.api.deps import get_platform_read_db
from bms_core.audit.base import AuditCapturer, get_audit_capturer
from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.exceptions import ParamError, PermissionError
from bms_core.db.session import DbSession
from bms_core.permission.base import require_permission
from bms_core.schemas.common import ApiResponse
from bms_core.services.module_registry import collaboration_catalog_view, domain_service_view
from bms_platform.domains.platform_registry.schemas.capability_grant import (
    CapabilityGrantViewItem,
    CapabilityGrantViewResponse,
)
from bms_platform.domains.platform_registry.services.capability_grant import CapabilityGrantService

router = BaseRouter(
    key="platform_internal_capability_grants",
    prefix="/platform/internal/capability-grants",
    tags=["platform-internal"],
    dependencies=[Depends(require_auth_or_service)],
)

ReadDbDep = Annotated[DbSession, Depends(get_platform_read_db)]
AuditDep = Annotated[AuditCapturer, Depends(get_audit_capturer)]
ContextDep = Annotated[AuthContext, Depends(require_auth_or_service)]
ProviderQuery = Annotated[str | None, Query(description="提供方业务域（入站维度；与 consumer 二选一）")]
ConsumerQuery = Annotated[str | None, Query(description="消费方服务键（出站维度；与 provider 二选一）")]


@router.get("")
async def capability_grant_view(
    request: Request,
    session: ReadDbDep,
    context: ContextDep,
    audit: AuditDep,
    provider: ProviderQuery = None,
    consumer: ConsumerQuery = None,
) -> ApiResponse:
    """按维度下发授权视图（`provider` / `consumer` 二选一）。

    Args:
        request: 请求对象（登录态分支的权限码校验用）。
        session: 平台库只读会话。
        context: 入站身份（服务身份或登录态）。
        audit: 审计捕获器（占位注入；只读端点不产生审计事件）。
        provider: 提供方业务域（入站维度）。
        consumer: 消费方服务键（出站维度）。

    Returns:
        ApiResponse: 统一响应，data 为 `{provider, consumer, grants}`。

    Raises:
        ParamError: `provider` / `consumer` 未二选一（10001）。
        PermissionError: 服务身份越界读取，或登录态缺少权限码（30001 / 403）。
    """
    if (provider is None) == (consumer is None):
        raise ParamError("授权视图须且只须给出 provider 或 consumer 之一")
    if context.source == "service":
        _ensure_scope(context.service_identity or "", provider=provider, consumer=consumer)
    else:
        await require_permission("capability-grant:query")(request)
    grants = await CapabilityGrantService(session, audit=audit).view(provider=provider, consumer=consumer)
    items: ConcurrentStableList[CapabilityGrantViewItem] = ConcurrentStableList()
    meta = ConcurrentStableDict((record.name, record) for record in collaboration_catalog_view())
    for grant in grants:
        record = meta.get(grant.capability_name)
        items.add(
            CapabilityGrantViewItem(
                capability_name=grant.capability_name,
                consumer_key=grant.consumer_key,
                domain=record.domain if record is not None else "",
                kind=record.kind if record is not None else "",
                expire_at=grant.expire_at,
            )
        )
    return ApiResponse.ok(CapabilityGrantViewResponse(provider=provider, consumer=consumer, grants=items))


def _ensure_scope(service_key: str, *, provider: str | None, consumer: str | None) -> None:
    """校验服务身份的读取范围（只许读自己承载的域 / 自己是消费方的记录）。

    Args:
        service_key: 调用方服务标识（服务 JWT 签发方）。
        provider: 提供方业务域（入站维度）。
        consumer: 消费方服务键（出站维度）。

    Raises:
        PermissionError: 跨域 / 跨消费方读取（30001 / 403）。
    """
    if consumer is not None:
        if consumer != service_key:
            raise PermissionError(f"服务身份只能读取自身作为消费方的授权：{service_key}")
        return
    carrier = domain_service_view().get(provider or "")
    if carrier != service_key:
        raise PermissionError(f"服务身份 {service_key} 不承载业务域：{provider}")
