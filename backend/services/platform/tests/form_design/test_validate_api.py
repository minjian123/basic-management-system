"""动态校验端到端（Kiwi 2526）：必填 / 长度 / 范围 / 正则 / 选项集 各一正一反。

渲染路径自测端点 `POST /forms/{form_code}/validate` 与业务接口共用同一 `BaseFormValidator`，
因此这里验证的规则口径与 `users` 试点一致。
"""

from typing import Any

import pytest
import pytest_asyncio
from httpx import AsyncClient

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.testing.namespace import Namespace
from tests_support.permission_admin import setup_min_tenant

from .helpers import register_form_key, reset_form_design_tables, seed_business, seed_form_with_fields

pytestmark = pytest.mark.kiwi_id(2526)

_LAYOUTS = "/api/v1/form-design/layouts"
_ATTRS = "/api/v1/form-design/attrs"
_VALIDATE = "/api/v1/forms/{code}/validate"


@pytest_asyncio.fixture(autouse=True)
async def prepared(tenant_db: str, service_app: Any) -> None:
    """租户库 + 系统管理员主体 + 清空表单定制四表。

    Args:
        tenant_db: 共享租户库连接串。
    """
    await setup_min_tenant(tenant_db)
    await reset_form_design_tables()


async def _form(ns: Namespace, suffix: str, *, app: object) -> str:
    """造业务码 + 表单 + 五个平台字段（文本 / 数字 / 枚举）。

    Args:
        ns: 用例命名空间。
        suffix: 后缀。
        app: 应用实例。

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
                ("amount", "金额", "number", 2),
                ("status", "状态", "option", 3),
                ("code", "编码", "text", 4),
                ("tags", "标签", "option_multi", 5),
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


async def _setup(  # bare-collections:allow（请求体 JSON 负载）
    code: str, client: AsyncClient, *, attrs: dict[str, Any]
) -> None:
    """保存租户层布局（引用全部字段）与指定属性。"""
    layout_ok = await client.put(
        _LAYOUTS,
        json={
            "form_code": code,
            "scope": "tenant",
            "role_id": 0,
            "layout_config": {
                "main": {"sections": [{"key": "s", "fields": ["name", "amount", "status", "code", "tags"]}]}
            },
        },
    )
    assert layout_ok.json()["code"] == 0
    saved = await client.put(
        _ATTRS,
        json={"form_code": code, "scope": "tenant", "role_id": 0, "fields": attrs["fields"]},
    )
    assert saved.json()["code"] == 0, saved.text


async def _validate(  # bare-collections:allow（请求体 JSON 负载）
    client: AsyncClient, code: str, values: dict[str, object]
) -> Any:
    """调用校验端点并返回 data。"""
    response = await client.post(_VALIDATE.format(code=code), json={"values": values})
    return _data(response, "校验")


async def test_required_rule(client: AsyncClient, service_app: Any, ns: Namespace) -> None:
    """必填：缺值被拒（required），补值通过。"""
    code = await _form(ns, "req", app=service_app)
    await _setup(
        code,
        client,
        attrs={"fields": [{"field_key": "name", "field_type": "text", "attrs": {"required": True}}]},
    )
    failed = await _validate(client, code, {"name": ""})
    assert failed["valid"] is False
    assert [item["rule"] for item in failed["errors"]] == ["required"]
    passed = await _validate(client, code, {"name": "张三"})
    assert passed["valid"] is True


async def test_length_rule(client: AsyncClient, service_app: Any, ns: Namespace) -> None:
    """长度：超出上限被拒（length），范围内通过。"""
    code = await _form(ns, "len", app=service_app)
    await _setup(
        code,
        client,
        attrs={
            "fields": [
                {
                    "field_key": "name",
                    "field_type": "text",
                    "attrs": {"rules": [{"kind": "length", "min": 2, "max": 4}]},
                }
            ]
        },
    )
    failed = await _validate(client, code, {"name": "abcdef"})
    assert [item["rule"] for item in failed["errors"]] == ["length"]
    assert (await _validate(client, code, {"name": "abc"}))["valid"] is True


async def test_range_rule(client: AsyncClient, service_app: Any, ns: Namespace) -> None:
    """范围：低于下限被拒（range），区间内通过。"""
    code = await _form(ns, "rng", app=service_app)
    await _setup(
        code,
        client,
        attrs={
            "fields": [
                {
                    "field_key": "amount",
                    "field_type": "number",
                    "attrs": {"rules": [{"kind": "range", "min": 1, "max": 10}]},
                }
            ]
        },
    )
    failed = await _validate(client, code, {"amount": 0.5})
    assert [item["rule"] for item in failed["errors"]] == ["range"]
    assert (await _validate(client, code, {"amount": 5}))["valid"] is True


async def test_pattern_rule(client: AsyncClient, service_app: Any, ns: Namespace) -> None:
    """正则：不匹配被拒（pattern），匹配通过。"""
    code = await _form(ns, "pat", app=service_app)
    await _setup(
        code,
        client,
        attrs={
            "fields": [
                {
                    "field_key": "code",
                    "field_type": "text",
                    "attrs": {"rules": [{"kind": "pattern", "pattern": "^[A-Z]{2}-\\d{3}$"}]},
                }
            ]
        },
    )
    failed = await _validate(client, code, {"code": "ab-1"})
    assert [item["rule"] for item in failed["errors"]] == ["pattern"]
    assert (await _validate(client, code, {"code": "AB-123"}))["valid"] is True


async def test_type_rule(client: AsyncClient, service_app: Any, ns: Namespace) -> None:
    """类型：数字字段传字符串被拒（type）。"""
    code = await _form(ns, "typ", app=service_app)
    await _setup(code, client, attrs={"fields": []})
    failed = await _validate(client, code, {"amount": "abc"})
    assert [item["rule"] for item in failed["errors"]] == ["type"]


async def test_multiple_errors_reported_per_field(client: AsyncClient, service_app: Any, ns: Namespace) -> None:
    """多字段同时失败 → 逐字段回报（field_key + rule）。"""
    code = await _form(ns, "multi", app=service_app)
    await _setup(
        code,
        client,
        attrs={
            "fields": [
                {"field_key": "name", "field_type": "text", "attrs": {"required": True}},
                {
                    "field_key": "amount",
                    "field_type": "number",
                    "attrs": {"rules": [{"kind": "range", "min": 1, "max": 10}]},
                },
            ]
        },
    )
    result = await _validate(client, code, {"name": "", "amount": 99})
    pairs = {(item["field_key"], item["rule"]) for item in result["errors"]}
    assert ("name", "required") in pairs
    assert ("amount", "range") in pairs


async def test_no_config_means_no_validation(client: AsyncClient, service_app: Any, ns: Namespace) -> None:
    """无布局 / 属性配置 → 不校验（与原接口行为一致，不破坏既有模块）。"""
    code = await _form(ns, "none", app=service_app)
    result = await _validate(client, code, {"name": "", "amount": "abc"})
    assert result["valid"] is True
    assert result["errors"] == []


async def test_unknown_form_passes_through(client: AsyncClient, ns: Namespace) -> None:
    """业务码不存在 → 校验器视为无配置（恒定通过，不因此报错）。"""
    result = await _validate(client, f"{ns.prefix}_absent", {"any": 1})
    assert result["valid"] is True
