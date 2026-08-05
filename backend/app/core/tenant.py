"""租户解析规则。

解析顺序（优先级从高到低，阶段一实现前两级，token 兜底阶段二认证接入后加入）：
1. X-Tenant-ID 请求头：一人多租户切换时前端携带（最终与 token 内 tenant_id 校验一致）
2. 子域名：{tenant}.bms.example.com（生产启用，dev 环境不启用）
3. access token 内 tenant_id（阶段二）

平台级请求（如 /healthz /readyz、租户开通）不经过租户解析，由中间件跳过。
"""

from __future__ import annotations

import re

from fastapi import Request

from .context import set_tenant
from .errors import CODE_TENANT_INVALID, BizError

TENANT_HEADER = "X-Tenant-ID"
TENANT_DOMAIN_SUFFIX = ".bms.example.com"
_TENANT_CODE_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{1,63}$")


def parse_tenant(request: Request) -> str | None:
    """从请求解析租户标识；平台级请求（无租户标识）返回 None，并写入上下文。"""
    tenant_code = request.headers.get(TENANT_HEADER)
    if tenant_code:
        validated = _validate(tenant_code)
        set_tenant(validated)
        return validated
    subdomain = _parse_subdomain(request)
    if subdomain:
        validated = _validate(subdomain)
        set_tenant(validated)
        return validated
    set_tenant(None)
    return None


def _parse_subdomain(request: Request) -> str | None:
    """从 Host 头解析子域名租户（仅生产泛域名 {tenant}.bms.example.com 生效）。"""
    host = request.headers.get("host", "")
    if host.endswith(TENANT_DOMAIN_SUFFIX):
        prefix = host.removesuffix(TENANT_DOMAIN_SUFFIX)
        return prefix.rsplit(".", 1)[-1] if "." in prefix else prefix
    return None


def _validate(tenant_code: str) -> str:
    """租户标识合法性校验（小写字母/数字/下划线/连字符，2~64 位）。"""
    if not _TENANT_CODE_RE.fullmatch(tenant_code):
        raise BizError(CODE_TENANT_INVALID, f"非法租户标识: {tenant_code}", status_code=400)
    return tenant_code
