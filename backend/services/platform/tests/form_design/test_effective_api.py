"""渲染路径 layout-effective（Kiwi 2526）：三级解析 / 空回退 / 权限优先 / 查询区与明细区。"""

from typing import Any

import pytest
import pytest_asyncio
from httpx import AsyncClient

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.testing.namespace import Namespace
from tests_support.permission_admin import setup_min_tenant

from .helpers import ensure_form_design_tables, register_form_key, seed_business, seed_form_with_fields

pytestmark = pytest.mark.kiwi_id(2526)

_LAYOUTS = "/api/v1/form-design/layouts"
_EFFECTIVE = "/api/v1/forms/{code}/layout-effective"


@pytest_asyncio.fixture(autouse=True)
async def prepared(tenant_db: str, service_app: Any) -> None:
    """租户库 + 系统管理员主体 + 四表存在性（不清表，隔离靠命名空间）。

    Args:
        tenant_db: 共享测试租户库连接串。
    """
    await setup_min_tenant(tenant_db)
    await ensure_form_design_tables()


async def _form(ns: Namespace, suffix: str, *, app: object) -> str:
    """造业务码 + 表单 + 三个平台字段（含一个枚举字段）。

    Args:
        ns: 用例命名空间。
        suffix: 后缀。
        app: 应用实例（登记物理表名）。

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
                ("note", "备注", "longtext", 3),
            )
        ),
    )
    register_form_key(app, code, f"biz_{code}")
    return code


def _data(response: Any, label: str) -> Any:
    r"""取统一响应 \`data\`。"""
    body = response.json()
    data = body.get("data")
    assert data is not None, f"{label} 失败（HTTP {response.status_code}）：{response.text}"
    return data


async def _save_layout(  # bare-collections:allow（请求体 JSON 负载，须内置容器）
    client: AsyncClient,
    code: str,
    scope: str,
    sections: list[dict[str, Any]],  # bare-collections:allow（请求体 JSON 负载，须内置容器）
    *,
    role_id: int = 0,
) -> None:
    """保存某层级布局（成功即断言 code=0）。"""
    response = await client.put(
        _LAYOUTS,
        json={
            "form_code": code,
            "scope": scope,
            "role_id": role_id,
            "layout_config": {"main": {"labelPosition": "top", "sections": sections}},
        },
    )
    assert response.json()["code"] == 0, response.text


async def test_empty_layout_falls_back_to_default_grid(client: AsyncClient, service_app: Any, ns: Namespace) -> None:
    """无任何配置 → 空布局回退默认栅格（source=empty、fallback=true，字段按 sort）。"""
    code = await _form(ns, "empty", app=service_app)
    data = _data(await client.get(_EFFECTIVE.format(code=code)), "layout-effective")
    assert data["source"] == "empty"
    assert data["fallback"] is True
    assert data["readonly"] is True
    refs = data["layout"]["main"]["sections"][0]["fields"]
    assert refs == ["name", "status", "note"]


async def test_tenant_layout_overrides_default(client: AsyncClient, service_app: Any, ns: Namespace) -> None:
    """租户层布局优先于平台默认（顺序与列数按租户配置）。"""
    code = await _form(ns, "tenant", app=service_app)
    await _save_layout(
        client,
        code,
        "tenant",
        [{"key": "s1", "title": "基本信息", "columns": 2, "fields": ["note", "name"]}],
    )
    data = _data(await client.get(_EFFECTIVE.format(code=code)), "layout-effective")
    assert data["source"] == "tenant"
    assert data["fallback"] is False
    section = data["layout"]["main"]["sections"][0]
    assert section["columns"] == 2
    assert section["fields"] == ["note", "name"]


async def test_query_and_detail_columns_are_delivered(client: AsyncClient, service_app: Any, ns: Namespace) -> None:
    """查询区字段序与明细列宽随生效布局下发。"""
    code = await _form(ns, "qd", app=service_app)
    response = await client.put(
        _LAYOUTS,
        json={
            "form_code": code,
            "scope": "tenant",
            "role_id": 0,
            "layout_config": {
                "main": {"sections": [{"key": "s", "fields": ["name"]}]},
                "query": {"fields": ["status", "name"]},
                "detail": {"columns": [{"key": "name", "width": 160}]},
            },
        },
    )
    assert response.json()["code"] == 0
    data = _data(await client.get(_EFFECTIVE.format(code=code)), "layout-effective")
    assert data["layout"]["query"]["fields"] == ["status", "name"]
    assert data["layout"]["detail"]["columns"] == [{"key": "name", "width": 160}]


async def test_required_attr_affects_served_fields(client: AsyncClient, service_app: Any, ns: Namespace) -> None:
    """字段属性（必填 / 提示）随生效布局下发。"""
    code = await _form(ns, "attr", app=service_app)
    await _save_layout(client, code, "tenant", [{"key": "s", "fields": ["name", "status"]}])
    saved = await client.put(
        "/api/v1/form-design/attrs",
        json={
            "form_code": code,
            "scope": "tenant",
            "role_id": 0,
            "fields": [{"field_key": "name", "field_type": "text", "attrs": {"required": True, "placeholder": "必填"}}],
        },
    )
    assert saved.json()["code"] == 0
    data = _data(await client.get(_EFFECTIVE.format(code=code)), "layout-effective")
    field = next(item for item in data["fields"] if item["key"] == "name")
    attrs = field["attrs"]
    assert attrs.get("required", False) is True
    assert attrs.get("placeholder") == "必填"


async def test_unknown_form_code_returns_40401(client: AsyncClient, ns: Namespace) -> None:
    """渲染路径业务码不存在 → 40401。"""
    response = await client.get(_EFFECTIVE.format(code=f"{ns.prefix}_absent"))
    assert response.status_code == 404
    assert response.json()["code"] == 40401
