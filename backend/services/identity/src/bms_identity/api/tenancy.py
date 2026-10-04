"""认证与身份服务端点层：请求租户解析（登录 / 找回等免登录链路共用）。"""

from bms_core.core.exceptions import MultipleActiveTenantsError, NeedTenantError
from bms_core.db.tenant import TenantContext, TenantLookup, TenantNotFoundError


async def resolve_request_tenant(
    body_tenant: str | None,
    context_tenant: TenantContext | None,
    source: TenantLookup,
) -> TenantContext:
    """解析免登录链路的生效租户。

    解析顺序（唯一权威）：请求体租户（含本机记住的编码，静默携带）→ 请求上下文（子域名 /
    `X-Tenant-ID` / 令牌租户位）→ 唯一启用租户。

    - **宽松请求体**：请求体携带的租户经租户源校验，**未知即视为未提供**（含陈旧的本机记忆值），
      继续后续解析——不区分「不存在」与「未提供」，不揭示租户存在性；租户停用 / 契约不可达照常上抛。
    - **唯一启用租户兜底**：无请求体、无上下文时，恰好 1 个启用租户 → 采用该租户继续登录；
      ≥ 2 个启用租户 → 抛 `NeedTenantError`（`20007`，需要选择租户）；0 个 → 沿用既有失败语义。

    Args:
        body_tenant: 请求体携带的租户编码（可选；含本机记住的编码）。
        context_tenant: 请求上下文（子域名 / `X-Tenant-ID` / 令牌租户位）租户。
        source: 租户源（按编码校验存在、解析唯一启用租户）。

    Returns:
        TenantContext: 生效租户上下文。

    Raises:
        NeedTenantError: 存在多个启用租户、无法唯一解析（`20007` / HTTP 200）。
        TenantNotFoundError: 无任何租户来源且无启用租户（404 / 80001）。
        TenantSuspendedError: 来源命中但租户已停用（403 / 80002）。
        ServiceUnavailableError: 租户注册契约不可达（503 / 10007）。
    """
    if body_tenant:
        try:
            return await source.by_code(body_tenant)
        except TenantNotFoundError:
            # 宽松：未知请求体租户视为未提供，继续解析（不揭示租户存在性）。
            pass
    if context_tenant is not None:
        return context_tenant
    try:
        single = await source.single_active()
    except MultipleActiveTenantsError as exc:
        raise NeedTenantError("需要选择租户") from exc
    if single is not None:
        return single
    raise TenantNotFoundError("未提供租户标识")
