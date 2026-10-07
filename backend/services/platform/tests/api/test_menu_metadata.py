"""菜单与权限元数据端点测试（Kiwi 2242）：菜单 / 表单 / 按钮 / 字段维护与挂接链校验。

覆盖：菜单增改删与路径冲突（40203）、父菜单不存在（40201）、表单业务 1:1 挂接冲突（10003）、
**菜单 ↔ 表单多对多（含孤儿表单与按菜单关联过滤）**、按钮同动作冲突（10003）与形态校验（10001）、
字段键重复（40205）、被引用禁删（40206）、业务 / 动作码只读列示，以及元数据变更发布 `sys.form.updated` 事件。
"""

import pytest
import pytest_asyncio
from httpx import AsyncClient

from tests_support.menu_metadata import outbox_types, reset_menu_tables, seed_action, seed_business


@pytest_asyncio.fixture(autouse=True)
async def clean_menu_tables(platform_db: None) -> None:
    """菜单元数据表逐用例清场（会话级平台库共享）。

    Args:
        platform_db: 平台库夹具（确保平台库连接串已注入）。
    """
    await reset_menu_tables()


_MENUS = "/api/v1/menus"
_FORMS = "/api/v1/forms"
_BUTTONS = "/api/v1/buttons"
_FIELDS = "/api/v1/fields"
_BUSINESSES = "/api/v1/businesses"
_ACTIONS = "/api/v1/actions"


@pytest.mark.kiwi_id(2242)
async def test_menu_create_update_delete_and_conflicts(client: AsyncClient) -> None:
    """菜单增改删：路径冲突（40203）、父菜单不存在（40201）、被表单引用禁删（40206）。"""
    created = await client.post(
        _MENUS,
        json={
            "parent_id": 0,
            "name": "测试目录",
            "path": "/t-dir",
            "component": None,
            "icon": None,
            "sort": 1,
            "hidden": False,
            "status": "enabled",
            "i18n": {"en-US": "Test dir"},
        },
    )
    assert created.json()["code"] == 0
    menu_id = int(created.json()["data"]["id"])
    assert created.json()["data"]["path"] == "/t-dir"

    duplicated = await client.post(_MENUS, json={"parent_id": 0, "name": "冲突", "path": "/t-dir", "status": "enabled"})
    assert duplicated.json()["code"] == 40203

    bad_parent = await client.post(
        _MENUS, json={"parent_id": 999999999, "name": "孤儿", "path": "/t-orphan", "status": "enabled"}
    )
    assert bad_parent.status_code == 404
    assert bad_parent.json()["code"] == 40201

    updated = await client.put(
        f"{_MENUS}/{menu_id}",
        json={
            "parent_id": 0,
            "name": "测试目录改",
            "path": "/t-dir",
            "component": None,
            "icon": "el:setting",
            "sort": 2,
            "hidden": True,
            "status": "enabled",
            "i18n": {"en-US": "Test dir updated"},
        },
    )
    assert updated.json()["code"] == 0
    assert updated.json()["data"]["name"] == "测试目录改"
    assert updated.json()["data"]["hidden"] is True

    missing = await client.put(
        f"{_MENUS}/999999999",
        json={"parent_id": 0, "name": "无", "path": "/t-none", "status": "enabled"},
    )
    assert missing.status_code == 404
    assert missing.json()["code"] == 40201

    business_id = await seed_business("t_menu")
    linked = await client.post(_FORMS, json={"menu_ids": [menu_id], "business_id": business_id, "status": "enabled"})
    assert linked.json()["code"] == 0

    referenced = await client.delete(f"{_MENUS}/{menu_id}")
    assert referenced.json()["code"] == 40206

    assert (await client.delete(f"{_FORMS}/{linked.json()['data']['id']}")).json()["code"] == 0
    assert (await client.delete(f"{_MENUS}/{menu_id}")).json()["code"] == 0

    tree = await client.get(_MENUS)
    assert all(node["path"] != "/t-dir" for node in tree.json()["data"]["items"])


@pytest.mark.kiwi_id(2242)
async def test_form_button_field_link_rules(client: AsyncClient) -> None:
    """表单 1:1、按钮同动作唯一、字段键唯一（40205）、被引用禁删（40206）。"""
    business_id = await seed_business("t_link")
    action_id = await seed_action(business_id, "create", "新建")

    menu = await client.post(_MENUS, json={"parent_id": 0, "name": "挂接页", "path": "/t-link", "status": "enabled"})
    menu_id = int(menu.json()["data"]["id"])

    unknown_business = await client.post(
        _FORMS, json={"menu_ids": [menu_id], "business_id": 999999999, "status": "enabled"}
    )
    assert unknown_business.status_code == 404
    assert unknown_business.json()["code"] == 40201

    unknown_menu = await client.post(
        _FORMS, json={"menu_ids": [999999999], "business_id": business_id, "status": "enabled"}
    )
    assert unknown_menu.status_code == 404
    assert unknown_menu.json()["code"] == 40201

    # 多对多：同一表单关联两个菜单入口
    second_menu = await client.post(
        _MENUS, json={"parent_id": 0, "name": "挂接页二", "path": "/t-link-2", "status": "enabled"}
    )
    second_menu_id = int(second_menu.json()["data"]["id"])
    form = await client.post(
        _FORMS,
        json={"menu_ids": [menu_id, second_menu_id], "business_id": business_id, "status": "enabled"},
    )
    assert form.json()["code"] == 0
    form_id = int(form.json()["data"]["id"])
    assert sorted(int(item) for item in form.json()["data"]["menu_ids"]) == sorted([menu_id, second_menu_id])
    by_menu = (await client.get(_FORMS, params={"menu_id": second_menu_id})).json()["data"]["items"]
    assert {int(item["id"]) for item in by_menu} == {form_id}

    duplicate_form = await client.post(
        _FORMS, json={"menu_ids": [menu_id], "business_id": business_id, "status": "enabled"}
    )
    assert duplicate_form.json()["code"] == 10003

    # 孤儿表单：无菜单入口，仅出现在全量列表
    orphan_business = await seed_business("t_link_orphan")
    orphan = await client.post(_FORMS, json={"menu_ids": [], "business_id": orphan_business, "status": "enabled"})
    assert orphan.json()["code"] == 0
    assert orphan.json()["data"]["menu_ids"] == []
    orphan_id = int(orphan.json()["data"]["id"])
    all_forms = (await client.get(_FORMS)).json()["data"]["items"]
    assert orphan_id in {int(item["id"]) for item in all_forms}
    assert orphan_id not in {
        int(item["id"]) for item in (await client.get(_FORMS, params={"menu_id": menu_id})).json()["data"]["items"]
    }

    button = await client.post(
        _BUTTONS,
        json={"form_id": form_id, "action_id": action_id, "name": "新增", "type": "toolbar", "sort": 1},
    )
    assert button.json()["code"] == 0

    duplicate_button = await client.post(
        _BUTTONS, json={"form_id": form_id, "action_id": action_id, "name": "新增2", "sort": 2}
    )
    assert duplicate_button.json()["code"] == 10003

    invalid_type = await client.post(
        _BUTTONS, json={"form_id": form_id, "action_id": action_id, "name": "非法", "type": "bad"}
    )
    assert invalid_type.json()["code"] == 10001

    field = await client.post(
        _FIELDS,
        json={
            "form_id": form_id,
            "field_key": "username",
            "name": "用户名",
            "type": "input",
            "sort": 1,
            "i18n": {"en-US": "Username"},
        },
    )
    assert field.json()["code"] == 0

    duplicate_field = await client.post(
        _FIELDS, json={"form_id": form_id, "field_key": "username", "name": "重名", "type": "input"}
    )
    assert duplicate_field.json()["code"] == 40205

    blocked = await client.delete(f"{_FORMS}/{form_id}")
    assert blocked.json()["code"] == 40206

    assert (await client.get(_FIELDS, params={"form_id": form_id})).json()["data"]["items"]
    await client.delete(f"{_FIELDS}/{field.json()['data']['id']}")
    await client.delete(f"{_BUTTONS}/{button.json()['data']['id']}")
    assert (await client.delete(f"{_FORMS}/{form_id}")).json()["code"] == 0
    assert (await client.get(_BUTTONS, params={"form_id": form_id})).json()["data"]["items"] == []


@pytest.mark.kiwi_id(2242)
async def test_business_action_read_lists(client: AsyncClient) -> None:
    """业务 / 动作码只读列示：业务清单含直插业务码、动作清单按业务过滤。"""
    business_id = await seed_business("t_read", "只读业务")
    await seed_action(business_id, "query", "查询")
    await seed_action(business_id, "manage", "管理")

    businesses = await client.get(_BUSINESSES)
    assert businesses.json()["code"] == 0
    assert "t_read" in [item["code"] for item in businesses.json()["data"]["items"]]

    actions = await client.get(_ACTIONS, params={"business_id": business_id})
    assert sorted(item["code"] for item in actions.json()["data"]["items"]) == ["manage", "query"]

    others = await client.get(_ACTIONS, params={"business_id": business_id + 1})
    assert others.json()["data"]["items"] == []


@pytest.mark.kiwi_id(2242)
async def test_form_updated_event_published(client: AsyncClient) -> None:
    """元数据变更在同一事务内经发件箱发布 `sys.form.updated`（只做发布侧，无消费者）。"""
    menu = await client.post(_MENUS, json={"parent_id": 0, "name": "事件页", "path": "/t-event", "status": "enabled"})
    menu_id = int(menu.json()["data"]["id"])

    assert "sys.form.updated" in await outbox_types(f"menu:{menu_id}")
