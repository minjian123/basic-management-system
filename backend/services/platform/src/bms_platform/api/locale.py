"""请求语言解析与作用域（平台侧横切，菜单表单与权限元数据 API 共用）。

- `accept_locale`：解析 `Accept-Language`——**有语言清单能力域时按库内清单解析**（新增语言即刻可命中），
  无注册表（纯函数测试 / 未装配）时回退种子常量；
- `locale_scope`：路由级依赖，设置 `current_dict_locale` 并在请求结束复位——写路径的必填语言
  与元数据缓存键语言都据此解析。
"""

from collections.abc import AsyncGenerator
from typing import cast

from fastapi import Request

from bms_core.dict.base import current_dict_locale
from bms_core.i18n.base import DEFAULT_LOCALE, SUPPORTED_LOCALES
from bms_core.i18n.locale import match_locale
from bms_core.i18n.registry import BaseLocaleRegistry

__all__ = ["accept_locale", "locale_scope"]


def accept_locale(request: Request, registry: BaseLocaleRegistry | None = None) -> str:
    """解析 `Accept-Language`（清单内匹配；缺省默认语言）。

    Args:
        request: 请求对象。
        registry: 语言清单能力域；None 时用种子常量解析（纯函数口径）。

    Returns:
        str: 生效语言。
    """
    raw = request.headers.get("accept-language", "")
    if registry is not None:
        return registry.resolve_locale(raw)
    return match_locale(raw, SUPPORTED_LOCALES, DEFAULT_LOCALE)


async def locale_scope(request: Request) -> AsyncGenerator[None]:
    """请求语言作用域（路由级依赖）：设置 `current_dict_locale`，请求结束复位。

    Args:
        request: 请求对象（取 `Accept-Language` 与已装配的语言清单能力域）。

    Yields:
        None: 作用域内请求语言生效。
    """
    registry: BaseLocaleRegistry | None = None
    if "app" in request.scope:
        registry = cast("BaseLocaleRegistry | None", getattr(request.app.state, "locale_registry", None))
    token = current_dict_locale.set(accept_locale(request, registry))
    try:
        yield
    finally:
        current_dict_locale.reset(token)
