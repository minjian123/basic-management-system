"""多租户解析：租户上下文、解析链与请求级依赖（占位租户源）。

- 解析链优先级：子域名 → `X-Tenant-ID` 请求头 → token 内 tenant_id（认证阶段接入）。
- 本阶段为**占位**：仅 `demo` 命中，其余未知租户抛 `TenantNotFoundError`（404 / 80001）；无来源回落 demo（开发兜底）。
- `TenantContext` 经依赖注入传入 services / repositories；**禁止全局单例持有租户引擎**。
"""

from dataclasses import dataclass

from fastapi import Request

from app.core.base import BaseObject
from app.core.context import current_tenant
from app.core.exceptions import TenantNotFoundError

TENANT_EXEMPT_PATHS: tuple[str, ...] = ("/", "/docs", "/openapi.json", "/healthz", "/readyz")


@dataclass(frozen=True)
class TenantContext(BaseObject):
    """租户上下文：租户编码、数据源键与名称。"""

    tenant_code: str
    db_key: str
    name: str


DEMO_TENANT = TenantContext(tenant_code="demo", db_key="tenant_demo", name="演示租户")


def is_exempt_path(path: str) -> bool:
    """是否为租户解析豁免路径。

    Args:
        path: 请求路径。

    Returns:
        bool: 豁免 True。
    """
    return path in TENANT_EXEMPT_PATHS


def _subdomain(host: str | None) -> str | None:
    """从 Host 头提取子域名（仅三段及以上域名视为 `{tenant}.` 前缀）。

    Args:
        host: Host 头（可含端口）。

    Returns:
        str | None: 子域名；无则 None。
    """
    if not host:
        return None
    hostname = host.split(":", 1)[0]
    parts = hostname.split(".")
    return parts[0] if len(parts) >= 3 else None


def _lookup(tenant_code: str) -> TenantContext:
    """按租户编码查租户源（占位：仅 demo）。

    Args:
        tenant_code: 租户编码。

    Returns:
        TenantContext: 租户上下文。

    Raises:
        TenantNotFoundError: 未知租户。
    """
    if tenant_code == DEMO_TENANT.tenant_code:
        return DEMO_TENANT
    raise TenantNotFoundError(f"未知租户：{tenant_code}")


def resolve_tenant(
    *,
    host: str | None = None,
    header: str | None = None,
    token_tenant: str | None = None,
) -> TenantContext:
    """按解析链解析租户（子域名 → 请求头 → token）；无来源回落 demo。

    Args:
        host: Host 头。
        header: `X-Tenant-ID` 请求头。
        token_tenant: token 内 tenant_id（认证阶段接入）。

    Returns:
        TenantContext: 租户上下文。

    Raises:
        TenantNotFoundError: 来源命中但未知租户。
    """
    for candidate in (_subdomain(host), header, token_tenant):
        if candidate:
            return _lookup(candidate)
    return DEMO_TENANT


async def get_tenant(request: Request) -> TenantContext | None:
    """请求级租户依赖：豁免路径放行（None），否则解析租户。

    Args:
        request: 当前请求。

    Returns:
        TenantContext | None: 租户上下文；豁免路径为 None。

    Raises:
        TenantNotFoundError: 未知租户（全局处理器转 404 / 80001）。
    """
    if is_exempt_path(request.url.path):
        return None
    return resolve_tenant(
        host=request.headers.get("host"),
        header=request.headers.get("X-Tenant-ID"),
    )


def current_tenant_context() -> TenantContext:
    """取当前请求上下文租户（服务 / 仓储在请求外调用时的统一入口）。

    - 上下文未设置（后台任务 / 测试直调）回落演示租户；
    - 上下文租户未知（异常来源）同样回落演示租户（避免读路径因租户解析失败整体报错）。

    Returns:
        TenantContext: 租户上下文。
    """
    code = current_tenant.get()
    if not code:
        return DEMO_TENANT
    try:
        return _lookup(code)
    except TenantNotFoundError:
        return DEMO_TENANT
