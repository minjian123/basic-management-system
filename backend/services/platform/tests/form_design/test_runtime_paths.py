"""表单定制运行期路径（Kiwi 2526）：选项集快照 / 权限收窄 / 自建字段合并 / 导入列派生。

本文件补齐「接口能触达但主流程未走到」的分支：枚举字段的选项集快照、字段权限
`visible` / `editable` 收窄对布局引用（分区 / 分组 / 查询区 / 明细列 / 字典高级查询）的连带剔除、
自建字段并入字段清单、只有属性没有布局的层级，以及 `user` 导入列派生依赖的
`layout_columns_of` 三表读取。
"""

from collections.abc import Callable
from typing import Any, cast

import pytest
import pytest_asyncio
from httpx import AsyncClient

from bms_core.core.concurrent import (
    ConcurrentStableDict,
    ConcurrentStableFrozenList,
    ConcurrentStableList,
    ConcurrentStableSet,
)
from bms_core.db.unit_of_work import DbUnitOfWork
from bms_core.formdesign.import_columns import layout_columns_of
from bms_core.formdesign.layout import dump_layout_config, normalize_layout
from bms_core.models.platform.form_design import SysFieldExt, SysFormFieldAttr, SysFormLayout
from bms_core.optionset.base import BaseOptionSetRegistry, OptionItem
from bms_core.optionset.local import LocalOptionSetRegistry
from bms_core.permission.field import BaseFieldPermissionProvider, FieldPermission
from bms_core.testing.namespace import Namespace
from bms_platform import wiring as wiring_module
from bms_platform.domains.form_design.repositories.adapters import OptionSetAdapter
from bms_platform.domains.form_design.repositories.layout import (
    FieldAttrRepository,
    FormLayoutRepository,
)
from bms_platform.domains.form_design.services.assemble import LevelSnapshot, assemble_layout
from bms_platform.wiring import build_local_form_validator
from tests_support.form_design import run_statement, tenant_session
from tests_support.permission_admin import TEST_SUBJECT, grant_system_admin, setup_min_tenant

from .helpers import (
    create_probe_table,
    drop_probe_table,
    register_form_key,
    seed_business,
    seed_form_with_fields,
    tenant_url,
)

pytestmark = pytest.mark.kiwi_id(2526)

_LAYOUTS = "/api/v1/form-design/layouts"
_ATTRS = "/api/v1/form-design/attrs"
_FIELDS = "/api/v1/form-design/fields"
_EFFECTIVE = "/api/v1/forms/{code}/layout-effective"
_VALIDATE = "/api/v1/forms/{code}/validate"

_OPTION_SET_KEY = "bms.tenant.status"
"""已登记的静态选项集（`deploy/registry/platform.toml`），枚举字段的属性校验与快照下发用。"""


class _StubPermissionProvider(BaseFieldPermissionProvider):
    """字段权限桩：`name` 不可见、`status` 不可编辑（其余字段全开）。"""

    async def resolve(
        self,
        *,
        role_ids: ConcurrentStableSet[int],
        form_ids: ConcurrentStableSet[int],
    ) -> ConcurrentStableList[FieldPermission]:
        """返回两条固定收窄项（与角色 / 表单无关）。

        Args:
            role_ids: 角色集（桩忽略）。
            form_ids: 表单集（桩忽略）。

        Returns:
            ConcurrentStableList[FieldPermission]: 收窄项。
        """
        del role_ids, form_ids
        return ConcurrentStableList(
            (
                FieldPermission(form_id=1, field_key="name", visible=False),
                FieldPermission(form_id=1, field_key="status", editable=False),
                FieldPermission(form_id=1, field_key="status", visible=True),
            )
        )


def _permission_factory(_tenant_session: Any, _platform_session: Any) -> BaseFieldPermissionProvider:
    """工厂桩：返回固定权限提供者。

    Args:
        _tenant_session: 租户库会话（桩忽略）。
        _platform_session: 平台库会话（桩忽略）。

    Returns:
        BaseFieldPermissionProvider: 固定提供者。
    """
    return _StubPermissionProvider()


def _permission_registry() -> Callable[[Any, Any], BaseFieldPermissionProvider]:
    """工厂登记桩：装配面每次取工厂都得到同一个桩。

    Returns:
        Callable[[Any, Any], BaseFieldPermissionProvider]: 工厂。
    """
    return _permission_factory


@pytest_asyncio.fixture(autouse=True)
async def prepared(tenant_db: str) -> None:
    """租户库 + 系统管理员主体 + 四表存在性（不清表，隔离靠命名空间）。

    Args:
        tenant_db: 共享测试租户库连接串。
    """
    await setup_min_tenant(tenant_db)


def _data(response: Any, label: str) -> Any:
    r"""取统一响应 \`data\`（失败时带完整响应体）。"""
    body = response.json()
    data = body.get("data")
    assert data is not None, f"{label} 失败（HTTP {response.status_code}）：{response.text}"
    return data


async def _form(ns: Namespace, suffix: str, *, app: Any, table: bool = False, with_tags: bool = False) -> str:
    """造业务码 + 表单 + 两个平台字段（文本 / 枚举）。

    Args:
        ns: 用例命名空间。
        suffix: 后缀。
        app: 应用实例（登记表单标识清单）。
        table: 是否建探针物理表（自建字段建列用）。
        with_tags: 是否加一个多选枚举字段（`tags`）。

    Returns:
        str: 表单标识（业务码）。
    """
    code = f"{ns.prefix}_{suffix}"
    business_id = await seed_business(code)
    fields: ConcurrentStableList[tuple[str, str, str, int]] = ConcurrentStableList(
        (
            ("name", "名称", "text", 1),
            ("status", "状态", "option", 2),
        )
    )
    if with_tags:
        fields.add(("tags", "标签", "option_multi", 3))
    await seed_form_with_fields(business_id, fields)
    if table:
        await create_probe_table(tenant_url(), f"biz_{code}")
        register_form_key(app, code, f"biz_{code}")
    return code


async def _save_layout(client: AsyncClient, code: str, layout_config: Any, *, scope: str = "tenant") -> None:
    """保存某层级布局（失败即断言，便于定位）。

    Args:
        client: 接口客户端。
        code: 表单标识。
        layout_config: 布局配置。
        scope: 层级。
    """
    saved = await client.put(
        _LAYOUTS,
        json={"form_code": code, "scope": scope, "role_id": 0, "layout_config": layout_config},
    )
    assert saved.json()["code"] == 0, saved.text


async def test_effective_ships_option_set_snapshot(client: AsyncClient, service_app: Any, ns: Namespace) -> None:
    """枚举字段的选项集快照随生效布局一次下发（平台字段按属性、自建字段按字段行两条来源）。"""
    code = await _form(ns, "optset", app=service_app, table=True)
    await _save_layout(client, code, {"main": {"sections": [{"key": "s", "fields": ["name", "status"]}]}})
    attrs = await client.put(
        _ATTRS,
        json={
            "form_code": code,
            "scope": "tenant",
            "role_id": 0,
            "fields": [{"field_key": "status", "field_type": "option", "attrs": {"optionSetKey": _OPTION_SET_KEY}}],
        },
    )
    assert attrs.json()["code"] == 0, attrs.text
    created = await client.post(
        _FIELDS,
        json={
            "form_code": code,
            "field_key": "stage",
            "name": "阶段",
            "type": "option",
            "option_set_key": _OPTION_SET_KEY,
            "sort": 3,
        },
    )
    assert created.json()["code"] == 0, created.text

    data = _data(await client.get(_EFFECTIVE.format(code=code)), "生效布局")
    keys = [item["option_set_key"] for item in data["option_sets"]]
    assert keys == [_OPTION_SET_KEY], keys
    items = data["option_sets"][0]["items"]
    assert len(items) > 0
    assert "value" in items[0] and "sort" in items[0]
    field_keys = [item["key"] for item in data["fields"]]
    assert field_keys == ["name", "status", "stage"], field_keys


async def test_effective_applies_field_permissions(
    client: AsyncClient, service_app: Any, ns: Namespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """权限优先：`visible=false` 的字段连同全部布局引用剔除，`editable=false` 保留并标记。"""
    monkeypatch.setattr(wiring_module, "current_field_permission_provider_factory", _permission_registry)
    code = await _form(ns, "perm", app=service_app)
    await _save_layout(
        client,
        code,
        {
            "main": {
                "sections": [
                    {"key": "s1", "fields": ["name"]},
                    {"key": "s2", "fields": ["status"], "groups": [{"key": "g1", "fields": ["name"]}]},
                ]
            },
            "query": {"fields": ["name"]},
            "detail": {"columns": ["name", {"key": "status", "width": 180}]},
            "dictAdvanced": {"fields": ["name"], "operators": ["eq"], "scheme": "advanced"},
        },
    )
    data = _data(await client.get(_EFFECTIVE.format(code=code)), "生效布局")
    assert [item["key"] for item in data["fields"]] == ["status"]
    assert data["permissions"]["status"] == {"visible": True, "editable": False}
    layout = data["layout"]
    sections = layout["main"]["sections"]
    assert [section["key"] for section in sections] == ["s1", "s2"]
    assert sections[0]["fields"] == []
    assert "groups" not in sections[1]
    assert "query" not in layout
    detail_columns = layout["detail"]["columns"]
    assert [column["key"] for column in detail_columns] == ["status"]
    advanced = layout["dictAdvanced"]
    assert advanced == {"operators": ["eq"], "scheme": "advanced"}


async def test_strip_invisible_keeps_advanced_with_scheme(
    client: AsyncClient, service_app: Any, ns: Namespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """字典高级查询在被剔除后仍有 `scheme` 时保留（不是整段丢弃）。"""
    monkeypatch.setattr(wiring_module, "current_field_permission_provider_factory", _permission_registry)
    code = await _form(ns, "permadv", app=service_app)
    await _save_layout(
        client,
        code,
        {
            "main": {"sections": [{"key": "s", "fields": ["status"]}]},
            "dictAdvanced": {"fields": ["name"], "columns": ["name"], "scheme": "advanced"},
        },
    )
    data = _data(await client.get(_EFFECTIVE.format(code=code)), "生效布局")
    advanced = data["layout"]["dictAdvanced"]
    assert advanced == {"scheme": "advanced"}


async def test_effective_merges_ext_field(client: AsyncClient, service_app: Any, ns: Namespace) -> None:
    """自建字段并入字段清单（`group=tenant`、按 `sort` 参与排序）。"""
    code = await _form(ns, "extmerge", app=service_app, table=True)
    created = await client.post(
        _FIELDS,
        json={"form_code": code, "field_key": "extra", "name": "补充", "type": "text", "sort": 0},
    )
    assert created.json()["code"] == 0, created.text
    data = _data(await client.get(_EFFECTIVE.format(code=code)), "生效布局")
    merged = next(item for item in data["fields"] if item["key"] == "extra")
    assert merged["group"] == "tenant"
    assert data["fields"][0]["key"] == "extra"


async def test_attrs_without_layout_still_apply(client: AsyncClient, service_app: Any, ns: Namespace) -> None:
    """只有属性、没有布局的层级也能命中（属性层独立于布局存在；布局走空回退）。"""
    code = await _form(ns, "attrsonly", app=service_app)
    saved = await client.put(
        _ATTRS,
        json={
            "form_code": code,
            "scope": "tenant",
            "role_id": 0,
            "fields": [{"field_key": "name", "field_type": "text", "attrs": {"required": True}}],
        },
    )
    assert saved.json()["code"] == 0, saved.text
    data = _data(await client.get(_EFFECTIVE.format(code=code)), "生效布局")
    # 属性与布局同层同源：该层无布局时走空回退，属性不单独生效（本轮口径）
    assert data["fallback"] is True
    assert [item["key"] for item in data["fields"]] == ["name", "status"]


async def test_layout_columns_of_reads_layout_and_ext_fields(
    client: AsyncClient, service_app: Any, ns: Namespace, tenant_db: str
) -> None:
    """导入列派生读取三表：布局序（租户层优先）+ 自建字段列规格；无布局时返回空键序。"""
    code = await _form(ns, "impcols", app=service_app, table=True)
    await _save_layout(client, code, {"main": {"sections": [{"key": "s", "fields": ["status", "name"]}]}})
    created = await client.post(_FIELDS, json={"form_code": code, "field_key": "extra", "name": "补充", "type": "text"})
    assert created.json()["code"] == 0, created.text

    async with tenant_session(tenant_db) as session:
        keys, specs = await layout_columns_of(
            session,
            form_code=code,
            layout_model=SysFormLayout,
            attr_model=SysFormFieldAttr,
            ext_model=SysFieldExt,
        )
    assert list(keys) == ["status", "name"]
    assert specs["extra"].title == "补充"

    async with tenant_session(tenant_db) as session:
        empty_keys, empty_specs = await layout_columns_of(
            session,
            form_code=f"{ns.prefix}_nolayout",
            layout_model=SysFormLayout,
            attr_model=SysFormFieldAttr,
            ext_model=SysFieldExt,
        )
    assert len(empty_keys) == 0
    assert len(empty_specs) == 0


async def test_layout_columns_of_falls_back_to_platform_level(ns: Namespace, tenant_db: str) -> None:
    """租户层为空布局时回落到平台层（平台层配置由运维直插，此处用仓储构造同形态数据）。"""
    code = f"{ns.prefix}_platformlvl"
    layout = normalize_layout({"main": {"sections": [{"key": "s", "fields": ["name"]}]}})
    async with tenant_session(tenant_db) as session:
        await FormLayoutRepository(session).create(
            form_code=code,
            scope="platform",
            role_id=0,
            layout_config=dump_layout_config(layout),
            status="enabled",
        )
        await session.commit()
    async with tenant_session(tenant_db) as session:
        keys, specs = await layout_columns_of(
            session,
            form_code=code,
            layout_model=SysFormLayout,
            attr_model=SysFormFieldAttr,
            ext_model=SysFieldExt,
        )
    assert list(keys) == ["name"]
    assert len(specs) == 0


async def test_save_layout_rejects_unknown_form(client: AsyncClient, ns: Namespace) -> None:
    """业务码不存在或不可定制 → 40401（保存期即拒）。"""
    response = await client.put(
        _LAYOUTS,
        json={
            "form_code": f"{ns.prefix}_absent",
            "scope": "tenant",
            "role_id": 0,
            "layout_config": {"main": {"sections": []}},
        },
    )
    assert response.status_code == 404
    assert response.json()["code"] == 40401


async def test_validate_option_rules_and_multi_values(client: AsyncClient, service_app: Any, ns: Namespace) -> None:
    """枚举 / 多选的类型与值域规则：多选值域越界、长度越界、单选取值越界均拒，合法值通过。"""
    code = await _form(ns, "optrule", app=service_app, with_tags=True)
    await _save_layout(client, code, {"main": {"sections": [{"key": "s", "fields": ["status", "tags"]}]}})
    attrs = await client.put(
        _ATTRS,
        json={
            "form_code": code,
            "scope": "tenant",
            "role_id": 0,
            "fields": [
                {"field_key": "status", "field_type": "option", "attrs": {"optionSetKey": _OPTION_SET_KEY}},
                {
                    "field_key": "tags",
                    "field_type": "option_multi",
                    "attrs": {"optionSetKey": _OPTION_SET_KEY, "rules": [{"kind": "length", "max": 1}]},
                },
            ],
        },
    )
    assert attrs.json()["code"] == 0, attrs.text

    out_of_domain = _data(await client.post(_VALIDATE.format(code=code), json={"values": {"status": "bogus"}}), "校验")
    assert [item["rule"] for item in out_of_domain["errors"]] == ["options"]

    multi_bad = _data(await client.post(_VALIDATE.format(code=code), json={"values": {"tags": ["bogus"]}}), "校验")
    assert [item["rule"] for item in multi_bad["errors"]] == ["options"]

    multi_length = _data(
        await client.post(
            _VALIDATE.format(code=code),
            json={"values": {"tags": ["provisioning", "active"]}},
        ),
        "校验",
    )
    assert [item["rule"] for item in multi_length["errors"]] == ["length"]

    assert (
        _data(await client.post(_VALIDATE.format(code=code), json={"values": {"status": "active"}}), "校验")["valid"]
        is True
    )


async def test_effective_picks_role_level_layout(client: AsyncClient, service_app: Any, ns: Namespace) -> None:
    """角色视图层级优先：给当前用户的内置角色配布局后，生效来源为 `role`。"""
    role_id = await grant_system_admin(int(TEST_SUBJECT))
    code = await _form(ns, "rolelvl", app=service_app)
    saved = await client.put(
        _LAYOUTS,
        json={
            "form_code": code,
            "scope": "role",
            "role_id": role_id,
            "layout_config": {"main": {"sections": [{"key": "r", "fields": ["status"]}]}},
        },
    )
    assert saved.json()["code"] == 0, saved.text
    data = _data(await client.get(_EFFECTIVE.format(code=code)), "生效布局")
    assert data["source"] == "role"
    assert [item["key"] for item in data["fields"]] == ["name", "status"]
    assert data["layout"]["main"]["sections"][0]["key"] == "r"


async def test_effective_keeps_group_and_drops_empty_advanced(
    client: AsyncClient, service_app: Any, ns: Namespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """权限剔除后仍含可见字段的分组保留；字典高级查询引用全被剔除且无 `scheme` 时整段丢弃。"""
    monkeypatch.setattr(wiring_module, "current_field_permission_provider_factory", _permission_registry)
    code = await _form(ns, "permgroup", app=service_app)
    await _save_layout(
        client,
        code,
        {
            "main": {
                "sections": [
                    {
                        "key": "s",
                        "fields": ["status"],
                        "groups": [{"key": "g1", "fields": ["name"]}, {"key": "g2", "fields": ["status"]}],
                    }
                ]
            },
            "dictAdvanced": {"fields": ["name"], "columns": ["name"]},
        },
    )
    data = _data(await client.get(_EFFECTIVE.format(code=code)), "生效布局")
    groups = data["layout"]["main"]["sections"][0]["groups"]
    assert [group["key"] for group in groups] == ["g2"]
    assert "dictAdvanced" not in data["layout"]


async def test_delete_unknown_layout_and_attr(client: AsyncClient, ns: Namespace) -> None:
    """删除不存在的主键 → 10002（布局 / 属性两个端点）。"""
    layout = await client.delete(f"{_LAYOUTS}/999999999")
    assert layout.json()["code"] == 10002
    attrs = await client.delete(f"{_ATTRS}/999999999")
    assert attrs.json()["code"] == 10002


async def test_list_levels_dedups_scope(client: AsyncClient, service_app: Any, ns: Namespace) -> None:
    """同层级多角色视图只上报一次层级名（`levels` 去重保序）。"""
    code = await _form(ns, "dedup", app=service_app)
    for role_id in (8001, 8002):
        saved = await client.put(
            _LAYOUTS,
            json={
                "form_code": code,
                "scope": "role",
                "role_id": role_id,
                "layout_config": {"main": {"sections": [{"key": f"r{role_id}", "fields": ["name"]}]}},
            },
        )
        assert saved.json()["code"] == 0, saved.text
    data = _data(await client.get(_LAYOUTS, params={"form_code": code}), "布局列表")
    assert data["levels"] == ["role"]


async def test_field_endpoints_reject_malformed_id(client: AsyncClient, ns: Namespace) -> None:
    """路径主键非数字 → 10001（更新与重试两个端点）。"""
    updated = await client.put(f"{_FIELDS}/abc", json={"sort": 1})
    assert updated.json()["code"] == 10001
    retried = await client.post(f"{_FIELDS}/abc/retry")
    assert retried.json()["code"] == 10001


async def test_field_unknown_form_and_unresolved_table(client: AsyncClient, ns: Namespace) -> None:
    """业务码不存在 / 物理表不可解析 → 40401（列表与新建各一次）。"""
    listed = await client.get(_FIELDS, params={"form_code": f"{ns.prefix}_absent"})
    assert listed.json()["code"] == 40401
    no_table = f"{ns.prefix}_notable"
    business_id = await seed_business(no_table)
    await seed_form_with_fields(business_id, ConcurrentStableList((("name", "名称", "text", 1),)))
    created = await client.post(
        _FIELDS, json={"form_code": no_table, "field_key": "x_col", "name": "无表", "type": "text"}
    )
    assert created.json()["code"] == 40401


async def test_field_create_rejects_option_on_plain_type(client: AsyncClient, service_app: Any, ns: Namespace) -> None:
    """非枚举字段带选项集 → 40404。"""
    code = await _form(ns, "optplain", app=service_app, table=True)
    response = await client.post(
        _FIELDS,
        json={
            "form_code": code,
            "field_key": "plain_opt",
            "name": "普通",
            "type": "text",
            "option_set_key": _OPTION_SET_KEY,
        },
    )
    assert response.json()["code"] == 40404


async def test_field_update_branches(client: AsyncClient, service_app: Any, ns: Namespace) -> None:
    """更新分支：改状态与排序 / 非法状态 / 未注册选项集 / 非枚举带选项集 / 主键不存在。"""
    code = await _form(ns, "upd", app=service_app, table=True)
    created = _data(
        await client.post(_FIELDS, json={"form_code": code, "field_key": "u_col", "name": "旧名", "type": "text"}),
        "新建",
    )
    field_id = created["id"]
    renamed = await client.put(f"{_FIELDS}/{field_id}", json={"name": "新名", "sort": 9})
    assert renamed.json()["code"] == 0
    assert renamed.json()["data"]["name"] == "新名"
    assert renamed.json()["data"]["sort"] == 9
    bad_status = await client.put(f"{_FIELDS}/{field_id}", json={"status": "unknown"})
    assert bad_status.json()["code"] == 40404
    unknown_option = await client.put(f"{_FIELDS}/{field_id}", json={"option_set_key": "bms.absent.set"})
    assert unknown_option.json()["code"] == 40404
    plain_option = await client.put(f"{_FIELDS}/{field_id}", json={"option_set_key": _OPTION_SET_KEY})
    assert plain_option.json()["code"] == 40404
    missing = await client.put(f"{_FIELDS}/999999999", json={"sort": 1})
    assert missing.json()["code"] == 10002
    missing_retry = await client.post(f"{_FIELDS}/999999999/retry")
    assert missing_retry.json()["code"] == 10002


async def test_field_recreate_after_disable(client: AsyncClient, service_app: Any, ns: Namespace) -> None:
    """停用后同键重建 → 复用同一行（走更新分支）并重新建列。"""
    code = await _form(ns, "reuse", app=service_app, table=True)
    first = _data(
        await client.post(_FIELDS, json={"form_code": code, "field_key": "reuse_col", "name": "复用", "type": "text"}),
        "新建",
    )
    disabled = await client.put(f"{_FIELDS}/{first['id']}", json={"status": "disabled"})
    assert disabled.json()["code"] == 0
    payload = {"form_code": code, "field_key": "reuse_col", "name": "复用二", "type": "text"}
    again = _data(await client.post(_FIELDS, json=payload), "重建")
    assert again["id"] == first["id"]
    assert again["ddl_status"] == "active"


async def test_ddl_idempotent_when_column_present(client: AsyncClient, service_app: Any, ns: Namespace) -> None:
    """列已存在时重试按幂等命中（不重复加列）。"""
    code = await _form(ns, "idem", app=service_app, table=True)
    created = _data(
        await client.post(_FIELDS, json={"form_code": code, "field_key": "idem_col", "name": "幂等", "type": "text"}),
        "新建",
    )
    retried = _data(await client.post(f"{_FIELDS}/{created['id']}/retry"), "重试")
    assert retried["ddl_status"] == "active"


async def test_ddl_failure_on_non_table_target(client: AsyncClient, service_app: Any, ns: Namespace) -> None:
    """目标对象不是可加列的实表（视图）时 DDL 失败 → `failed` 且不抛给调用方。"""
    code = f"{ns.prefix}_view"
    business_id = await seed_business(code)
    await seed_form_with_fields(business_id, ConcurrentStableList((("name", "名称", "text", 1),)))
    table = f"biz_{code}"
    await drop_probe_table(tenant_url(), table)
    await run_statement(tenant_url(), f"DROP VIEW IF EXISTS {table}")
    await run_statement(tenant_url(), f"CREATE VIEW {table} AS SELECT 1 AS id")
    register_form_key(service_app, code, table)
    created = _data(
        await client.post(_FIELDS, json={"form_code": code, "field_key": "view_col", "name": "视图", "type": "text"}),
        "新建（预期建列失败）",
    )
    assert created["ddl_status"] == "failed"


async def test_purge_level_without_rows_returns_false(tenant_db: str, ns: Namespace) -> None:
    """仓储层：层级本无行时物理删除返回 False（不误报删到）。"""
    async with tenant_session(tenant_db) as session:
        layouts = FormLayoutRepository(session)
        assert await layouts.purge_by_level(f"{ns.prefix}_nopurge", "tenant", 0) is False
        attrs = FieldAttrRepository(session)
        assert await attrs.purge_level(f"{ns.prefix}_nopurge", "tenant", 0) is False
        await session.commit()


async def test_metadata_returns_none_when_form_row_missing(client: AsyncClient, ns: Namespace) -> None:
    """业务码存在但表单行缺失 → 视为不可定制（40401）。"""
    code = f"{ns.prefix}_noform"
    await seed_business(code)
    response = await client.get(_LAYOUTS, params={"form_code": code})
    assert response.status_code == 404
    assert response.json()["code"] == 40401


async def test_validate_applies_permissions_and_ext_fields(
    client: AsyncClient, service_app: Any, ns: Namespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """校验同源权限：不可见字段不参与校验、不可编辑字段跳必填但仍校验值域；自建字段一并校验。"""
    monkeypatch.setattr(wiring_module, "current_field_permission_provider_factory", _permission_registry)
    code = await _form(ns, "valperm", app=service_app, table=True)
    await _save_layout(client, code, {"main": {"sections": [{"key": "s", "fields": ["name", "status"]}]}})
    attrs = await client.put(
        _ATTRS,
        json={
            "form_code": code,
            "scope": "tenant",
            "role_id": 0,
            "fields": [
                {"field_key": "name", "field_type": "text", "attrs": {"required": True}},
                {"field_key": "status", "field_type": "option", "attrs": {"optionSetKey": _OPTION_SET_KEY}},
            ],
        },
    )
    assert attrs.json()["code"] == 0, attrs.text
    created = await client.post(
        _FIELDS,
        json={
            "form_code": code,
            "field_key": "stage",
            "name": "阶段",
            "type": "option",
            "option_set_key": _OPTION_SET_KEY,
        },
    )
    assert created.json()["code"] == 0, created.text

    result = _data(
        await client.post(
            _VALIDATE.format(code=code),
            json={"values": {"name": "", "status": "bogus", "stage": "bogus"}},
        ),
        "校验",
    )
    pairs = {(item["field_key"], item["rule"]) for item in result["errors"]}
    assert ("name", "required") not in pairs
    assert ("status", "options") in pairs
    assert ("stage", "options") in pairs


async def test_validate_attrs_only_level_backfills(client: AsyncClient, service_app: Any, ns: Namespace) -> None:
    """只有属性没有布局时，校验仍按该层属性求值（属性索引第二轮回填）。"""
    code = await _form(ns, "valattr", app=service_app)
    saved = await client.put(
        _ATTRS,
        json={
            "form_code": code,
            "scope": "tenant",
            "role_id": 0,
            "fields": [{"field_key": "name", "field_type": "text", "attrs": {"required": True}}],
        },
    )
    assert saved.json()["code"] == 0, saved.text
    result = _data(await client.post(_VALIDATE.format(code=code), json={"values": {"name": ""}}), "校验")
    assert [item["rule"] for item in result["errors"]] == ["required"]


_FAKE_OPTION_ITEMS: ConcurrentStableList[OptionItem] = ConcurrentStableList(
    (
        OptionItem(value="a", label="A", sort=1),
        OptionItem(value="b", label="B", label_key="k.b", color="success", disabled=True, sort=2),
    )
)


class _FakeOptionInfo:
    """选项集解析结果桩（只暴露 `items`，与注册表返回形态一致）。"""

    def __init__(self, items: ConcurrentStableList[OptionItem]) -> None:
        """初始化。

        Args:
            items: 条目清单。
        """
        self.items = items


class _FakeOptionRegistry:
    """选项集注册表桩：仅 `fake` 键可解析。"""

    def resolve(self, option_set_key: str) -> _FakeOptionInfo:
        """解析条目。

        Args:
            option_set_key: 选项集标识（桩忽略）。

        Returns:
            _FakeOptionInfo: 固定条目。
        """
        del option_set_key
        return _FakeOptionInfo(_FAKE_OPTION_ITEMS)

    def get(self, option_set_key: str) -> _FakeOptionInfo | None:
        """标识是否可解析。

        Args:
            option_set_key: 选项集标识。

        Returns:
            _FakeOptionInfo | None: `fake` 键给结果，其余 None。
        """
        return _FakeOptionInfo(_FAKE_OPTION_ITEMS) if option_set_key == "fake" else None


async def test_delete_layout_and_attr_reject_malformed_id(client: AsyncClient, ns: Namespace) -> None:
    """删除路径主键非数字 → 10001（布局 / 属性两个端点）。"""
    layout = await client.delete(f"{_LAYOUTS}/abc")
    assert layout.json()["code"] == 10001
    attrs = await client.delete(f"{_ATTRS}/abc")
    assert attrs.json()["code"] == 10001


async def test_delete_platform_level_requires_platform_admin(
    client: AsyncClient, service_app: Any, ns: Namespace, tenant_db: str
) -> None:
    """平台默认层级的删除要求平台超管（布局 / 属性各一次，30001）。"""
    code = await _form(ns, "pdel", app=service_app)
    layout = normalize_layout({"main": {"sections": [{"key": "p", "fields": ["name"]}]}})
    async with tenant_session(tenant_db) as session:
        row = await FormLayoutRepository(session).create(
            form_code=code,
            scope="platform",
            role_id=0,
            layout_config=dump_layout_config(layout),
            status="enabled",
        )
        attr_row = await FieldAttrRepository(session).create(
            form_code=code,
            scope="platform",
            role_id=0,
            field_key="name",
            attrs='{"required":true}',
        )
        await session.commit()
        layout_id = row.id
        attr_id = attr_row.id
    denied_layout = await client.delete(f"{_LAYOUTS}/{layout_id}")
    assert denied_layout.json()["code"] == 30001
    denied_attr = await client.delete(f"{_ATTRS}/{attr_id}")
    assert denied_attr.json()["code"] == 30001


async def test_save_attrs_rejects_unknown_form_and_bad_scope(
    client: AsyncClient, service_app: Any, ns: Namespace
) -> None:
    """属性保存：业务码不存在 40401 / 平台层级要求超管 30001 / 非角色层级带角色 ID 40403。"""
    unknown = await client.put(
        _ATTRS,
        json={
            "form_code": f"{ns.prefix}_absent",
            "scope": "tenant",
            "role_id": 0,
            "fields": [{"field_key": "name", "field_type": "text", "attrs": {"required": True}}],
        },
    )
    assert unknown.json()["code"] == 40401

    code = await _form(ns, "attrscope", app=service_app)
    platform = await client.put(
        _ATTRS,
        json={
            "form_code": code,
            "scope": "platform",
            "role_id": 0,
            "fields": [{"field_key": "name", "field_type": "text", "attrs": {"required": True}}],
        },
    )
    assert platform.json()["code"] == 30001

    mismatched = await client.put(
        _ATTRS,
        json={
            "form_code": code,
            "scope": "tenant",
            "role_id": 12,
            "fields": [{"field_key": "name", "field_type": "text", "attrs": {"required": True}}],
        },
    )
    assert mismatched.json()["code"] == 40403


async def test_option_snapshot_merges_attr_and_ext_sources(
    client: AsyncClient, service_app: Any, ns: Namespace
) -> None:
    """选项集快照两条来源都计入（属性行一条、自建字段一条，同键去重）。"""
    code = await _form(ns, "optset2", app=service_app, table=True)
    await _save_layout(client, code, {"main": {"sections": [{"key": "s", "fields": ["status"]}]}})
    attrs = await client.put(
        _ATTRS,
        json={
            "form_code": code,
            "scope": "tenant",
            "role_id": 0,
            "fields": [
                {
                    "field_key": "status",
                    "field_type": "option",
                    "attrs": {"optionSetKey": "bms.tenant.module_status"},
                }
            ],
        },
    )
    assert attrs.json()["code"] == 0, attrs.text
    created = await client.post(
        _FIELDS,
        json={
            "form_code": code,
            "field_key": "stage",
            "name": "阶段",
            "type": "option",
            "option_set_key": _OPTION_SET_KEY,
        },
    )
    assert created.json()["code"] == 0, created.text
    data = _data(await client.get(_EFFECTIVE.format(code=code)), "生效布局")
    assert sorted(item["option_set_key"] for item in data["option_sets"]) == [
        "bms.tenant.module_status",
        _OPTION_SET_KEY,
    ]


async def test_validate_role_level_attrs(client: AsyncClient, service_app: Any, ns: Namespace) -> None:
    """角色层布局 + 角色层属性：校验按角色层属性求值（属性索引首轮命中角色层）。"""
    role_id = await grant_system_admin(int(TEST_SUBJECT))
    code = await _form(ns, "valrole", app=service_app)
    saved = await client.put(
        _LAYOUTS,
        json={
            "form_code": code,
            "scope": "role",
            "role_id": role_id,
            "layout_config": {"main": {"sections": [{"key": "r", "fields": ["name"]}]}},
        },
    )
    assert saved.json()["code"] == 0, saved.text
    saved_attrs = await client.put(
        _ATTRS,
        json={
            "form_code": code,
            "scope": "role",
            "role_id": role_id,
            "fields": [{"field_key": "name", "field_type": "text", "attrs": {"required": True}}],
        },
    )
    assert saved_attrs.json()["code"] == 0, saved_attrs.text
    result = _data(await client.post(_VALIDATE.format(code=code), json={"values": {"name": ""}}), "校验")
    assert [item["rule"] for item in result["errors"]] == ["required"]


async def test_validate_type_and_rule_fallbacks(client: AsyncClient, service_app: Any, ns: Namespace) -> None:
    """类型与规则兜底：开关非布尔 / 多选给标量 / 未覆盖类型放行 / 长度下限 / 范围非数值 / 正则非字符串。"""
    code = f"{ns.prefix}_types"
    business_id = await seed_business(code)
    await seed_form_with_fields(
        business_id,
        ConcurrentStableList(
            (
                ("enabled", "启用", "switch", 1),
                ("tags", "标签", "option_multi", 2),
                ("when", "时间", "datetime", 3),
                ("code", "编码", "text", 4),
                ("note", "备注", "text", 5),
            )
        ),
    )
    await _save_layout(
        client,
        code,
        {"main": {"sections": [{"key": "s", "fields": ["enabled", "tags", "when", "code", "note"]}]}},
    )
    saved = await client.put(
        _ATTRS,
        json={
            "form_code": code,
            "scope": "tenant",
            "role_id": 0,
            "fields": [
                {"field_key": "code", "field_type": "text", "attrs": {"rules": [{"kind": "length", "min": 3}]}},
                {
                    "field_key": "note",
                    "field_type": "text",
                    "attrs": {"rules": [{"kind": "range", "min": 1, "max": 3}]},
                },
                {
                    "field_key": "when",
                    "field_type": "datetime",
                    "attrs": {"rules": [{"kind": "pattern", "pattern": "^x"}]},
                },
            ],
        },
    )
    assert saved.json()["code"] == 0, saved.text

    bad_switch = _data(await client.post(_VALIDATE.format(code=code), json={"values": {"enabled": "yes"}}), "校验")
    assert [item["rule"] for item in bad_switch["errors"]] == ["type"]

    bad_multi = _data(await client.post(_VALIDATE.format(code=code), json={"values": {"tags": "a"}}), "校验")
    assert [item["rule"] for item in bad_multi["errors"]] == ["type"]

    short_code = _data(await client.post(_VALIDATE.format(code=code), json={"values": {"code": "ab"}}), "校验")
    assert [item["rule"] for item in short_code["errors"]] == ["length"]

    ranged = _data(await client.post(_VALIDATE.format(code=code), json={"values": {"note": "文本"}}), "校验")
    assert ranged["valid"] is True, ranged
    # 正则规则落在非字符串类型字段上：值为字符串时照常匹配（`datetime` 不属类型白名单，靠规则拦截）
    unmatched = _data(await client.post(_VALIDATE.format(code=code), json={"values": {"when": "2026-01-01"}}), "校验")
    assert [item["rule"] for item in unmatched["errors"]] == ["pattern"]
    matched = _data(await client.post(_VALIDATE.format(code=code), json={"values": {"when": "x"}}), "校验")
    assert matched["valid"] is True


async def test_validate_option_field_without_option_set_passes(
    client: AsyncClient, service_app: Any, ns: Namespace
) -> None:
    """枚举字段无属性配置（无选项集来源）时值域无法判定 → 放行（不误报）。"""
    code = await _form(ns, "nooptset", app=service_app)
    await _save_layout(client, code, {"main": {"sections": [{"key": "s", "fields": ["status"]}]}})
    saved = await client.put(
        _ATTRS,
        json={"form_code": code, "scope": "tenant", "role_id": 0, "fields": []},
    )
    assert saved.json()["code"] == 0, saved.text
    result = _data(await client.post(_VALIDATE.format(code=code), json={"values": {"status": "any"}}), "校验")
    assert result["valid"] is True


async def test_local_validator_describe(tenant_db: str) -> None:
    """真实校验实现的元信息可读（能力契约 `describe`）。"""
    async with tenant_session(tenant_db) as tenant, tenant_session(tenant_db) as platform:
        validator = build_local_form_validator(
            tenant_uow=DbUnitOfWork(tenant),
            platform_uow=DbUnitOfWork(platform),
            option_set_registry=LocalOptionSetRegistry(),
        )
        assert "真实实现" in validator.describe()


def test_option_set_adapter_emits_optional_fields() -> None:
    """选项集适配器：`labelKey` / `color` / `disabled` 仅在有值时下发，`sort` 恒下发。"""
    registry = _FakeOptionRegistry()
    adapter = OptionSetAdapter(cast("BaseOptionSetRegistry", registry))
    items = adapter.resolve_items("fake")
    assert items[0] == ConcurrentStableDict({"value": "a", "label": "A", "sort": 1})
    assert items[1]["labelKey"] == "k.b"
    assert items[1]["color"] == "success"
    assert items[1]["disabled"] is True
    assert adapter.is_registered("fake") is True
    assert adapter.is_registered("absent") is False


def test_assemble_layout_tenant_and_platform_levels() -> None:
    """组装器按请求层级换回退顺序：租户层级跳过角色层，平台层级只看平台层。"""
    platform_layout = normalize_layout({"main": {"sections": [{"key": "p", "fields": ["a"]}]}})
    levels: ConcurrentStableDict[str, ConcurrentStableDict[int, LevelSnapshot]] = ConcurrentStableDict(
        {
            "platform": ConcurrentStableDict(
                {0: LevelSnapshot(scope="platform", role_id=0, layout=platform_layout, attrs=ConcurrentStableDict())}
            ),
            "tenant": ConcurrentStableDict(),
            "role": ConcurrentStableDict(),
        }
    )
    tenant_result = assemble_layout(
        levels=levels,
        level="tenant",
        role_hint=(None, None),
        platform_fields=ConcurrentStableList(),
        ext_fields=ConcurrentStableList(),
        hidden_keys=ConcurrentStableFrozenList(()),
        permissions=ConcurrentStableDict(),
        option_sets=ConcurrentStableFrozenList(()),
    )
    assert tenant_result.source == "platform"
    platform_result = assemble_layout(
        levels=levels,
        level="platform",
        role_hint=(None, None),
        platform_fields=ConcurrentStableList(),
        ext_fields=ConcurrentStableList(),
        hidden_keys=ConcurrentStableFrozenList(()),
        permissions=ConcurrentStableDict(),
        option_sets=ConcurrentStableFrozenList(()),
    )
    assert platform_result.source == "platform"
    assert platform_result.fallback is False


def test_assemble_layout_role_hint_without_candidate_uses_hint_layout() -> None:
    """角色布局由外部提示给出、层级归集里没有该角色行时，用提示布局并取空属性。"""
    role_layout = normalize_layout({"main": {"sections": [{"key": "r", "fields": ["a"]}]}})
    levels: ConcurrentStableDict[str, ConcurrentStableDict[int, LevelSnapshot]] = ConcurrentStableDict(
        {"platform": ConcurrentStableDict(), "tenant": ConcurrentStableDict(), "role": ConcurrentStableDict()}
    )
    result = assemble_layout(
        levels=levels,
        level="role",
        role_hint=(77, role_layout),
        platform_fields=ConcurrentStableList(),
        ext_fields=ConcurrentStableList(),
        hidden_keys=ConcurrentStableFrozenList(()),
        permissions=ConcurrentStableDict(),
        option_sets=ConcurrentStableFrozenList(()),
    )
    assert result.source == "role"
    assert result.layout.main.sections[0].key == "r"


async def test_option_collect_skips_non_object_attrs(
    client: AsyncClient, service_app: Any, ns: Namespace, tenant_db: str
) -> None:
    """属性行的 `attrs` 若不是 JSON 对象（历史脏数据）则跳过选项集收集，不影响下发。"""
    code = await _form(ns, "dirtyattr", app=service_app)
    await _save_layout(client, code, {"main": {"sections": [{"key": "s", "fields": ["status"]}]}})
    async with tenant_session(tenant_db) as session:
        await FieldAttrRepository(session).create(
            form_code=code, scope="tenant", role_id=0, field_key="status", attrs="[1,2]"
        )
        await session.commit()
    data = _data(await client.get(_EFFECTIVE.format(code=code)), "生效布局")
    assert data["option_sets"] == []


async def test_validate_numeric_field_with_text_rules(client: AsyncClient, service_app: Any, ns: Namespace) -> None:
    """数值字段挂文本类规则：长度 / 正则对非字符串值放行（由类型规则负责）。"""
    code = f"{ns.prefix}_numrules"
    business_id = await seed_business(code)
    await seed_form_with_fields(business_id, ConcurrentStableList((("amount", "金额", "number", 1),)))
    await _save_layout(client, code, {"main": {"sections": [{"key": "s", "fields": ["amount"]}]}})
    saved = await client.put(
        _ATTRS,
        json={
            "form_code": code,
            "scope": "tenant",
            "role_id": 0,
            "fields": [
                {
                    "field_key": "amount",
                    "field_type": "number",
                    "attrs": {"rules": [{"kind": "length", "min": 5}, {"kind": "pattern", "pattern": "^x$"}]},
                }
            ],
        },
    )
    assert saved.json()["code"] == 0, saved.text
    result = _data(await client.post(_VALIDATE.format(code=code), json={"values": {"amount": 5}}), "校验")
    assert result["valid"] is True


async def test_validate_platform_level_attrs(
    client: AsyncClient, service_app: Any, ns: Namespace, tenant_db: str
) -> None:
    """只有平台层属性（无任何布局）时按属性校验：属性索引第二轮回填（布局走空回退）。"""
    code = await _form(ns, "platattr", app=service_app)
    async with tenant_session(tenant_db) as session:
        await FieldAttrRepository(session).create(
            form_code=code, scope="platform", role_id=0, field_key="name", attrs='{"required":true}'
        )
        await session.commit()
    result = _data(await client.post(_VALIDATE.format(code=code), json={"values": {"name": ""}}), "校验")
    assert [item["rule"] for item in result["errors"]] == ["required"]
