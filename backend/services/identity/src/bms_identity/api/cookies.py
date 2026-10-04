"""认证与身份服务端点：refresh cookie 下发 / 清理（本地登录与 SSO 共用）。

- 口径：HttpOnly + Secure（`[login].cookie_secure`）+ SameSite=Lax + `Path=/`（**浏览器按 `Path`
  前缀匹配回传**，服务内路径与前端外部地址 `/api/{service_key}/v1/...` 不匹配 → 取 `/`，见
  `schemas/auth.py::REFRESH_COOKIE_PATH`）；
- 本地登录 / 刷新与 SSO 回调成功都经本模块下发；登出 / 失败路径清理（含历史路径，见
  `REFRESH_COOKIE_LEGACY_PATHS`）。
"""

from fastapi import Request, Response

from bms_identity.schemas.auth import REFRESH_COOKIE_LEGACY_PATHS, REFRESH_COOKIE_NAME, REFRESH_COOKIE_PATH


def set_refresh_cookie(response: Response, request: Request, token: str, max_age: int | None) -> None:
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


def clear_refresh_cookie(response: Response) -> None:
    """清理 refresh cookie（登出 / 失败路径）：**新路径与历史路径各下发一次删除**。

    浏览器按 `Path` 隔离 cookie，只删当前路径无法清掉历史作用域（`/api/v1/auth`）的残留项，
    故按 `REFRESH_COOKIE_PATH` + `REFRESH_COOKIE_LEGACY_PATHS` 逐个下发删除（同键不同路径）。

    Args:
        response: 响应对象。
    """
    for path in (REFRESH_COOKIE_PATH, *REFRESH_COOKIE_LEGACY_PATHS):
        response.delete_cookie(REFRESH_COOKIE_NAME, path=path)
