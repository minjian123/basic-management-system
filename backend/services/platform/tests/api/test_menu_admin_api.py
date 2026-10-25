"""业务码 / 动作码 / 权限码写接口测试（03_03/_02，需求 07-17）。

覆盖：业务 / 动作码新增（40209 重复、code 只读）、停用联动权限码、有条件删除（40206）、
权限码手工新增（40210 重复）/ 批量补生成 / 启停引用保护 / 删除引用保护。
"""

import pytest
import pytest_asyncio
from httpx import AsyncClient

from tests_support.menu_metadata import reset_menu_tables
from tests_support.permission_admin import setup_min_tenant

_BUSINESSES = "/api/v1/businesses"
_ACTIONS = "/api/v1/actions"
_PERMISSIONS = "/api/v1/permissions"
_FORMS = "/api/v1/forms"
_BUTTONS = "/api/v1/buttons"


@pytest_asyncio.fixture(autouse=True)
async def clean_tables(platform_db: None) -> None:
    """菜单元数据表逐用例清场（会话级平台库共享）。

    Args:
        platform_db: 平台库夹具。
    """
    await reset_menu_tables()


@pytest_asyncio.fixture(autouse=True)
async def tenant_db(tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> None:
    """最小租户库（权限引擎读表）+ 内置系统管理员主体。

    Args:
        tmp_path_factory: pytest 临时目录工厂。
        monkeypatch: pytest 环境变量覆盖夹具。
    """
    await setup_min_tenant(tmp_path_factory, monkeypatch)


async def _create_business(client: AsyncClient, code: str, name: str = "测试业务") -> int:
    """新增业务码并返回主键。

    Args:
        client: 测试客户端。
        code: 业务码。
        name: 名称。

    Returns:
        int: 业务码主键。
    """
    resp = await client.post(_BUSINESSES, json={"code": code, "status": "enabled", "i18n": {"zh-CN": name}})
    assert resp.json()["code"] == 0, resp.text
    return int(resp.json()["data"]["id"])


async def _create_action(client: AsyncClient, code: str, name: str = "测试动作") -> int:
    """新增动作码并返回主键。

    Args:
        client: 测试客户端。
        code: 动作码。
        name: 名称。

    Returns:
        int: 动作码主键。
    """
    resp = await client.post(_ACTIONS, json={"code": code, "status": "enabled", "i18n": {"zh-CN": name}})
    assert resp.json()["code"] == 0, resp.text
    return int(resp.json()["data"]["id"])


async def _create_permission(client: AsyncClient, business_id: int, action_id: int) -> int:
    """手工新增权限码并返回主键。

    Args:
        client: 测试客户端。
        business_id: 业务码主键。
        action_id: 动作码主键。

    Returns:
        int: 权限码主键。
    """
    resp = await client.post(_PERMISSIONS, json={"business_id": business_id, "action_id": action_id})
    assert resp.json()["code"] == 0, resp.text
    return int(resp.json()["data"]["id"])


@pytest.mark.kiwi_id(2242)
async def test_business_crud_code_readonly_and_duplicate(client: AsyncClient) -> None:
    """业务码：新增、重复 40209、code 只读（带 code 更新 422）、名称与状态更新、列表含权限码数。"""
    business_id = await _create_business(client, "t_order", "测试订单")
    duplicated = await client.post(
        _BUSINESSES, json={"code": "t_order", "status": "enabled", "i18n": {"zh-CN": "重复"}}
    )
    assert duplicated.json()["code"] == 40209

    with_code = await client.put(
        f"{_BUSINESSES}/{business_id}",
        json={"code": "t_other", "status": "enabled", "i18n": {"zh-CN": "改名"}},
    )
    assert with_code.status_code == 200
    assert with_code.json()["code"] == 10001
    assert with_code.json()["data"][0]["type"] == "extra_forbidden"

    updated = await client.put(f"{_BUSINESSES}/{business_id}", json={"status": "disabled", "i18n": {"zh-CN": "改名"}})
    assert updated.json()["code"] == 0
    assert updated.json()["data"]["name"] == "改名"
    assert updated.json()["data"]["status"] == "disabled"

    listed = await client.get(_BUSINESSES)
    row = next(item for item in listed.json()["data"]["items"] if int(item["id"]) == business_id)
    assert row["permission_count"] == 0


@pytest.mark.kiwi_id(2242)
async def test_action_crud_and_delete_guard(client: AsyncClient) -> None:
    """动作码：新增 / 重复 40209 / 有条件删除（其下有权限码时 40206）。"""
    action_id = await _create_action(client, "t_ship", "发货")
    duplicated = await client.post(_ACTIONS, json={"code": "t_ship", "status": "enabled", "i18n": {"zh-CN": "重复"}})
    assert duplicated.json()["code"] == 40209

    business_id = await _create_business(client, "t_order")
    permission_id = await _create_permission(client, business_id, action_id)
    blocked = await client.delete(f"{_ACTIONS}/{action_id}")
    assert blocked.json()["code"] == 40206

    await client.delete(f"{_PERMISSIONS}/{permission_id}")
    removed = await client.delete(f"{_ACTIONS}/{action_id}")
    assert removed.json()["code"] == 0


@pytest.mark.kiwi_id(2242)
async def test_permission_manual_create_generate_and_duplicate(client: AsyncClient) -> None:
    """权限码：手工新增、组合重复 40210、批量补生成计数与幂等。"""
    business_a = await _create_business(client, "t_a", "业务 A")
    business_b = await _create_business(client, "t_b", "业务 B")
    action_x = await _create_action(client, "t_x", "动作 X")
    action_y = await _create_action(client, "t_y", "动作 Y")

    permission_id = await _create_permission(client, business_a, action_x)
    duplicated = await client.post(_PERMISSIONS, json={"business_id": business_a, "action_id": action_x})
    assert duplicated.json()["code"] == 40210

    generated = await client.post(
        _PERMISSIONS + "/generate",
        json={"business_ids": [business_a, business_b], "action_ids": [action_x, action_y]},
    )
    assert generated.json()["data"] == {"created": 3, "restored": 0, "skipped": 1}
    again = await client.post(
        _PERMISSIONS + "/generate",
        json={"business_ids": [business_a, business_b], "action_ids": [action_x, action_y]},
    )
    assert again.json()["data"] == {"created": 0, "restored": 0, "skipped": 4}

    row = next(
        item for item in (await client.get(_PERMISSIONS)).json()["data"]["items"] if int(item["id"]) == permission_id
    )
    assert row["code"] == "t_a:t_x"
    assert row["name"] == "业务 A·动作 X"


@pytest.mark.kiwi_id(2242)
async def test_permission_stop_and_delete_blocked_by_button(client: AsyncClient) -> None:
    """被按钮挂接的权限码：停用 40206、删除 40206；停用业务码整批拒绝。"""
    business_id = await _create_business(client, "t_biz")
    action_id = await _create_action(client, "t_act")
    permission_id = await _create_permission(client, business_id, action_id)
    form = await client.post(
        _FORMS, json={"menu_ids": [], "business_id": business_id, "component": None, "status": "enabled"}
    )
    form_id = int(form.json()["data"]["id"])
    button = await client.post(
        _BUTTONS,
        json={
            "form_id": form_id,
            "permission_id": permission_id,
            "name": "测试按钮",
            "type": "toolbar",
            "sort": 1,
            "status": "enabled",
        },
    )
    assert button.json()["code"] == 0, button.text

    stopped = await client.put(f"{_PERMISSIONS}/{permission_id}", json={"status": "disabled"})
    assert stopped.json()["code"] == 40206
    removed = await client.delete(f"{_PERMISSIONS}/{permission_id}")
    assert removed.json()["code"] == 40206

    business_stopped = await client.put(
        f"{_BUSINESSES}/{business_id}", json={"status": "disabled", "i18n": {"zh-CN": "业务"}}
    )
    assert business_stopped.json()["code"] == 40206

    business_removed = await client.delete(f"{_BUSINESSES}/{business_id}")
    assert business_removed.json()["code"] == 40206


@pytest.mark.kiwi_id(2242)
async def test_update_and_delete_endpoints_full_paths(client: AsyncClient) -> None:
    """动作码 / 权限码更新端点与业务码删除成功路径，及三类「不存在」分支。

    补齐 api/menu.py 未覆盖的端点成功路径（update_action / update_permission /
    delete_business）与 _business_item / _action_item / _permission_item 的缺行异常。
    """
    business_id = await _create_business(client, "t_full")
    action_id = await _create_action(client, "t_full_act")
    permission_id = await _create_permission(client, business_id, action_id)

    # update_action：改名称与状态，回显走 _action_item
    patched_action = await client.put(
        f"{_ACTIONS}/{action_id}", json={"status": "disabled", "i18n": {"zh-CN": "动作改名"}}
    )
    assert patched_action.json()["code"] == 0, patched_action.text
    assert patched_action.json()["data"]["status"] == "disabled"

    # update_permission：改状态，回显走 _permission_item
    patched_permission = await client.put(f"{_PERMISSIONS}/{permission_id}", json={"status": "disabled"})
    assert patched_permission.json()["code"] == 0, patched_permission.text
    assert patched_permission.json()["data"]["status"] == "disabled"

    # 三类缺行分支：更新不存在的动作码 / 权限码
    missing_action = await client.put(f"{_ACTIONS}/987654321", json={"status": "enabled", "i18n": {"zh-CN": "无"}})
    assert missing_action.status_code == 404
    missing_permission = await client.put(f"{_PERMISSIONS}/987654321", json={"status": "enabled"})
    assert missing_permission.status_code == 404

    # delete_business 成功路径（先解掉权限码与动作码的引用）
    assert (await client.delete(f"{_PERMISSIONS}/{permission_id}")).json()["code"] == 0
    assert (await client.delete(f"{_ACTIONS}/{action_id}")).json()["code"] == 0
    removed_business = await client.delete(f"{_BUSINESSES}/{business_id}")
    assert removed_business.json()["code"] == 0, removed_business.text


@pytest.mark.kiwi_id(2242)
async def test_generate_restores_soft_deleted_permission(client: AsyncClient) -> None:
    """批量补生成：同组合软删后再次生成走恢复分支并计入 restored。

    覆盖 services/menu.py 的 deleted_pairs 收集（1035-1037）与恢复计数（1048-1052）。
    """
    business_id = await _create_business(client, "t_restore")
    action_id = await _create_action(client, "t_restore_act")
    permission_id = await _create_permission(client, business_id, action_id)

    # 先软删该组合，使 active_pairs 不含它、deleted_pairs 含它
    assert (await client.delete(f"{_PERMISSIONS}/{permission_id}")).json()["code"] == 0

    generated = await client.post(
        _PERMISSIONS + "/generate",
        json={"business_ids": [business_id], "action_ids": [action_id]},
    )
    assert generated.json()["code"] == 0, generated.text
    assert generated.json()["data"] == {"created": 0, "restored": 1, "skipped": 0}

    # 恢复后状态为启用且仍为原主键
    rows = (await client.get(_PERMISSIONS)).json()["data"]["items"]
    restored_row = next(item for item in rows if int(item["id"]) == permission_id)
    assert restored_row["status"] == "enabled"


@pytest.mark.kiwi_id(2242)
async def test_repeat_stop_skips_cascade(client: AsyncClient) -> None:
    """已停用的业务码 / 动作码再次停用：跳过联动（844->848 / 941->946 的假分支）。"""
    business_id = await _create_business(client, "t_idem")
    action_id = await _create_action(client, "t_idem_act")
    await _create_permission(client, business_id, action_id)

    # 首次停用：走联动分支
    first = await client.put(f"{_BUSINESSES}/{business_id}", json={"status": "disabled", "i18n": {"zh-CN": "幂等业务"}})
    assert first.json()["code"] == 0, first.text

    # 再次停用：current.status 已是 disabled，条件为假，跳过联动
    again = await client.put(f"{_BUSINESSES}/{business_id}", json={"status": "disabled", "i18n": {"zh-CN": "幂等业务"}})
    assert again.json()["code"] == 0, again.text
    assert again.json()["data"]["status"] == "disabled"

    # 动作码同构：首次停用走联动，再次停用跳过
    first_action = await client.put(
        f"{_ACTIONS}/{action_id}", json={"status": "disabled", "i18n": {"zh-CN": "幂等动作"}}
    )
    assert first_action.json()["code"] == 0, first_action.text
    again_action = await client.put(
        f"{_ACTIONS}/{action_id}", json={"status": "disabled", "i18n": {"zh-CN": "幂等动作"}}
    )
    assert again_action.json()["code"] == 0, again_action.text


@pytest.mark.kiwi_id(2242)
async def test_update_permission_when_not_first_in_list(client: AsyncClient) -> None:
    """权限码列表含多个条目且目标非首个时，_permission_item 继续迭代后命中。

    覆盖 api/menu.py 的循环未命中继续分支（1064->1063）。
    """
    business_id = await _create_business(client, "t_iter")
    action_first = await _create_action(client, "t_iter_a1")
    action_second = await _create_action(client, "t_iter_a2")
    await _create_permission(client, business_id, action_first)
    target_id = await _create_permission(client, business_id, action_second)

    # 列表按主键升序，target 为第二条：首轮未命中后继续迭代
    patched = await client.put(f"{_PERMISSIONS}/{target_id}", json={"status": "disabled"})
    assert patched.json()["code"] == 0, patched.text
    assert patched.json()["data"]["status"] == "disabled"


@pytest.mark.kiwi_id(2242)
async def test_business_stop_cascades_permission(client: AsyncClient) -> None:
    """无引用的业务码停用：其权限码连带停用。"""
    business_id = await _create_business(client, "t_cascade")
    action_id = await _create_action(client, "t_cascade_act")
    permission_id = await _create_permission(client, business_id, action_id)

    stopped = await client.put(f"{_BUSINESSES}/{business_id}", json={"status": "disabled", "i18n": {"zh-CN": "级联"}})
    assert stopped.json()["code"] == 0
    row = next(
        item for item in (await client.get(_PERMISSIONS)).json()["data"]["items"] if int(item["id"]) == permission_id
    )
    assert row["status"] == "disabled"
