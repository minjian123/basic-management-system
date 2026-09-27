"""认证与身份服务端点层：请求租户解析（登录 / 找回等免登录链路共用）。"""

from bms_core.db.tenant import TenantContext, TenantLookup, TenantNotFoundError


async def resolve_request_tenant(
    body_tenant: str | None,
    context_tenant: TenantContext | None,
    source: TenantLookup,
) -> TenantContext:
    """解析生效租户：请求上下文优先，无则 body 指定，再校验存在。

    Args:
        body_tenant: 请求体携带的租户编码（可选；不一致时以之为准）。
        context_tenant: 请求上下文（子域名 / `X-Tenant-ID`）租户。
        source: 租户源（按编码校验存在）。

    Returns:
        TenantContext: 生效租户上下文。

    Raises:
        TenantNotFoundError: 无任何租户来源（404）。
    """
    if body_tenant:
        return await source.by_code(body_tenant)
    if context_tenant is not None:
        return context_tenant
    raise TenantNotFoundError("未提供租户标识")
