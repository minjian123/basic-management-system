"""布局与属性接口（Kiwi 2526）：三级读写 / 整份覆盖 / 恢复默认 / 结构校验 / 层级入参。"""

from typing import Any

import pytest
import pytest_asyncio
from httpx import AsyncClient

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.testing.namespace import Namespace
from tests_support.permission_admin import setup_min_tenant

from .helpers import (
    ensure_form_design_tables,
    outbox_types_in_tenant,
    seed_business,
    seed_form_with_fields,
)

pytestmark = pytest.mark.kiwi_id(2526)

_LAYOUTS = "/api/v1/form-design/layouts"
_ATTRS = "/api/v1/form-design/attrs"


@pytest_asyncio.fixture(autouse=True)
async def prepared(tenant_db: str) -> None:
    """真实权限校验所需租户库 + 内置系统管理员主体 + 表单定制四表存在性。

    单库叠加口径：**不清表**，隔离靠用例命名空间（`form_code = ns.prefix_suffix`）。

    Args:
        tenant_db: 共享测试租户库连接串。
    """
    await setup_min_tenant(tenant_db)
    await ensure_form_design_tables()


async def _form(ns: Namespace, suffix: str) -> str:
    """造业务码 + 表单 + 两个平台字段，返回业务码（表单标识）。

    Args:
        ns: 用例命名空间。
        suffix: 后缀。

    Returns:
        str: 表单标识（业务码）。
    """
    code = f"{ns.prefix}_{suffix}"
    business_id = await seed_business(code)
    await seed_form_with_fields(
        business_id,
        ConcurrentStableList(
            (
                ("name", "名称", "text", 1),
                ("status", "状态", "option", 2),
            )
        ),
    )
    return code


def _data(response: Any, label: str) -> Any:
    r"""取统一响应 \`data\`（失败时带完整响应体）。"""
    body = response.json()
    data = body.get("data")
    assert data is not None, f"{label} 失败（HTTP {response.status_code}）：{response.text}"
    return data


async def test_save_and_list_layout(client: AsyncClient, ns: Namespace) -> None:
    """保存租户层布局后可读回，配置元素（分区 / 列数 / 跨列 / 标签宽 / 查询区 / 明细列）完整。"""
    code = await _form(ns, "lay")
    saved = await client.put(
        _LAYOUTS,
        json={
            "form_code": code,
            "scope": "tenant",
            "role_id": 0,
            "layout_config": {
                "main": {
                    "labelPosition": "left",
                    "labelWidth": 120,
                    "sections": [
                        {
                            "key": "s1",
                            "title": "基本信息",
                            "columns": 2,
                            "fields": ["name", {"key": "status", "colSpan": True}],
                        },
                    ],
                },
                "query": {"fields": ["name"]},
                "detail": {"columns": [{"key": "name", "width": 200}]},
            },
        },
    )
    assert saved.json()["code"] == 0

    listed = await client.get(_LAYOUTS, params={"form_code": code})
    data = _data(listed, "布局列表")
    assert data["levels"] == ["tenant"]
    row = data["layouts"][0]
    config = row["layout_config"]
    assert config["main"]["labelPosition"] == "left"
    assert config["main"]["labelWidth"] == 120
    assert config["main"]["sections"][0]["columns"] == 2
    assert config["query"]["fields"] == ["name"]
    assert config["detail"]["columns"][0]["width"] == 200


async def test_save_layout_is_full_overwrite(client: AsyncClient, ns: Namespace) -> None:
    """整份覆盖：第二次保存不保留第一份的分区（覆盖式写入）。"""
    code = await _form(ns, "ow")
    first = {"main": {"sections": [{"key": "a", "columns": 1, "fields": ["name"]}]}}
    second = {"main": {"sections": [{"key": "b", "columns": 3, "fields": ["status"]}]}}
    for payload in (first, second):
        response = await client.put(
            _LAYOUTS, json={"form_code": code, "scope": "tenant", "role_id": 0, "layout_config": payload}
        )
        assert response.json()["code"] == 0
    data = _data(await client.get(_LAYOUTS, params={"form_code": code}), "布局列表")
    sections = data["layouts"][0]["layout_config"]["main"]["sections"]
    assert [section["key"] for section in sections] == ["b"]


async def test_delete_layout_restores_next_level(client: AsyncClient, ns: Namespace) -> None:
    """删除当前层级 → 回退下一级（删租户层后只剩角色层）。"""
    code = await _form(ns, "del")
    role_id = 7001
    for scope, rid in (("tenant", 0), ("role", role_id)):
        response = await client.put(
            _LAYOUTS,
            json={
                "form_code": code,
                "scope": scope,
                "role_id": rid,
                "layout_config": {"main": {"sections": [{"key": scope, "fields": ["name"]}]}},
            },
        )
        assert response.json()["code"] == 0
    data = _data(await client.get(_LAYOUTS, params={"form_code": code}), "布局列表")
    tenant_row = next(row for row in data["layouts"] if row["scope"] == "tenant")
    removed = await client.delete(f"{_LAYOUTS}/{tenant_row['id']}")
    assert removed.json()["code"] == 0
    assert removed.json()["data"]["applied"] is True
    after = _data(await client.get(_LAYOUTS, params={"form_code": code}), "布局列表")
    remaining = [row["scope"] for row in after["layouts"]]
    assert "tenant" not in remaining, f"租户层未删掉：{remaining}"
    assert "role" in remaining


async def test_platform_scope_requires_platform_admin(client: AsyncClient, ns: Namespace) -> None:
    """平台默认层级的写操作要求平台超管（测试主体为系统管理员 → 30001）。"""
    code = await _form(ns, "padm")
    denied = await client.put(
        _LAYOUTS,
        json={
            "form_code": code,
            "scope": "platform",
            "role_id": 0,
            "layout_config": {"main": {"sections": [{"key": "p", "fields": ["name"]}]}},
        },
    )
    assert denied.json()["code"] == 30001


async def test_layout_scope_validation(client: AsyncClient, ns: Namespace) -> None:
    """层级与角色 ID 组合非法 → 40403；未知层级同样拒绝。"""
    code = await _form(ns, "scope")
    bad = await client.put(
        _LAYOUTS, json={"form_code": code, "scope": "role", "role_id": 0, "layout_config": {"main": {"sections": []}}}
    )
    assert bad.json()["code"] == 40403
    bad_scope = await client.put(
        _LAYOUTS, json={"form_code": code, "scope": "ghost", "role_id": 0, "layout_config": {"main": {"sections": []}}}
    )
    assert bad_scope.json()["code"] == 40403


async def test_unknown_form_code_rejected(client: AsyncClient, ns: Namespace) -> None:
    """业务码不存在 → 40401（404）。"""
    response = await client.get(_LAYOUTS, params={"form_code": f"{ns.prefix}_absent"})
    assert response.status_code == 404
    assert response.json()["code"] == 40401


async def test_save_attrs_and_read_back(client: AsyncClient, ns: Namespace) -> None:
    """属性保存后可读回（必填 / 正则 / 提示）。"""
    code = await _form(ns, "attr")
    saved = await client.put(
        _ATTRS,
        json={
            "form_code": code,
            "scope": "tenant",
            "role_id": 0,
            "fields": [
                {
                    "field_key": "name",
                    "field_type": "text",
                    "attrs": {"required": True, "placeholder": "请输入", "rules": [{"kind": "length", "max": 8}]},
                }
            ],
        },
    )
    assert saved.json()["code"] == 0
    data = _data(await client.get(_LAYOUTS, params={"form_code": code}), "布局列表")
    assert len(data["attrs"]) == 1
    attrs = data["attrs"][0]["attrs"]
    assert attrs["required"] is True
    assert attrs["placeholder"] == "请输入"


async def test_save_attrs_rejects_invalid(client: AsyncClient, ns: Namespace) -> None:
    """非法属性 → 40408（非法正则 / 枚举缺选项集）。"""
    code = await _form(ns, "attrbad")
    bad_pattern = await client.put(
        _ATTRS,
        json={
            "form_code": code,
            "scope": "tenant",
            "role_id": 0,
            "fields": [
                {"field_key": "name", "field_type": "text", "attrs": {"rules": [{"kind": "pattern", "pattern": "("}]}}
            ],
        },
    )
    assert bad_pattern.json()["code"] == 40408
    missing_option = await client.put(
        _ATTRS,
        json={
            "form_code": code,
            "scope": "tenant",
            "role_id": 0,
            "fields": [{"field_key": "status", "field_type": "option", "attrs": {}}],
        },
    )
    assert missing_option.json()["code"] == 40408


async def test_delete_attrs_clears_level(client: AsyncClient, ns: Namespace) -> None:
    """删除层级属性 → 该层属性清空。"""
    code = await _form(ns, "attrdel")
    await client.put(
        _ATTRS,
        json={
            "form_code": code,
            "scope": "tenant",
            "role_id": 0,
            "fields": [{"field_key": "name", "field_type": "text", "attrs": {"required": True}}],
        },
    )
    data = _data(await client.get(_LAYOUTS, params={"form_code": code}), "布局列表")
    attr_id = data["attrs"][0]["id"]
    removed = await client.delete(f"{_ATTRS}/{attr_id}")
    assert removed.json()["code"] == 0
    after = _data(await client.get(_LAYOUTS, params={"form_code": code}), "布局列表")
    assert len(after["attrs"]) == 0


async def test_layout_save_publishes_event(client: AsyncClient, ns: Namespace) -> None:
    """保存布局在写事务内发 sys.form.updated（changed_type=layout）。"""
    code = await _form(ns, "evt")
    saved = await client.put(
        _LAYOUTS,
        json={
            "form_code": code,
            "scope": "tenant",
            "role_id": 0,
            "layout_config": {"main": {"sections": [{"key": "s", "fields": ["name"]}]}},
        },
    )
    assert saved.json()["code"] == 0
    types = await outbox_types_in_tenant(f"form:{code}")
    assert "sys.form.updated" in types


del ConcurrentStableDict
