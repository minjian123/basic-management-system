"""帮助覆盖率台账接口（`GET /api/v1/help/coverage`，08_04；Kiwi 2523）。

覆盖：鉴权与路由登记、分产品模块过滤、确定性响应、明细类别过滤、参考统计开关、锚点写入后覆盖变化。
元数据经维护接口按命名空间创建，断言只限定本命名空间（平台库单库叠加）。
"""

from __future__ import annotations

from typing import Any

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from bms_core.core.concurrent import ConcurrentStableDict
from bms_core.testing.namespace import Namespace
from tests_support.permission_admin import setup_min_tenant

_COVERAGE = "/api/v1/help/coverage"
_MENUS = "/api/v1/menus"
_FORMS = "/api/v1/forms"
_BUTTONS = "/api/v1/buttons"
_ACTIONS = "/api/v1/actions"
_BUSINESSES = "/api/v1/businesses"
_PERMISSIONS = "/api/v1/permissions"


@pytest_asyncio.fixture(autouse=True)
async def permission_engine(tenant_db: str) -> None:
    """真实权限校验所需的租户库（共享租户库）+ 内置系统管理员主体。

    Args:
        tenant_db: 共享租户库连接串。
    """
    await setup_min_tenant(tenant_db)


def _data(response: Any, label: str) -> Any:
    """取统一响应 `data`（失败时把完整响应体写进断言信息）。

    Args:
        response: httpx 响应。
        label: 调用标识。

    Returns:
        Any: `data` 字段。
    """
    payload = response.json()
    assert response.status_code == 200, f"{label} 失败：{payload}"
    assert payload["code"] == 0, f"{label} 失败：{payload}"
    return payload["data"]


def _code(ns: Namespace, suffix: str) -> str:
    """生成命名空间内的业务 / 动作编码。

    Args:
        ns: 命名空间。
        suffix: 后缀。

    Returns:
        str: 编码。
    """
    return f"{ns.prefix}_{suffix}"


async def _create_menu(client: AsyncClient, path: str) -> Any:
    """新增菜单。

    Args:
        client: 测试客户端。
        path: 路由路径。

    Returns:
        Any: 菜单行。
    """
    return _data(
        await client.post(
            _MENUS,
            json={
                "parent_id": 0,
                "path": path,
                "sort": 1,
                "hidden": False,
                "status": "enabled",
                "i18n": {"zh-CN": "覆盖率用例", "en-US": "Coverage case"},
            },
        ),
        "新增菜单",
    )


async def _seed(client: AsyncClient, ns: Namespace) -> ConcurrentStableDict[str, Any]:
    """构造一套覆盖率元数据（业务 / 动作 / 权限码 / 菜单 / 表单 / 按钮）。

    Args:
        client: 测试客户端。
        ns: 命名空间。

    Returns:
        dict[str, Any]: 关键行。
    """
    business_code = _code(ns, "biz")
    business = _data(
        await client.post(_BUSINESSES, json={"code": business_code, "i18n": {"zh-CN": "覆盖率业务"}}),
        "新增业务码",
    )
    action = _data(
        await client.post(
            _ACTIONS, json={"code": _code(ns, "act"), "status": "enabled", "i18n": {"zh-CN": "覆盖率动作"}}
        ),
        "新增动作码",
    )
    permission = _data(
        await client.post(_PERMISSIONS, json={"business_id": business["id"], "action_id": action["id"]}),
        "新增权限码",
    )
    menu = await _create_menu(client, f"/probe/{ns.prefix}")
    form = _data(
        await client.post(
            _FORMS,
            json={
                "menu_ids": [menu["id"]],
                "business_id": business["id"],
                "status": "enabled",
                "component": "probe/view",
            },
        ),
        "新增表单",
    )
    button = _data(
        await client.post(
            _BUTTONS,
            json={
                "form_id": form["id"],
                "permission_id": permission["id"],
                "name": "新增",
                "type": "toolbar",
                "sort": 1,
                "status": "enabled",
            },
        ),
        "新增按钮",
    )
    return ConcurrentStableDict(
        {
            "business_code": business_code,
            "menu": menu,
            "form": form,
            "button": button,
            "permission": permission,
        }
    )


@pytest.mark.kiwi_id(2523)
async def test_route_requires_auth_and_is_registered(service_app: FastAPI) -> None:
    """未登录返回 401；公开契约登记该路径。"""
    async with AsyncClient(transport=ASGITransport(app=service_app), base_url="http://test") as anon:
        response = await anon.get(_COVERAGE)
    assert response.status_code == 401
    assert _COVERAGE in service_app.openapi()["paths"]


@pytest.mark.kiwi_id(2523)
async def test_coverage_filters_and_determinism(client: AsyncClient, ns: Namespace) -> None:
    """过滤、明细与重复调用一致。"""
    seeded = await _seed(client, ns)
    module = seeded["business_code"]
    first = _data(await client.get(_COVERAGE, params={"module_key": module}), "覆盖率（首次）")
    second = _data(await client.get(_COVERAGE, params={"module_key": module}), "覆盖率（再次）")
    stable_keys = ("schema_version", "kind", "as_of", "scope", "summary", "groups", "units", "exemptions")
    assert {key: first[key] for key in stable_keys} == {key: second[key] for key in stable_keys}
    assert first["summary"]["action"]["total"] == 1
    assert first["summary"]["action"]["gap"] == 1
    assert first["summary"]["menu"]["total"] == 1
    assert first["units"][0]["key"].endswith("_act")
    assert first["scope"]["module_keys"] == [module]

    actions_only = _data(
        await client.get(_COVERAGE, params={"module_key": module, "kind": "action"}),
        "动作过滤",
    )
    assert {unit["kind"] for unit in actions_only["units"]} == {"action"}

    no_reference = _data(
        await client.get(_COVERAGE, params={"module_key": module, "include_reference": False}),
        "关闭参考统计",
    )
    assert no_reference["summary"]["reference"]["form"]["total"] == 0
    assert no_reference["summary"]["reference"]["field"]["total"] == 0
    assert no_reference["groups"][0]["reference"]["form_total"] == 0

    empty = _data(await client.get(_COVERAGE, params={"module_key": _code(ns, "missing")}), "未知模块")
    assert empty["summary"]["action"]["total"] == 0
    assert empty["units"] == []


@pytest.mark.kiwi_id(2523)
async def test_covered_rows_after_help_key_update(client: AsyncClient, ns: Namespace) -> None:
    """按钮与菜单写入锚点后覆盖数变为 1、对账一致。"""
    seeded = await _seed(client, ns)
    menu = seeded["menu"]
    button = seeded["button"]
    permission = seeded["permission"]
    module = seeded["business_code"]
    button_key = f"platform:{ns.prefix}:{module}::create"
    menu_key = f"platform:{ns.prefix}:::"

    updated_button = await client.put(
        f"{_BUTTONS}/{int(button['id'])}",
        json={
            "permission_id": permission["id"],
            "name": "新增",
            "type": "toolbar",
            "sort": 1,
            "status": "enabled",
            "help_key": button_key,
        },
    )
    assert _data(updated_button, "按钮锚点")["help_key"] == button_key

    updated_menu = await client.put(
        f"{_MENUS}/{int(menu['id'])}",
        json={
            "parent_id": 0,
            "path": menu["path"],
            "component": "probe/view",
            "sort": 1,
            "hidden": False,
            "status": "enabled",
            "i18n": {"zh-CN": "覆盖率用例", "en-US": "Coverage case"},
            "help_key": menu_key,
        },
    )
    assert _data(updated_menu, "菜单锚点")["help_key"] == menu_key

    data = _data(await client.get(_COVERAGE, params={"module_key": module}), "覆盖后覆盖率")
    assert data["summary"]["action"]["covered"] == 1
    assert data["summary"]["menu"]["covered"] == 1
    assert data["reconciliation"]["consistent"] is True
    assert data["reconciliation"]["covered"]["menu"] >= 1
    assert data["reconciliation"]["covered"]["action"] >= 1
    assert data["verdict"]["blocked"] is False
