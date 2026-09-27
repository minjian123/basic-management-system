"""认证与身份服务端点：refresh cookie 下发 / 清理（本地登录与 SSO 共用）。

- 口径：HttpOnly + Secure（`[login].cookie_secure`）+ SameSite=Lax + `Path=/api/v1/auth`；
  本地登录 / 刷新与 SSO 回调成功都经本模块下发，登出 / 失败路径清理。
"""

from fastapi import Request, Response

from bms_identity.schemas.auth import REFRESH_COOKIE_NAME, REFRESH_COOKIE_PATH


def set_refresh_cookie(response: Response, request: Request, token: str, max_age: int) -> None:
    """下发 refresh cookie。

    Args:
        response: 响应对象。
        request: 请求对象（取 cookie 安全开关）。
        token: refresh token 紧凑串。
        max_age: 有效期（秒）。
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


def clear_refresh_cookie(response: Response) -> None:
    """清理 refresh cookie（登出 / 失败路径）。

    Args:
        response: 响应对象。
    """
    response.delete_cookie(REFRESH_COOKIE_NAME, path=REFRESH_COOKIE_PATH)
