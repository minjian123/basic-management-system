"""用户扩展信息端点测试（Kiwi 2238）：读列表 / 新增 / 更新 / 冲突 / 不存在 / 参数校验 / 保序。

服务端点为 `/api/v1/user-extensions`（具名插槽样例插件的后端契约面）：读＝按 `user_id` 列示、
写＝新增 / 更新一条；同用户同标签唯一（10003）、目标缺失（10002）、参数非法（10001）。
"""

from typing import cast

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import Table
from sqlalchemy.ext.asyncio import create_async_engine

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.config import get_settings
from bms_core.models.base import Base
from bms_platform.models.system import SysUserExtension

_TABLES: ConcurrentStableList[Table] = ConcurrentStableList([cast("Table", SysUserExtension.__table__)])

_API = "/api/v1/user-extensions"
_USER_ID = 1001


@pytest_asyncio.fixture(autouse=True)
async def tenant_schema(tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> None:
    """为临时租户库补建用户扩展信息表，并把服务租户库指向该临时文件。

    本端点按请求租户库读写，故用例为租户链补建表结构（平台链与种子由既有夹具提供）。

    Args:
        tmp_path_factory: 临时目录工厂。
        monkeypatch: 环境变量覆盖。
    """
    url = f"sqlite+aiosqlite:///{tmp_path_factory.mktemp('tenant') / 'tenant.db'}"
    monkeypatch.setenv("BMS_DATABASE__TENANTS__URL", url)
    get_settings.cache_clear()
    engine = create_async_engine(url)
    async with engine.begin() as connection:
        await connection.run_sync(lambda conn: Base.metadata.create_all(conn, tables=list(_TABLES)))
    await engine.dispose()


@pytest.mark.kiwi_id(2238)
async def test_user_extension_flow(client: AsyncClient) -> None:
    """读列表（空 → 有）→ 新增 → 更新 → 冲突 / 不存在 / 参数校验各分支。"""
    empty = await client.get(_API, params={"user_id": _USER_ID})
    assert empty.status_code == 200
    assert empty.json()["code"] == 0
    assert empty.json()["data"]["items"] == []

    created = await client.post(_API, json={"user_id": _USER_ID, "label": "vip", "remark": "重要客户"})
    assert created.json()["code"] == 0
    created_item = created.json()["data"]
    # 契约统一口径：整型字段（含雪花 ID）在 JSON 中以字符串输出，避免前端精度丢失
    assert created_item["user_id"] == str(_USER_ID)
    assert created_item["label"] == "vip"
    assert created_item["remark"] == "重要客户"
    assert created_item["created_at"] != ""
    extension_id = created_item["id"]

    listed = await client.get(_API, params={"user_id": _USER_ID})
    assert [item["label"] for item in listed.json()["data"]["items"]] == ["vip"]

    other_user = await client.get(_API, params={"user_id": _USER_ID + 1})
    assert other_user.json()["data"]["items"] == []

    conflict = await client.post(_API, json={"user_id": _USER_ID, "label": "vip"})
    assert conflict.json()["code"] == 10003

    updated = await client.put(f"{_API}/{extension_id}", json={"label": "svip", "remark": None})
    assert updated.json()["code"] == 0
    assert updated.json()["data"]["label"] == "svip"
    assert updated.json()["data"]["remark"] is None

    missing = await client.put(f"{_API}/999999999", json={"label": "x"})
    assert missing.status_code == 404
    assert missing.json()["code"] == 10002

    invalid = await client.get(_API, params={"user_id": 0})
    assert invalid.json()["code"] == 10001

    absent = await client.get(_API)
    assert absent.json()["code"] == 10001

    bad_body = await client.post(_API, json={"user_id": _USER_ID, "label": ""})
    assert bad_body.json()["code"] == 10001


@pytest.mark.kiwi_id(2238)
async def test_user_extension_update_label_conflict(client: AsyncClient) -> None:
    """更新标签撞上同用户既有行即拒绝；标签不变的保存不再做同键探测。"""
    first = await client.post(_API, json={"user_id": _USER_ID, "label": "vip"})
    second = await client.post(_API, json={"user_id": _USER_ID, "label": "inner"})
    first_id = first.json()["data"]["id"]
    second_id = second.json()["data"]["id"]

    clash = await client.put(f"{_API}/{second_id}", json={"label": "vip"})
    assert clash.json()["code"] == 10003

    kept = await client.put(f"{_API}/{second_id}", json={"label": "inner", "remark": "备注"})
    assert kept.json()["code"] == 0
    assert kept.json()["data"]["label"] == "inner"
    assert kept.json()["data"]["remark"] == "备注"

    ordered = await client.get(_API, params={"user_id": _USER_ID})
    assert [item["id"] for item in ordered.json()["data"]["items"]] == [first_id, second_id]
