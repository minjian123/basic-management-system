"""自建字段与动态 DDL 接口（Kiwi 2526）：登记 / 建列 / 冲突 / 停用不删列 / 重试 / 注入拒收。

重写口径（13_11）：
- 权限放行改配置面（`stub_permission_provider`），不写共享租户库；
- 运行期 DDL 开关直接改装配态 `settings.app.allow_runtime_ddl`（改环境变量在装配常驻后读不到）；
- 隔离靠命名空间 + 共享探针表（不建引擎、不清表）。
"""

from typing import Any

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.testing.namespace import Namespace
from tests_support.permission_stub import stub_permission_provider

from .helpers import (
    list_columns,
    register_form_key,
    seed_business,
    seed_form_with_fields,
    tenant_url,
)

pytestmark = [
    pytest.mark.kiwi_id(2526),
    pytest.mark.xdist_group("form-design"),
]

_FIELDS = "/api/v1/form-design/fields"

_PROBE = "biz_ext_probe"
"""共享库探针表（初始化阶段建好；结构变更只在初始化阶段发生）。"""

_TABLES: dict[str, str] = {}  # bare-collections:allow（测试内简单映射，仅断言用）


@pytest.fixture(autouse=True)
def prepared(tenant_db: str, service_app: FastAPI, monkeypatch: pytest.MonkeyPatch) -> None:
    """本套用例权限放行 + 清空表名映射（隔离靠命名空间，不清表）。

    保留 `tenant_db`：它既保证共享租户库就绪，也把连接串写进环境变量（`tenant_url()` 读它）。
    运行期 DDL 关闭（测试口径）：新建自建字段只落 `pending`，建列由初始化阶段完成。

    Args:
        tenant_db: 共享租户库连接串（夹具副作用：库就绪 + 环境变量）。
        service_app: 平台服务应用。
        monkeypatch: 补丁夹具。
    """
    assert tenant_db
    stub_permission_provider(service_app, monkeypatch)
    _TABLES.clear()


async def _form(ns: Namespace, suffix: str, *, app: object, table: str | None = None) -> str:
    """造业务码 + 表单 + 平台字段，并把业务码登记进表单标识清单可解析的表名。

    Args:
        ns: 用例命名空间。
        suffix: 后缀。
        app: 应用实例（登记表单标识 → 物理表名）。
        table: 目标物理表名（缺省用共享探针表）。

    Returns:
        str: 表单标识（业务码）。
    """
    code = f"{ns.prefix}_{suffix}"
    table_name = table or _PROBE
    business_id = await seed_business(code)
    await seed_form_with_fields(business_id, ConcurrentStableList((("name", "名称", "text", 1),)))
    register_form_key(app, code, table_name)
    _TABLES[code] = table_name
    return code


def _data(response: Any, label: str) -> Any:
    r"""取统一响应 \`data\`。"""
    body = response.json()
    data = body.get("data")
    assert data is not None, f"{label} 失败（HTTP {response.status_code}）：{response.text}"
    return data


async def _columns(table: str) -> ConcurrentStableList[str]:
    """读目标表现有列名（共享基座调用，用例不建引擎）。"""
    return await list_columns(tenant_url(), table)


async def test_create_field_keeps_pending(client: AsyncClient, service_app: Any, ns: Namespace) -> None:
    """新建自建字段 → 只落 pending（运行期不改结构），建列由初始化阶段完成。"""
    code = await _form(ns, "ddl", app=service_app)
    created = await client.post(
        _FIELDS,
        json={"form_code": code, "field_key": "project_no", "name": "项目编号", "type": "text", "sort": 5},
    )
    data = _data(created, "新建自建字段")
    assert data["ddl_status"] == "pending"
    assert data["column_name"] == "ext_project_no"


async def test_create_field_rejects_duplicate_key(client: AsyncClient, service_app: Any, ns: Namespace) -> None:
    """字段键重复 → 40402。"""
    code = await _form(ns, "dup", app=service_app)
    payload = {"form_code": code, "field_key": "dup_key", "name": "重复", "type": "text"}
    assert (await client.post(_FIELDS, json=payload)).json()["code"] == 0
    again = await client.post(_FIELDS, json=payload)
    assert again.json()["code"] == 40402


async def test_create_field_rejects_bad_type_and_option(client: AsyncClient, service_app: Any, ns: Namespace) -> None:
    """类型不在白名单 / 枚举缺选项集 / 选项集未注册 → 40404。"""
    code = await _form(ns, "type", app=service_app)
    bad_type = await client.post(
        _FIELDS, json={"form_code": code, "field_key": "rich", "name": "富文本", "type": "richtext"}
    )
    assert bad_type.json()["code"] == 40404
    missing_option = await client.post(
        _FIELDS, json={"form_code": code, "field_key": "opt1", "name": "枚举", "type": "option"}
    )
    assert missing_option.json()["code"] == 40404
    unknown_option = await client.post(
        _FIELDS,
        json={
            "form_code": code,
            "field_key": "opt2",
            "name": "枚举",
            "type": "option",
            "option_set_key": "bms.absent.set",
        },
    )
    assert unknown_option.json()["code"] == 40404


@pytest.mark.parametrize("bad_key", ["a;drop table x", "a'--", "1abc", "select", "a" * 70])
async def test_create_field_rejects_injection(
    client: AsyncClient, service_app: Any, ns: Namespace, bad_key: str
) -> None:
    """非法字段键（注入 / 大写 / 保留字 / 超长）在登记阶段即拒（10001）。"""
    code = await _form(ns, f"inj{abs(hash(bad_key)) % 1000}", app=service_app)
    rejected = await client.post(
        _FIELDS, json={"form_code": code, "field_key": bad_key, "name": "坏键", "type": "text"}
    )
    assert rejected.json()["code"] == 10001


async def test_disable_field_keeps_column(client: AsyncClient, service_app: Any, ns: Namespace) -> None:
    """停用字段：状态置 disabled；初始化阶段建好的列仍在（不生成 DROP COLUMN）。"""
    code = await _form(ns, "dis", app=service_app)
    created = await client.post(
        _FIELDS, json={"form_code": code, "field_key": "keep_col", "name": "保留列", "type": "text"}
    )
    field_id = _data(created, "新建")["id"]
    disabled = await client.put(f"{_FIELDS}/{field_id}", json={"status": "disabled"})
    assert disabled.json()["code"] == 0
    assert disabled.json()["data"]["status"] == "disabled"
    assert "ext_seeded" in await _columns(_PROBE)


async def test_retry_keeps_pending(client: AsyncClient, service_app: Any, ns: Namespace) -> None:
    """重试：运行期 DDL 关闭，重试后仍 pending（建列统一由初始化阶段执行）。"""
    code = await _form(ns, "retry", app=service_app)
    created = await client.post(
        _FIELDS, json={"form_code": code, "field_key": "retry_col", "name": "重试列", "type": "text"}
    )
    data = _data(created, "新建")
    assert data["ddl_status"] == "pending"
    retried = await client.post(f"{_FIELDS}/{data['id']}/retry")
    assert _data(retried, "重试")["ddl_status"] == "pending"


async def test_list_fields_includes_ddl_status(client: AsyncClient, service_app: Any, ns: Namespace) -> None:
    """列表下发各字段 ddl_status（前端按「待建列 / 已生效 / 建列失败」标记）。"""
    code = await _form(ns, "list", app=service_app)
    await client.post(_FIELDS, json={"form_code": code, "field_key": "z_col", "name": "甲", "type": "text", "sort": 2})
    listed = await client.get(_FIELDS, params={"form_code": code})
    data = _data(listed, "自建字段列表")
    assert [item["field_key"] for item in data["items"]] == ["z_col"]
    assert data["items"][0]["ddl_status"] == "pending"


async def test_create_field_unknown_form(client: AsyncClient, ns: Namespace) -> None:
    """业务码不存在 → 40401。"""
    response = await client.post(
        _FIELDS, json={"form_code": f"{ns.prefix}_absent", "field_key": "x_col", "name": "无", "type": "text"}
    )
    assert response.status_code == 404
    assert response.json()["code"] == 40401


async def test_runtime_ddl_disabled_keeps_pending(
    client: AsyncClient, service_app: Any, ns: Namespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """运行期 DDL 关闭（测试 / 生产口径）→ 只写元数据落 pending、不建物理列。

    结构只有「数据初始化」一次机会：请求路径不执行 `ALTER TABLE`，列由
    `ops.build_ext_columns` 统一补齐（该脚本行为见 `test_build_ext_columns.py`）。
    """
    monkeypatch.setattr(service_app.state.settings.app, "allow_runtime_ddl", False)
    code = await _form(ns, "pending", app=service_app)
    created = await client.post(
        _FIELDS,
        json={"form_code": code, "field_key": "pending_col", "name": "待建列", "type": "text"},
    )
    data = _data(created, "新建（待初始化建列）")
    assert data["ddl_status"] == "pending"
    assert data["column_name"] == "ext_pending_col"
    assert "ext_pending_col" not in await _columns(_TABLES[code])
