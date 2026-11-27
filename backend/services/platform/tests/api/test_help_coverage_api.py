"""帮助覆盖率台账接口（`GET /api/v1/help/coverage`，08_04；Kiwi 2523）。

覆盖：鉴权与路由登记、分产品模块过滤、确定性响应、明细类别过滤、参考统计开关、锚点写入后覆盖变化。

运行口径（2026-11-27 重写）：平台库全 worker 共用、跨轮次叠加，故元数据一律按**用例命名空间**派生
（业务 / 动作编码、菜单路径、表单视图组件都用 `ns` 前缀），断言只限定本命名空间。特别注意不能沿用
`/probe/…` 路径与 `probe…` 组件标识——`libs/bms_core/tests/repositories` 的 autouse 清场按
`path LIKE '/probe/%'` 与 `component LIKE 'probe%'` 删探测行，用它会被别的 worker 在两个请求之间删掉
（实测「新增表单 失败：40201 菜单不存在」）。
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from bms_core.core.concurrent import ConcurrentStableDict
from bms_core.testing.namespace import Namespace
from tests_support.permission_stub import stub_permission_provider

_COVERAGE = "/api/v1/help/coverage"
_MENUS = "/api/v1/menus"
_FORMS = "/api/v1/forms"
_BUTTONS = "/api/v1/buttons"
_ACTIONS = "/api/v1/actions"
_BUSINESSES = "/api/v1/businesses"
_PERMISSIONS = "/api/v1/permissions"


@pytest.fixture(autouse=True)
def permission_engine(service_app: FastAPI, monkeypatch: pytest.MonkeyPatch) -> None:
    """本套用例权限放行：本应用解析到占位检查器（**不写共享租户库**）。

    这些用例测的是端点语义而非授权链路；写库授系统管理员会把「测试主体 → 豁免层级」留给
    同进程其它服务的无权限断言（实测 403 变 200）。

    Args:
        service_app: 平台服务应用。
        monkeypatch: 补丁夹具（用例结束自动还原）。
    """
    stub_permission_provider(service_app, monkeypatch)


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


def _menu_path(ns: Namespace) -> str:
    """本用例的菜单路径（命名空间独占，不落 `/probe/` 这个共享前缀）。

    Args:
        ns: 命名空间。

    Returns:
        str: 前端路由路径。
    """
    return f"/{ns.prefix}/coverage"


def _component(ns: Namespace) -> str:
    """本用例的表单视图组件标识（命名空间独占，不用 `probe…` 形态）。

    Args:
        ns: 命名空间。

    Returns:
        str: 组件标识。
    """
    return f"{ns.prefix}/view"


async def _create_menu(client: AsyncClient, ns: Namespace) -> Any:
    """新增本用例的菜单。

    Args:
        client: 测试客户端。
        ns: 命名空间。

    Returns:
        Any: 菜单行。
    """
    return _data(
        await client.post(
            _MENUS,
            json={
                "parent_id": 0,
                "path": _menu_path(ns),
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
    menu = await _create_menu(client, ns)
    form = _data(
        await client.post(
            _FORMS,
            json={
                "menu_ids": [menu["id"]],
                "business_id": business["id"],
                "status": "enabled",
                "component": _component(ns),
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
    scoped_keys = tuple(key for key in stable_keys if key != "summary")
    assert {key: first[key] for key in scoped_keys} == {key: second[key] for key in scoped_keys}
    # `summary.reference`（表单 / 字段 / 动作码兜底）是**全平台**口径、不随 module_key 收敛：
    # 两次调用之间别的 worker 新增锚点就会变，不参与确定性比对。
    first_summary = {key: value for key, value in first["summary"].items() if key != "reference"}
    second_summary = {key: value for key, value in second["summary"].items() if key != "reference"}
    assert first_summary == second_summary
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
    """按钮与菜单写入锚点后覆盖数变为 1，且本用例锚点计入基准（不进孤儿、不重复）。"""
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
            "component": _component(ns),
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
    # 对账里的 `consistent` / `verdict.blocked` 是**全平台**口径（覆盖数 + 孤儿数 = 锚点总数且无重复）：
    # 共享库叠加下会被别的命名空间残留的锚点带偏，不在本用例断言范围内。这里只校验本用例的锚点
    # 确实进了基准（不在孤儿清单）且没有重复。
    reconciliation = data["reconciliation"]
    assert reconciliation["covered"]["menu"] >= 1
    assert reconciliation["covered"]["action"] >= 1
    assert {menu_key, button_key}.isdisjoint(reconciliation["duplicate_help_keys"])
    orphan_keys = {orphan["help_key"] for orphan in reconciliation["orphans"]}
    assert {menu_key, button_key}.isdisjoint(orphan_keys)
