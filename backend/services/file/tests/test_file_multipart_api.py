"""分片上传接口测试（Kiwi 2374）：初始化 / 分片 / 断点续传 / 合并 / 取消 / 幂等。"""

import hashlib
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from file_fixtures import PDF_BYTES, FilePorts
from httpx import AsyncClient

from bms_core.api.deps import get_idempotency_store
from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.config import get_settings
from bms_core.core.error_codes import ErrorCode
from bms_core.idempotency.base import IDEMPOTENCY_PAYLOAD_TYPE, IdempotencyStore

pytestmark = pytest.mark.kiwi_id(2374)

API = "/api/v1/files"
PART_SIZE = 10


def _pdf_bytes(size: int = 25) -> bytes:
    """构造指定长度的合法 PDF 内容（头部 magic + 填充）。"""
    head = b"%PDF-1.4\n"
    return head + b"x" * (size - len(head))


@pytest.fixture(autouse=True)
def _small_parts(monkeypatch: pytest.MonkeyPatch) -> None:
    """把分片大小调到 10 字节（便于多片用例；生产缺省 5MB）。"""
    monkeypatch.setattr(get_settings().file_options, "part_size", PART_SIZE)


async def _initiate(client: AsyncClient, data: bytes) -> ConcurrentStableDict[str, Any]:
    """初始化分片会话并返回响应 data。"""
    resp = await client.post(
        f"{API}/multipart",
        json={"name": "big.pdf", "size": len(data), "sha256": hashlib.sha256(data).hexdigest()},
    )
    assert resp.status_code == 200, resp.text
    return ConcurrentStableDict(resp.json()["data"])


def _slice(data: bytes, part_no: int) -> bytes:
    """取第 part_no 片（从 1 起）。"""
    start = (part_no - 1) * PART_SIZE
    return data[start : start + PART_SIZE]


async def _put_part(client: AsyncClient, upload_id: str, part_no: int, chunk: bytes) -> None:
    """上传单片（带 SHA256 头）。"""
    resp = await client.put(
        f"{API}/multipart/{upload_id}/parts/{part_no}",
        files={"data": ("part.bin", chunk, "application/octet-stream")},
        headers={"X-Part-Sha256": hashlib.sha256(chunk).hexdigest()},
    )
    assert resp.status_code == 200, resp.text


async def test_full_multipart_flow(client: AsyncClient, file_ports: FilePorts, tmp_path: Path) -> None:
    """完整流程：初始化 → 逐片 → 状态 → 合并；合并后对象为按序拼接、分片已清理。"""
    data = _pdf_bytes()
    session = await _initiate(client, data)
    assert session["total_parts"] == 3
    assert session["part_size"] == PART_SIZE
    upload_id = str(session["upload_id"])

    for part_no in (1, 2, 3):
        await _put_part(client, upload_id, part_no, _slice(data, part_no))

    status = (await client.get(f"{API}/multipart/{upload_id}")).json()["data"]
    assert status["uploaded"] == [1, 2, 3]
    assert status["missing"] == []
    assert status["uploaded_parts"] == 3

    done = (await client.post(f"{API}/multipart/{upload_id}/complete")).json()["data"]
    assert done["status"] == "completed"
    assert done["size"] == len(data)
    assert done["sha256"] == hashlib.sha256(data).hexdigest()
    assert list(file_ports.outbox.events) == ["file.uploaded"]
    final = [path for path in tmp_path.rglob("*") if path.is_file() and ".part." not in path.name]
    assert len(final) == 1
    assert final[0].read_bytes() == data
    assert not [path for path in tmp_path.rglob("*") if ".part." in path.name]


async def test_resume_only_missing_parts(client: AsyncClient, file_ports: FilePorts) -> None:
    """断点续传：只补缺失片即可合并（重传同片为覆盖写）。"""
    data = _pdf_bytes()
    upload_id = str((await _initiate(client, data))["upload_id"])
    await _put_part(client, upload_id, 1, _slice(data, 1))
    await _put_part(client, upload_id, 3, _slice(data, 3))

    status = (await client.get(f"{API}/multipart/{upload_id}")).json()["data"]
    assert status["missing"] == [2]

    await _put_part(client, upload_id, 2, _slice(data, 2))
    again = (await client.get(f"{API}/multipart/{upload_id}")).json()["data"]
    assert again["missing"] == []

    done = (await client.post(f"{API}/multipart/{upload_id}/complete")).json()["data"]
    assert done["status"] == "completed"


async def test_part_checksum_mismatch(client: AsyncClient, file_ports: FilePorts) -> None:
    """分片 SHA256 不符：拒绝（`50103` / 400）。"""
    data = _pdf_bytes()
    upload_id = str((await _initiate(client, data))["upload_id"])
    resp = await client.put(
        f"{API}/multipart/{upload_id}/parts/1",
        files={"data": ("part.bin", _slice(data, 1), "application/octet-stream")},
        headers={"X-Part-Sha256": "0" * 64},
    )
    assert resp.status_code == 400
    assert resp.json()["code"] == ErrorCode.FILE_CHECKSUM_MISMATCH


async def test_complete_rejects_missing_parts(client: AsyncClient, file_ports: FilePorts) -> None:
    """缺片即合并：拒绝并给出缺失序号（`50104` / 409）。"""
    data = _pdf_bytes()
    upload_id = str((await _initiate(client, data))["upload_id"])
    await _put_part(client, upload_id, 1, _slice(data, 1))

    resp = await client.post(f"{API}/multipart/{upload_id}/complete")
    assert resp.status_code == 409
    assert resp.json()["code"] == ErrorCode.FILE_UPLOAD_SESSION_INVALID
    assert "[2, 3]" in resp.json()["message"]


async def test_complete_is_idempotent(client: AsyncClient, file_ports: FilePorts) -> None:
    """重复合并：已完成时回既有结果（不重复占配额、不重复发事件）。"""
    data = _pdf_bytes()
    upload_id = str((await _initiate(client, data))["upload_id"])
    for part_no in (1, 2, 3):
        await _put_part(client, upload_id, part_no, _slice(data, part_no))
    first = (await client.post(f"{API}/multipart/{upload_id}/complete")).json()["data"]
    second = (await client.post(f"{API}/multipart/{upload_id}/complete")).json()["data"]
    assert first == second
    assert list(file_ports.outbox.events) == ["file.uploaded"]


async def test_abort_then_session_invalid(client: AsyncClient, file_ports: FilePorts, tmp_path: Path) -> None:
    """取消后会话失效：再合并 `50104`，分片文件已清理。"""
    data = _pdf_bytes()
    upload_id = str((await _initiate(client, data))["upload_id"])
    await _put_part(client, upload_id, 1, _slice(data, 1))

    assert (await client.delete(f"{API}/multipart/{upload_id}")).status_code == 200
    assert not [path for path in tmp_path.rglob("*") if ".part." in path.name]
    resp = await client.post(f"{API}/multipart/{upload_id}/complete")
    assert resp.status_code == 409
    assert resp.json()["code"] == ErrorCode.FILE_UPLOAD_SESSION_INVALID
    status = (await client.get(f"{API}/multipart/{upload_id}")).json()["data"]
    assert status["status"] == "failed"


async def test_initiate_rejects_unknown_type_and_oversize(client: AsyncClient, file_ports: FilePorts) -> None:
    """初始化预检：扩展名不在白名单 `50101`；超单文件上限 `50102`。"""
    bad = await client.post(f"{API}/multipart", json={"name": "evil.exe", "size": 10, "sha256": "a" * 64})
    assert bad.status_code == 400
    assert bad.json()["code"] == ErrorCode.FILE_TYPE_NOT_ALLOWED

    huge = await client.post(
        f"{API}/multipart", json={"name": "big.pdf", "size": 3 * 1024 * 1024 * 1024, "sha256": "a" * 64}
    )
    assert huge.status_code == 413
    assert huge.json()["code"] == ErrorCode.FILE_SIZE_EXCEEDED


async def test_status_unknown_session(client: AsyncClient, file_ports: FilePorts) -> None:
    """未知会话查状态：`50106` / 404。"""
    resp = await client.get(f"{API}/multipart/does-not-exist")
    assert resp.status_code == 404
    assert resp.json()["code"] == ErrorCode.FILE_NOT_FOUND


class _FakeIdempotencyStore(IdempotencyStore):
    """幂等替身：首次登记、重复请求回放首次载荷。"""

    def __init__(self) -> None:
        self._payloads: ConcurrentStableList[IDEMPOTENCY_PAYLOAD_TYPE] = ConcurrentStableList()

    async def begin(self, key: str, *, ttl: int = 0) -> bool:
        del key, ttl
        return not self._payloads

    async def load(self, key: str) -> IDEMPOTENCY_PAYLOAD_TYPE | None:
        del key
        return self._payloads[0] if self._payloads else None

    async def save(self, key: str, payload: IDEMPOTENCY_PAYLOAD_TYPE, *, ttl: int = 0) -> None:
        del key, ttl
        self._payloads.add(payload)


async def test_initiate_idempotency_reuses_first_session(
    client: AsyncClient, file_ports: FilePorts, service_app: FastAPI
) -> None:
    """初始化幂等键：重复初始化回放首次会话（不新建记录）。"""
    store = _FakeIdempotencyStore()
    service_app.dependency_overrides[get_idempotency_store] = lambda: store
    body = {"name": "big.pdf", "size": len(PDF_BYTES), "sha256": hashlib.sha256(PDF_BYTES).hexdigest()}
    first = await client.post(f"{API}/multipart", json=body, headers={"Idempotency-Key": "case-2374"})
    second = await client.post(f"{API}/multipart", json=body, headers={"Idempotency-Key": "case-2374"})
    assert first.json()["data"] == second.json()["data"]
