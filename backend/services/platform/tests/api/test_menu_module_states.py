"""平台菜单模块状态与字段权限工厂登记测试（任务 `04_01`；Kiwi 2325）。

覆盖：无租户 / 非法租户上下文时模块状态为空（不访问门禁）；基础版字段权限工厂登记入口。
"""

import pytest
from fastapi import FastAPI
from starlette.requests import Request

from bms_core.core import context
from bms_platform.api.menu import _module_states  # pyright: ignore[reportPrivateUsage]
from bms_platform.permission.field_provider import register_static_field_provider

pytestmark = pytest.mark.kiwi_id(2325)


async def test_module_states_empty_without_or_invalid_tenant() -> None:
    """无租户 / 非数字租户：返回空状态，不触达门禁实现（平台全局菜单）。"""
    request = Request({"type": "http", "app": FastAPI(), "headers": []})
    token = context.current_tenant_id.set(None)
    try:
        assert dict(await _module_states(request)) == {}
    finally:
        context.current_tenant_id.reset(token)

    token = context.current_tenant_id.set("not-a-number")
    try:
        assert dict(await _module_states(request)) == {}
    finally:
        context.current_tenant_id.reset(token)


def test_register_static_field_provider() -> None:
    """基础版字段权限工厂登记入口可直接调用（后代档位同键覆盖）。"""
    register_static_field_provider()
