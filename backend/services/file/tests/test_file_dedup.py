"""秒传登记接口测试（Kiwi 2374）：命中复用对象 / 未命中 / 对象丢失 / 配额不重复占用。"""

import hashlib
from pathlib import Path
from typing import Any

import pytest
from file_fixtures import PDF_BYTES, FilePorts
from httpx import AsyncClient

from bms_core.core.concurrent import ConcurrentStableDict
from bms_core.core.error_codes import ErrorCode
from bms_file.domains.file.limits import MAX_FILE_SIZE_KEY

pytestmark = pytest.mark.kiwi_id(2374)

API = "/api/v1/files"
_SHA = hashlib.sha256(PDF_BYTES).hexdigest()


async def _upload(client: AsyncClient) -> ConcurrentStableDict[str, Any]:
    """先落一个已完成文件（供秒传命中）。"""
    resp = await client.post(API, files={"file": ("report.pdf", PDF_BYTES, "application/octet-stream")})
    assert resp.status_code == 200, resp.text
    return ConcurrentStableDict(resp.json()["data"])


async def test_dedup_hit_reuses_object_without_quota(
    client: AsyncClient, file_ports: FilePorts, tmp_path: Path
) -> None:
    """命中：建新元数据行、复用同一对象、不重复占配额、发上传事件。"""
    original = await _upload(client)
    calls_before = len(file_ports.quota.calls)

    resp = await client.post(API + "/dedup", json={"name": "copy.pdf", "size": len(PDF_BYTES), "sha256": _SHA})
    data = resp.json()["data"]
    assert data["dedup"] is True
    assert data["file_id"] != original["file_id"]
    assert len(file_ports.quota.calls) == calls_before
    assert list(file_ports.outbox.events) == ["file.uploaded", "file.uploaded"]
    objects = [path for path in tmp_path.rglob("*") if path.is_file()]
    assert len(objects) == 1


async def test_dedup_miss_returns_null(client: AsyncClient, file_ports: FilePorts) -> None:
    """未命中：data 为 null（调用方走正常上传）。"""
    resp = await client.post(API + "/dedup", json={"name": "unknown.pdf", "size": 4321, "sha256": "b" * 64})
    assert resp.status_code == 200
    assert resp.json()["data"] is None


async def test_dedup_object_missing_treated_as_miss(client: AsyncClient, file_ports: FilePorts, tmp_path: Path) -> None:
    """候选元数据在但对象已丢：视为未命中（不建死引用）。"""
    await _upload(client)
    for path in tmp_path.rglob("*"):
        if path.is_file():
            path.unlink()
    resp = await client.post(API + "/dedup", json={"name": "copy.pdf", "size": len(PDF_BYTES), "sha256": _SHA})
    assert resp.json()["data"] is None


async def test_dedup_rejects_type_and_size(client: AsyncClient, file_ports: FilePorts) -> None:
    """秒传不是绕过白名单的后门：非法扩展名 `50101`，超限 `50102`。"""
    bad_type = await client.post(API + "/dedup", json={"name": "evil.exe", "size": 10, "sha256": "c" * 64})
    assert bad_type.status_code == 400
    assert bad_type.json()["code"] == ErrorCode.FILE_TYPE_NOT_ALLOWED

    file_ports.use_config(ConcurrentStableDict({MAX_FILE_SIZE_KEY: "10"}))
    too_big = await client.post(API + "/dedup", json={"name": "big.pdf", "size": 100, "sha256": "c" * 64})
    assert too_big.status_code == 413
    assert too_big.json()["code"] == ErrorCode.FILE_SIZE_EXCEEDED


async def test_dedup_rejects_bad_sha256(client: AsyncClient, file_ports: FilePorts) -> None:
    """SHA256 形态非法：`10001` / 400。"""
    resp = await client.post(API + "/dedup", json={"name": "a.pdf", "size": 10, "sha256": "z" * 64})
    assert resp.json()["code"] == ErrorCode.PARAM
