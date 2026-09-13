"""core 层请求上下文占位：跨切面的上下文变量。

- `current_user_id`：供审计字段（created_by / updated_by）使用，占位默认 None。
- `current_tenant`：当前租户编码（审计 / 日志 / 同库过滤统一来源），占位默认 None。
- `read_only`：只读上下文标记（读写分离路由依据），占位默认 False。
- `current_masker`：当前请求的掩码器（`BaseSchema` 序列化期掩码依据），占位默认 None。
- 认证 / 日志 / 多租户 / 脱敏阶段接入后设置对应变量。
"""

from contextvars import ContextVar, Token
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.masking.base import BaseMasker

current_user_id: ContextVar[int | None] = ContextVar("current_user_id", default=None)
current_tenant: ContextVar[str | None] = ContextVar("current_tenant", default=None)
read_only: ContextVar[bool] = ContextVar("read_only", default=False)
current_masker: ContextVar[BaseMasker | None] = ContextVar("current_masker", default=None)


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
