"""文件接口失败分支测试（Kiwi 2374）：序号越界 / 声明类型冲突 / 会话失效 / 快照重建 / 落库失败回滚。

与成功路径用例分开：这里只断言**失败语义与回滚副作用**（对象是否清理、状态是否落失败、配额是否回滚）。
"""

import hashlib
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

import pytest
from fastapi import FastAPI
from file_fixtures import PDF_BYTES, FilePorts
from httpx import AsyncClient

from bms_core.api.deps import get_outbox_store
from bms_core.core.concurrent import ConcurrentStableDict
from bms_core.core.error_codes import ErrorCode
from bms_core.outbox.base import BaseOutboxStore
from bms_core.redis.base import shared_redis_client
from bms_file.domains.file.services import file as service_module

pytestmark = pytest.mark.kiwi_id(2374)

API = "/api/v1/files"
PART_SIZE = 10


def _pdf_bytes(size: int = 25) -> bytes:
    """构造指定长度的合法 PDF 内容（头部 magic + 填充）。"""
    head = b"%PDF-1.4\n"
    return head + b"x" * (size - len(head))


def _slice(data: bytes, part_no: int) -> bytes:
    """取第 part_no 片（从 1 起）。"""
    start = (part_no - 1) * PART_SIZE
    return data[start : start + PART_SIZE]


@pytest.fixture(autouse=True)
def _small_parts(monkeypatch: pytest.MonkeyPatch) -> None:
    """把分片大小调到 10 字节（便于多片用例；生产缺省 5MB）。"""
    from bms_core.core.config import get_settings

    monkeypatch.setattr(get_settings().file_options, "part_size", PART_SIZE)


class _FailingOutbox:
    """发件箱替身：写入即抛错（模拟事务内落库失败）。"""

    async def enqueue(self, session: Any, event: Any) -> str:
        """直接抛错。

        Raises:
            RuntimeError: 恒定抛出。
        """
        del session, event
        raise RuntimeError("outbox unavailable")


async def _initiate(client: AsyncClient, data: bytes, *, mime: str | None = None) -> ConcurrentStableDict[str, Any]:
    """初始化分片会话并返回响应 data。"""
    body: ConcurrentStableDict[str, object] = ConcurrentStableDict(
        {"name": "big.pdf", "size": len(data), "sha256": hashlib.sha256(data).hexdigest()}
    )
    if mime is not None:
        body.set("mime", mime)
    resp = await client.post(f"{API}/multipart", json=dict(body.items()))
    assert resp.status_code == 200, resp.text
    return ConcurrentStableDict(resp.json()["data"])


async def _put_part(client: AsyncClient, upload_id: str, part_no: int, chunk: bytes) -> None:
    """上传单片（带 SHA256 头）。"""
    resp = await client.put(
        f"{API}/multipart/{upload_id}/parts/{part_no}",
        files={"data": ("part.bin", chunk, "application/octet-stream")},
        headers={"X-Part-Sha256": hashlib.sha256(chunk).hexdigest()},
    )
    assert resp.status_code == 200, resp.text


async def test_put_part_rejects_out_of_range_index(client: AsyncClient, file_ports: FilePorts) -> None:
    """分片序号越界（大于总数）：`50104` / 409，不写对象。"""
    data = _pdf_bytes()
    upload_id = str((await _initiate(client, data))["upload_id"])

    resp = await client.put(
        f"{API}/multipart/{upload_id}/parts/9",
        files={"data": ("part.bin", b"x" * PART_SIZE, "application/octet-stream")},
        headers={"X-Part-Sha256": hashlib.sha256(b"x" * PART_SIZE).hexdigest()},
    )
    assert resp.status_code == 409
    assert resp.json()["code"] == ErrorCode.FILE_UPLOAD_SESSION_INVALID


async def test_initiate_rejects_declared_mime_conflict(client: AsyncClient, file_ports: FilePorts) -> None:
    """声明类型与扩展名不相容：`50101` / 400（白名单规范值才算数）。"""
    resp = await client.post(
        f"{API}/multipart",
        json={"name": "big.pdf", "size": 25, "sha256": "a" * 64, "mime": "text/plain"},
    )
    assert resp.status_code == 400
    assert resp.json()["code"] == ErrorCode.FILE_TYPE_NOT_ALLOWED


async def test_abort_unknown_session(client: AsyncClient, file_ports: FilePorts) -> None:
    """取消不存在的会话：`50104` / 409。"""
    resp = await client.delete(f"{API}/multipart/does-not-exist")
    assert resp.status_code == 409
    assert resp.json()["code"] == ErrorCode.FILE_UPLOAD_SESSION_INVALID


async def test_part_upload_rebuilds_lost_session_snapshot(client: AsyncClient, file_ports: FilePorts) -> None:
    """会话快照丢失（Redis 过期 / 重建）：按库内记录沿用原标识重建后继续上传成功。"""
    data = _pdf_bytes()
    upload_id = str((await _initiate(client, data))["upload_id"])
    await _put_part(client, upload_id, 1, _slice(data, 1))

    await cast("Any", shared_redis_client().async_client()).flushdb()
    await _put_part(client, upload_id, 2, _slice(data, 2))

    status = (await client.get(f"{API}/multipart/{upload_id}")).json()["data"]
    assert status["uploaded"] == [1, 2]


async def test_part_upload_rejects_expired_session(
    client: AsyncClient, file_ports: FilePorts, monkeypatch: pytest.MonkeyPatch
) -> None:
    """会话过期后再传片：`50104` / 409（过期即不可续，需重新初始化）。"""
    data = _pdf_bytes()
    upload_id = str((await _initiate(client, data))["upload_id"])

    def _future() -> datetime:
        return datetime.now(UTC).replace(tzinfo=None) + timedelta(days=30)

    monkeypatch.setattr(service_module, "_now", _future)
    resp = await client.put(
        f"{API}/multipart/{upload_id}/parts/1",
        files={"data": ("part.bin", _slice(data, 1), "application/octet-stream")},
        headers={"X-Part-Sha256": hashlib.sha256(_slice(data, 1)).hexdigest()},
    )
    assert resp.status_code == 409
    assert resp.json()["code"] == ErrorCode.FILE_UPLOAD_SESSION_INVALID


async def test_complete_rolls_back_on_quota_exceeded(
    client: AsyncClient, file_ports: FilePorts, tmp_path: Path
) -> None:
    """合并后配额超限：删已合并对象、置失败、`82005` / 409（不留半成品）。"""
    data = _pdf_bytes()
    upload_id = str((await _initiate(client, data))["upload_id"])
    for part_no in (1, 2, 3):
        await _put_part(client, upload_id, part_no, _slice(data, part_no))

    file_ports.use_quota(82005)
    resp = await client.post(f"{API}/multipart/{upload_id}/complete")
    assert resp.status_code == 409
    assert resp.json()["code"] == ErrorCode.TENANT_QUOTA_EXCEEDED

    assert not [path for path in tmp_path.rglob("*") if path.is_file()]
    status = (await client.get(f"{API}/multipart/{upload_id}")).json()["data"]
    assert status["status"] == "failed"


async def test_complete_rolls_back_when_event_write_fails(
    client: AsyncClient, file_ports: FilePorts, service_app: FastAPI, tmp_path: Path
) -> None:
    """合并落库阶段失败（事件写不进）：删对象、回滚配额、不落完成态。"""
    data = _pdf_bytes()
    upload_id = str((await _initiate(client, data))["upload_id"])
    for part_no in (1, 2, 3):
        await _put_part(client, upload_id, part_no, _slice(data, part_no))

    service_app.dependency_overrides[get_outbox_store] = lambda: cast("BaseOutboxStore", _FailingOutbox())
    with pytest.raises(RuntimeError, match="outbox unavailable"):
        await client.post(f"{API}/multipart/{upload_id}/complete")

    assert not [path for path in tmp_path.rglob("*") if path.is_file()]
    assert any(call.endswith("/quotas/release") for call in file_ports.quota.calls)


async def test_upload_rolls_back_when_event_write_fails(
    client: AsyncClient, file_ports: FilePorts, service_app: FastAPI, tmp_path: Path
) -> None:
    """整包上传落库阶段失败（事件写不进）：删对象、回滚配额、不落元数据。"""
    service_app.dependency_overrides[get_outbox_store] = lambda: cast("BaseOutboxStore", _FailingOutbox())

    with pytest.raises(RuntimeError, match="outbox unavailable"):
        await client.post(API, files={"file": ("rollback.pdf", PDF_BYTES, "application/pdf")})

    assert not [path for path in tmp_path.rglob("*") if path.is_file()]
    assert any(call.endswith("/quotas/release") for call in file_ports.quota.calls)
    listed = (await client.get(API, params={"name": "rollback.pdf"})).json()["data"]
    assert listed["total"] == 0
