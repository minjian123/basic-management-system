"""认证域领域服务接口（Protocol）。

跨域消费方只依赖本模块的协议；实现类留在域内（`services/`），由装配面 `bms_identity.wiring`
构造后注入。这样出口暴露的是**契约**而不是**实现**——改实现类不影响出口面，改协议必须动本文件，
评审与护栏都看得见。
"""

from __future__ import annotations

from typing import Protocol

from fastapi import Request, Response

from bms_identity.domains.auth.dto import IssuedSession

__all__ = ["SessionCookiePolicy", "SessionIssuerPort"]


class SessionIssuerPort(Protocol):
    """会话签发接口：双 token 同会话 id + 会话落库 + 会话标记。"""

    async def issue(
        self,
        *,
        user_id: int,
        tenant_id: str,
        tenant_code: str,
        ip: str | None,
        user_agent: str | None,
        remember_me: bool = True,
    ) -> IssuedSession:
        """签发会话。

        Args:
            user_id: 用户 ID（platform 库 `sys_user.id`）。
            tenant_id: 租户主键（雪花 id 字符串；令牌 / 会话标记租户位）。
            tenant_code: 租户编码（会话记录 / 展示用）。
            ip: 客户端 IP（可选）。
            user_agent: 客户端 User-Agent（可选）。
            remember_me: 是否记住我。

        Returns:
            IssuedSession: 会话签发结果（含 refresh 原始票据）。
        """
        ...


class SessionCookiePolicy(Protocol):
    """refresh cookie 下发与清理口径（HttpOnly / Secure / SameSite / Path 由实现方统一决定）。"""

    def apply_refresh(self, response: Response, request: Request, issued: IssuedSession) -> None:
        """下发 refresh cookie。

        Args:
            response: 响应对象。
            request: 请求对象（取 cookie 安全开关）。
            issued: 已签发的会话（取 refresh 票据与有效期）。
        """
        ...

    def clear_refresh(self, response: Response) -> None:
        """清理 refresh cookie（登出 / 失败路径，含历史路径）。

        Args:
            response: 响应对象。
        """
        ...
