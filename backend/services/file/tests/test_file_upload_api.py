"""整包上传接口测试（Kiwi 2374）：成功 / 类型 / 大小 / 配额 / 事件。"""

from pathlib import Path

import pytest
from fastapi import FastAPI
from file_fixtures import PDF_BYTES, TEXT_BYTES, FilePorts, pdf_part_sha
from httpx import AsyncClient

from bms_core.core.concurrent import ConcurrentStableDict
from bms_core.core.error_codes import ErrorCode
from bms_file.domains.file.limits import MAX_UPLOAD_SIZE_KEY, WHITELIST_KEY
from bms_file.domains.file.rules import DEFAULT_WHITELIST

pytestmark = pytest.mark.kiwi_id(2374)

API = "/api/v1/files"


async def test_upload_completes_and_emits_event(
    client: AsyncClient, file_ports: FilePorts, tmp_path: Path, service_app: FastAPI
) -> None:
    """整包上传成功：落对象、写元数据、占配额一次、发 `file.uploaded`。"""
    ports = file_ports
    resp = await client.post(
        API, files={"file": ("report.pdf", PDF_BYTES, "application/octet-stream")}, params={"name": "report.pdf"}
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["status"] == "completed"
    assert data["mime_type"] == "application/pdf"
    assert data["size"] == len(PDF_BYTES)
    assert data["sha256"] == pdf_part_sha(PDF_BYTES)
    assert ports.quota.calls and ports.quota.calls[0].endswith("/quotas/consume")
    assert list(ports.outbox.events) == ["file.uploaded"]
    objects: ConcurrentStableDict[str, Path] = ConcurrentStableDict(
        {path.name: path for path in tmp_path.rglob("*") if path.is_file()}
    )
    assert str(data["file_id"]) in objects


async def test_upload_rejects_renamed_binary(client: AsyncClient, file_ports: FilePorts) -> None:
    """改扩展名绕过：内容不是 PDF 时拒绝（`50101` / 400）。"""
    resp = await client.post(API, files={"file": ("evil.pdf", b"MZ\x90\x00binary", "application/pdf")})
    assert resp.status_code == 400
    assert resp.json()["code"] == ErrorCode.FILE_TYPE_NOT_ALLOWED


async def test_upload_rejects_empty(client: AsyncClient, file_ports: FilePorts) -> None:
    """空文件拒绝（`50102` / 413）。"""
    resp = await client.post(API, files={"file": ("empty.pdf", b"", "application/pdf")})
    assert resp.status_code == 413
    assert resp.json()["code"] == ErrorCode.FILE_SIZE_EXCEEDED


async def test_upload_rejects_oversized(client: AsyncClient, file_ports: FilePorts) -> None:
    """超整包上限（参数可调）：提示走分片（`50102`）。"""
    file_ports.use_config(ConcurrentStableDict({MAX_UPLOAD_SIZE_KEY: "10", WHITELIST_KEY: DEFAULT_WHITELIST}))
    resp = await client.post(API, files={"file": ("report.pdf", PDF_BYTES, "application/pdf")})
    assert resp.status_code == 413
    assert resp.json()["code"] == ErrorCode.FILE_SIZE_EXCEEDED


async def test_upload_rejects_on_quota_exceeded(client: AsyncClient, file_ports: FilePorts, tmp_path: Path) -> None:
    """配额超限：删已写对象并返回 `82005` / 409。"""
    file_ports.use_quota(82005)
    resp = await client.post(API, files={"file": ("report.pdf", PDF_BYTES, "application/pdf")})
    assert resp.status_code == 409
    assert resp.json()["code"] == ErrorCode.TENANT_QUOTA_EXCEEDED
    assert not any(path.is_file() for path in tmp_path.rglob("*"))


async def test_upload_fails_open_when_quota_unavailable(client: AsyncClient, file_ports: FilePorts) -> None:
    """配额服务不可用：fail-open 放行（不阻断上传）。"""
    file_ports.use_quota(10007)
    resp = await client.post(API, files={"file": ("note.txt", TEXT_BYTES, "text/plain")})
    assert resp.status_code == 200
    assert resp.json()["data"]["mime_type"] == "text/plain"
