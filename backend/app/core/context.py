"""core 层请求上下文占位：跨切面的上下文变量。

- `current_user_id`：供审计字段（created_by / updated_by）使用，占位默认 None。
- `read_only`：只读上下文标记（读写分离路由依据），占位默认 False。
- 认证 / 日志 / 多租户阶段接入后设置对应变量。
"""

from contextvars import ContextVar, Token

current_user_id: ContextVar[int | None] = ContextVar("current_user_id", default=None)
read_only: ContextVar[bool] = ContextVar("read_only", default=False)


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
