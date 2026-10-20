"""平台菜单模块状态测试（任务 `04_01`；Kiwi 2325）。

覆盖：无租户 / 非法租户上下文时模块状态为空（不访问门禁）。

> 字段权限工厂登记入口不在此文件断言——02_04/_01 下沉后登记统一在
> `bms_platform.permission.checker.register_platform_permission` 内完成（`cc276b0d` 删除了
> `field_provider.register_static_field_provider` 死函数），该登记由 `tests/permission/test_source.py`
> 的 `test_register_platform_permission_wires_everything` 覆盖。
"""

import pytest
from fastapi import FastAPI
from starlette.requests import Request

from bms_core.core import context
from bms_platform.api.menu import _module_states  # pyright: ignore[reportPrivateUsage]

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
