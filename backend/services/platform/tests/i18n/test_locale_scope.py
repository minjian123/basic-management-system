"""请求语言作用域：非 HTTP 调用（scope 无 `app`）时的防御分支。

后台任务 / 脚本里构造的 `Request` 不含 `app`，`locale_scope` 必须照常工作（回落种子清单），
不得因取 `app.state.locale_registry` 而抛错。
"""

from __future__ import annotations

import pytest
from starlette.requests import Request

from bms_core.dict.base import current_dict_locale
from bms_platform.api.locale import locale_scope

pytestmark = [pytest.mark.kiwi_id(2404)]


async def test_locale_scope_without_app_scope() -> None:
    """scope 无 `app`：不取能力域，仍能进入 / 退出作用域并复位上下文。"""
    before = current_dict_locale.get()
    request = Request({"type": "http", "headers": []})
    generator = locale_scope(request)
    await generator.__anext__()
    assert current_dict_locale.get()
    await generator.aclose()
    assert current_dict_locale.get() == before
