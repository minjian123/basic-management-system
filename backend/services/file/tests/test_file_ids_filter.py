"""批量回显 `ids` 筛选测试（Kiwi 2524）：`GET /api/v1/files?ids=` 的主键过滤与非法入参。

覆盖：
- 只返回指定主键（与名称筛选叠加）；
- 重复主键去重（同一主键只查一次）；
- 未传 / 空串不筛选；
- 非法形态（非整数 / 非正数 / 空段 / 小数 / 超上限）统一 `10001`。
"""

from typing import Any

import pytest
from file_fixtures import PDF_BYTES, TEXT_BYTES, FilePorts
from httpx import AsyncClient

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.error_codes import ErrorCode

pytestmark = pytest.mark.kiwi_id(2524)

API = "/api/v1/files"
MAX_IDS = 200


async def _upload(client: AsyncClient, name: str, data: bytes) -> ConcurrentStableDict[str, Any]:
    """整包上传并返回响应 data。"""
    resp = await client.post(API, files={"file": (name, data, "application/octet-stream")})
    assert resp.status_code == 200, resp.text
    return ConcurrentStableDict(resp.json()["data"])


async def test_ids_filter_returns_only_requested_rows(client: AsyncClient, file_ports: FilePorts) -> None:
    """`ids` 只返回指定主键；与名称筛选叠加；重复主键不做重复查询。"""
    first = await _upload(client, "ids-a.pdf", PDF_BYTES)
    second = await _upload(client, "ids-b.txt", TEXT_BYTES)
    await _upload(client, "ids-c.txt", TEXT_BYTES)

    wanted = ConcurrentStableList([str(first["file_id"]), str(second["file_id"])])
    page = (await client.get(API, params={"ids": ",".join(wanted), "size": 10})).json()["data"]
    assert page["total"] == 2
    assert {str(item["id"]) for item in page["list"]} == set(wanted)

    duplicated = (await client.get(API, params={"ids": f"{wanted[0]},{wanted[0]},{wanted[1]}"})).json()["data"]
    assert duplicated["total"] == 2

    narrowed = (await client.get(API, params={"ids": ",".join(wanted), "name": "ids-a"})).json()["data"]
    assert narrowed["total"] == 1
    assert str(narrowed["list"][0]["id"]) == wanted[0]


async def test_ids_blank_means_no_filter(client: AsyncClient, file_ports: FilePorts) -> None:
    """未传 / 空串 / 纯空格视为不筛选（走原列表口径；按名称隔离，避开共享库并行 / 历史用例）。"""
    row = await _upload(client, "ids-blank.txt", TEXT_BYTES)
    baseline = (await client.get(API, params={"name": "ids-blank", "size": 10})).json()["data"]
    assert str(row["file_id"]) in {str(item["id"]) for item in baseline["list"]}

    for raw in ("", "   "):
        page = (await client.get(API, params={"name": "ids-blank", "ids": raw, "size": 10})).json()["data"]
        assert page["total"] == baseline["total"]


@pytest.mark.parametrize("raw", ["abc", "0", "-1", "1,,2", "1,", ",1", "1.5"])
async def test_ids_rejects_invalid_form(client: AsyncClient, file_ports: FilePorts, raw: str) -> None:
    """非法形态（非整数 / 非正数 / 空段 / 小数）统一 `10001`。"""
    resp = await client.get(API, params={"ids": raw})
    assert resp.status_code == 200
    assert resp.json()["code"] == ErrorCode.PARAM


async def test_ids_rejects_over_limit(client: AsyncClient, file_ports: FilePorts) -> None:
    """超过 200 个主键即拒绝（防超量查询）。"""
    raw = ",".join(str(index) for index in range(1, MAX_IDS + 2))
    resp = await client.get(API, params={"ids": raw})
    assert resp.status_code == 200
    assert resp.json()["code"] == ErrorCode.PARAM
