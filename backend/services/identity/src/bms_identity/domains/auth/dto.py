"""认证域数据 DTO：域公共出口只交本模块的不可变对象（D6 出口导出面）。

`IssuedSession` 是会话签发结果：双 token + 会话 id + 有效期，供域外下发 cookie 与拼装响应体；
`@dataclass(frozen=True)` 保证出口对象不可变（改动即 `FrozenInstanceError`），消费方按字段取值、
不挂关系、不做懒加载。
"""

from __future__ import annotations

from dataclasses import dataclass

from bms_core.core.objects import BaseRefreshableTokenContract
from bms_core.oauth.base import TOKEN_TYPE_BEARER

__all__ = ["IssuedSession"]


@dataclass(frozen=True)
class IssuedSession(BaseRefreshableTokenContract):
    """会话签发结果（双 token + 会话 id，供下发 cookie 与响应体）。"""

    access_token: str
    """访问令牌（紧凑 JWT）。"""

    refresh_token: str
    """刷新令牌（紧凑 JWT）。"""

    access_expires_in: int
    """access 有效期（秒）。"""

    refresh_expires_in: int
    """refresh 有效期（秒）。"""

    session_id: str
    """会话 id（= 双 token `jti`）。"""

    remember_me: bool = True
    """是否记住我（决定 Cookie 是否持久；refresh 保留时长选项）。"""

    token_type: str = TOKEN_TYPE_BEARER
    """令牌类型（响应口径）。"""
