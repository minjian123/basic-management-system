"""认证域 refresh cookie 策略实现（逻辑唯一落点；`api/cookies.py` 只做薄转发）。

口径：HttpOnly + Secure（`[login].cookie_secure`）+ SameSite=Lax + `Path=/`（**浏览器按 `Path`
前缀匹配回传**，服务内路径与前端外部地址 `/api/{service_key}/v1/...` 不匹配 → 取 `/`，见
`schemas/auth.py::REFRESH_COOKIE_PATH`）。
"""

from __future__ import annotations

from fastapi import Request, Response

from bms_core.core.objects import BaseFrameworkObject
from bms_identity.domains.auth.dto import IssuedSession
from bms_identity.domains.auth.schemas.auth import (
    REFRESH_COOKIE_LEGACY_PATHS,
    REFRESH_COOKIE_NAME,
    REFRESH_COOKIE_PATH,
)

__all__ = ["HttpSessionCookiePolicy", "delete_refresh_cookie", "write_refresh_cookie"]


def write_refresh_cookie(response: Response, request: Request, token: str, max_age: int | None) -> None:
    """下发 refresh cookie。

    Args:
        response: 响应对象。
        request: 请求对象（取 cookie 安全开关）。
        token: refresh token 紧凑串。
        max_age: 有效期（秒）；`None` 下发**会话 Cookie**（浏览器会话结束即失效）。
    """
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=token,
        max_age=max_age,
        path=REFRESH_COOKIE_PATH,
        httponly=True,
        secure=bool(request.app.state.settings.login.cookie_secure),
        samesite="lax",
    )


def delete_refresh_cookie(response: Response) -> None:
    """清理 refresh cookie：**新路径与历史路径各下发一次删除**。

    浏览器按 `Path` 隔离 cookie，只删当前路径无法清掉历史作用域（`/api/v1/auth`）的残留项，
    故按 `REFRESH_COOKIE_PATH` + `REFRESH_COOKIE_LEGACY_PATHS` 逐个下发删除（同键不同路径）。

    Args:
        response: 响应对象。
    """
    for path in (REFRESH_COOKIE_PATH, *REFRESH_COOKIE_LEGACY_PATHS):
        response.delete_cookie(REFRESH_COOKIE_NAME, path=path)


class HttpSessionCookiePolicy(BaseFrameworkObject):
    """`SessionCookiePolicy` 的 HTTP 实现（口径与本地登录 / 刷新完全一致）。"""

    def apply_refresh(self, response: Response, request: Request, issued: IssuedSession) -> None:
        """下发 refresh cookie（有效期取签发结果，与改造前同值）。

        Args:
            response: 响应对象。
            request: 请求对象（取 cookie 安全开关）。
            issued: 已签发的会话。
        """
        write_refresh_cookie(response, request, issued.refresh_token, issued.refresh_expires_in)

    def clear_refresh(self, response: Response) -> None:
        """清理 refresh cookie。

        Args:
            response: 响应对象。
        """
        delete_refresh_cookie(response)
