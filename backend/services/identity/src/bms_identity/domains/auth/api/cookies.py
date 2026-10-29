"""认证与身份服务端点：refresh cookie 下发 / 清理（本地登录与 SSO 共用）。

实现在 `domains/auth/services/cookie_policy.py`（单一落点）；本模块只保留端点侧函数名，
供本域路由按既有签名调用（分层方向 `api → services`）。
"""

from fastapi import Request, Response

from bms_identity.domains.auth.services.cookie_policy import (
    delete_refresh_cookie,
    write_refresh_cookie,
)

__all__ = ["clear_refresh_cookie", "set_refresh_cookie"]


def set_refresh_cookie(response: Response, request: Request, token: str, max_age: int | None) -> None:
    """下发 refresh cookie。

    Args:
        response: 响应对象。
        request: 请求对象（取 cookie 安全开关）。
        token: refresh token 紧凑串。
        max_age: 有效期（秒）；`None` 下发**会话 Cookie**（浏览器会话结束即失效）。
    """
    write_refresh_cookie(response, request, token, max_age)


def clear_refresh_cookie(response: Response) -> None:
    """清理 refresh cookie（登出 / 失败路径）：**新路径与历史路径各下发一次删除**。

    Args:
        response: 响应对象。
    """
    delete_refresh_cookie(response)
