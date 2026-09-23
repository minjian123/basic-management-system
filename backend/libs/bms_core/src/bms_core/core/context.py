"""core 层请求上下文占位：跨切面的上下文变量。

- `current_user_id`：供审计字段（created_by / updated_by）使用，占位默认 None。
- `current_tenant`：当前租户编码（审计 / 日志 / 同库过滤统一来源），占位默认 None。
- `read_only`：只读上下文标记（读写分离路由依据），占位默认 False。
- `current_masker`：当前请求的掩码器（`BaseSchema` 序列化期掩码依据），占位默认 None。
- `current_trace_id` / `current_span_id`：链路追踪上下文（日志关联与链路贯穿依据），占位默认 None。
- 认证 / 日志 / 多租户 / 脱敏 / 链路阶段接入后设置对应变量。
"""

from contextvars import ContextVar, Token
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from bms_core.db.tenant import TenantContext
    from bms_core.masking.base import BaseMasker

current_user_id: ContextVar[int | None] = ContextVar("current_user_id", default=None)
current_tenant: ContextVar[str | None] = ContextVar("current_tenant", default=None)
current_tenant_context_var: ContextVar[TenantContext | None] = ContextVar("current_tenant_context", default=None)
"""当前租户完整上下文（编码 / 库键 / 主键 / 状态；租户全局中间件设置）。"""
read_only: ContextVar[bool] = ContextVar("read_only", default=False)
current_masker: ContextVar[BaseMasker | None] = ContextVar("current_masker", default=None)
current_trace_id: ContextVar[str | None] = ContextVar("current_trace_id", default=None)
current_span_id: ContextVar[str | None] = ContextVar("current_span_id", default=None)
current_request_id: ContextVar[str | None] = ContextVar("current_request_id", default=None)
current_client_ip: ContextVar[str | None] = ContextVar("current_client_ip", default=None)


def set_current_user_id(user_id: int | None) -> Token[int | None]:
    """设置当前用户上下文。

    Args:
        user_id: 用户标识（可信边缘身份解析所得）。

    Returns:
        Token[int | None]: 复位令牌。
    """
    return current_user_id.set(user_id)


def reset_current_user_id(token: Token[int | None]) -> None:
    """复位当前用户上下文。

    Args:
        token: `set_current_user_id` 返回的令牌。
    """
    current_user_id.reset(token)


def get_current_user_id() -> int | None:
    """当前用户标识。

    Returns:
        int | None: 用户标识；无则 None。
    """
    return current_user_id.get()


def set_current_tenant(tenant_code: str | None) -> Token[str | None]:
    """设置当前租户上下文。

    Args:
        tenant_code: 租户编码。

    Returns:
        Token[str | None]: 复位令牌。
    """
    return current_tenant.set(tenant_code)


def reset_current_tenant(token: Token[str | None]) -> None:
    """复位当前租户上下文。

    Args:
        token: `set_current_tenant` 返回的令牌。
    """
    current_tenant.reset(token)


def get_current_tenant() -> str | None:
    """当前租户编码。

    Returns:
        str | None: 租户编码；无则 None。
    """
    return current_tenant.get()


def set_tenant_context(context: TenantContext | None) -> Token[TenantContext | None]:
    """设置当前租户完整上下文。

    Args:
        context: 租户上下文；None 表示清除。

    Returns:
        Token: 复位令牌。
    """
    return current_tenant_context_var.set(context)


def reset_tenant_context(token: Token[TenantContext | None]) -> None:
    """复位当前租户完整上下文。

    Args:
        token: `set_tenant_context` 返回的令牌。
    """
    current_tenant_context_var.reset(token)


def get_tenant_context() -> TenantContext | None:
    """当前租户完整上下文。

    Returns:
        TenantContext | None: 租户上下文；无则 None。
    """
    return current_tenant_context_var.get()


def set_read_only(value: bool = True) -> Token[bool]:
    """设置只读上下文标记。

    Args:
        value: 是否只读。

    Returns:
        Token[bool]: 复位令牌（供 `reset_read_only` 使用）。
    """
    return read_only.set(value)


def reset_read_only(token: Token[bool]) -> None:
    """复位只读上下文标记。

    Args:
        token: `set_read_only` 返回的令牌。
    """
    read_only.reset(token)


def is_read_only() -> bool:
    """当前是否处于只读上下文。

    Returns:
        bool: 只读 True。
    """
    return read_only.get()


def set_current_masker(masker: BaseMasker | None) -> Token[BaseMasker | None]:
    """设置当前请求的掩码器。

    Args:
        masker: 掩码器实例；None 表示清除（序列化直通）。

    Returns:
        Token[BaseMasker | None]: 复位令牌。
    """
    return current_masker.set(masker)


def reset_current_masker(token: Token[BaseMasker | None]) -> None:
    """复位当前掩码器上下文。

    Args:
        token: `set_current_masker` 返回的令牌。
    """
    current_masker.reset(token)


def get_current_masker() -> BaseMasker | None:
    """当前请求的掩码器。

    Returns:
        BaseMasker | None: 掩码器；未注入则为 None（序列化直通）。
    """
    return current_masker.get()


def set_current_trace_id(trace_id: str | None) -> Token[str | None]:
    """设置当前链路 id。

    Args:
        trace_id: 链路 id；None 表示清除。

    Returns:
        Token[str | None]: 复位令牌。
    """
    return current_trace_id.set(trace_id)


def reset_current_trace_id(token: Token[str | None]) -> None:
    """复位当前链路 id 上下文。

    Args:
        token: `set_current_trace_id` 返回的令牌。
    """
    current_trace_id.reset(token)


def get_current_trace_id() -> str | None:
    """当前链路 id。

    Returns:
        str | None: 链路 id；不在链路内为 None。
    """
    return current_trace_id.get()


def set_current_span_id(span_id: str | None) -> Token[str | None]:
    """设置当前 span id。

    Args:
        span_id: span id；None 表示清除。

    Returns:
        Token[str | None]: 复位令牌。
    """
    return current_span_id.set(span_id)


def reset_current_span_id(token: Token[str | None]) -> None:
    """复位当前 span id 上下文。

    Args:
        token: `set_current_span_id` 返回的令牌。
    """
    current_span_id.reset(token)


def get_current_span_id() -> str | None:
    """当前 span id。

    Returns:
        str | None: span id；不在 span 内为 None。
    """
    return current_span_id.get()


def set_current_request_id(request_id: str | None) -> Token[str | None]:
    """设置当前请求 id。

    Args:
        request_id: 请求 id；None 表示清除。

    Returns:
        Token[str | None]: 复位令牌。
    """
    return current_request_id.set(request_id)


def reset_current_request_id(token: Token[str | None]) -> None:
    """复位当前请求 id 上下文。

    Args:
        token: `set_current_request_id` 返回的令牌。
    """
    current_request_id.reset(token)


def get_current_request_id() -> str | None:
    """当前请求 id。

    Returns:
        str | None: 请求 id；不在请求内为 None。
    """
    return current_request_id.get()


def set_current_client_ip(client_ip: str | None) -> Token[str | None]:
    """设置当前请求来源 IP。

    Args:
        client_ip: 来源 IP；None 表示清除。

    Returns:
        Token[str | None]: 复位令牌。
    """
    return current_client_ip.set(client_ip)


def reset_current_client_ip(token: Token[str | None]) -> None:
    """复位当前来源 IP 上下文。

    Args:
        token: `set_current_client_ip` 返回的令牌。
    """
    current_client_ip.reset(token)


def get_current_client_ip() -> str | None:
    """当前请求来源 IP。

    Returns:
        str | None: 来源 IP；不在请求内为 None。
    """
    return current_client_ip.get()
