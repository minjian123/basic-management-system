"""请求语言解析与作用域（平台侧横切，菜单表单与权限元数据 API 共用）。

- `accept_locale`：解析 `Accept-Language`（按支持清单匹配，缺省默认语言）；
- `locale_scope`：路由级依赖，设置 `current_dict_locale` 并在请求结束复位——写路径的必填语言
  与元数据缓存键语言都据此解析。
"""

from collections.abc import AsyncGenerator

from fastapi import Request

from bms_core.dict.base import current_dict_locale
from bms_core.i18n.base import DEFAULT_LOCALE, SUPPORTED_LOCALES

__all__ = ["accept_locale", "locale_scope"]


def accept_locale(request: Request) -> str:
    """解析 `Accept-Language`（支持清单内匹配；缺省默认语言）。

    Args:
        request: 请求对象。

    Returns:
        str: 生效语言。
    """
    raw = request.headers.get("accept-language", "")
    for part in raw.split(","):
        tag = part.split(";")[0].strip()
        if not tag:
            continue
        if tag in SUPPORTED_LOCALES:
            return tag
        prefix = tag.split("-")[0].lower()
        for supported in SUPPORTED_LOCALES:
            if supported.split("-")[0].lower() == prefix:
                return supported
    return DEFAULT_LOCALE


async def locale_scope(request: Request) -> AsyncGenerator[None]:
    """请求语言作用域（路由级依赖）：设置 `current_dict_locale`，请求结束复位。

    Args:
        request: 请求对象（取 `Accept-Language`）。

    Yields:
        None: 作用域内请求语言生效。
    """
    token = current_dict_locale.set(accept_locale(request))
    try:
        yield
    finally:
        current_dict_locale.reset(token)
