"""下载 / 预览 / 列表 / 删除接口测试（Kiwi 2374）：预签名、类型复核、软删与事件。"""

import hashlib
from pathlib import Path
from typing import Any

import pytest
from file_fixtures import PDF_BYTES, TEXT_BYTES, FilePorts
from httpx import AsyncClient

from bms_core.core.concurrent import ConcurrentStableDict
from bms_core.core.error_codes import ErrorCode

pytestmark = pytest.mark.kiwi_id(2374)

API = "/api/v1/files"


async def _upload(client: AsyncClient, name: str, data: bytes) -> ConcurrentStableDict[str, Any]:
    """整包上传并返回响应 data。"""
    resp = await client.post(API, files={"file": (name, data, "application/octet-stream")})
    assert resp.status_code == 200, resp.text
    return ConcurrentStableDict(resp.json()["data"])


async def test_download_url_returns_presigned(client: AsyncClient, file_ports: FilePorts) -> None:
    """下载取址：返回限时地址（本地实现为 `file://`），默认有效期取参数。"""
    row = await _upload(client, "report.pdf", PDF_BYTES)
    resp = await client.get(f"{API}/{row['file_id']}/download-url")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["url"].startswith("file://")
    assert data["expires_in"] == 3600
    assert data["method"] == "GET"


async def test_download_url_truncates_custom_ttl(client: AsyncClient, file_ports: FilePorts) -> None:
    """自定义有效期不得超过参数上限（此处参数为 100s，请求 1000s 被截断）。"""
    from bms_core.core.concurrent import ConcurrentStableDict
    from bms_file.domains.file.limits import PRESIGN_TTL_KEY

    file_ports.use_config(ConcurrentStableDict({PRESIGN_TTL_KEY: "100"}))
    row = await _upload(client, "report.pdf", PDF_BYTES)
    data = (await client.get(f"{API}/{row['file_id']}/download-url", params={"expires_in": 1000})).json()["data"]
    assert data["expires_in"] == 100


async def test_preview_url_allows_pdf_and_rejects_others(client: AsyncClient, file_ports: FilePorts) -> None:
    """预览取址：PDF 直开；文本类型 `50108` / 400。"""
    pdf = await _upload(client, "report.pdf", PDF_BYTES)
    ok = await client.get(f"{API}/{pdf['file_id']}/preview-url")
    assert ok.status_code == 200

    txt = await _upload(client, "note.txt", TEXT_BYTES)
    bad = await client.get(f"{API}/{txt['file_id']}/preview-url")
    assert bad.status_code == 400
    assert bad.json()["code"] == ErrorCode.FILE_PREVIEW_UNSUPPORTED


async def test_presign_rejects_missing_and_unfinished(client: AsyncClient, file_ports: FilePorts) -> None:
    """取址复核：未知文件 `50106`；未完成上传 `50104`。"""
    missing = await client.get(f"{API}/987654321/download-url")
    assert missing.status_code == 404
    assert missing.json()["code"] == ErrorCode.FILE_NOT_FOUND

    data = b"%PDF-1.4 pending"
    init = await client.post(
        f"{API}/multipart",
        json={"name": "pending.pdf", "size": len(data), "sha256": hashlib.sha256(data).hexdigest()},
    )
    file_id = init.json()["data"]["file_id"]
    unfinished = await client.get(f"{API}/{file_id}/download-url")
    assert unfinished.status_code == 409
    assert unfinished.json()["code"] == ErrorCode.FILE_UPLOAD_SESSION_INVALID


async def test_presign_rejects_missing_object(client: AsyncClient, file_ports: FilePorts, tmp_path: Path) -> None:
    """对象被外部清理：`50109` / 404（元数据仍在）。"""
    row = await _upload(client, "report.pdf", PDF_BYTES)
    for path in tmp_path.rglob("*"):
        if path.is_file():
            path.unlink()
    resp = await client.get(f"{API}/{row['file_id']}/download-url")
    assert resp.status_code == 404
    assert resp.json()["code"] == ErrorCode.FILE_OBJECT_MISSING


async def test_list_filters_and_pagination(client: AsyncClient, file_ports: FilePorts) -> None:
    """列表：按名称 / 类型筛选，返回分页结构。"""
    await _upload(client, "report.pdf", PDF_BYTES)
    await _upload(client, "note.txt", TEXT_BYTES)

    page = (await client.get(API, params={"size": 10})).json()["data"]
    assert page["total"] >= 2
    assert page["page"] == 1 and page["size"] == 10

    pdf_only = (await client.get(API, params={"mime_type": "application/pdf"})).json()["data"]
    assert all(item["mime_type"] == "application/pdf" for item in pdf_only["list"])

    named = (await client.get(API, params={"name": "note"})).json()["data"]
    assert named["list"] and all(item["name"] == "note.txt" for item in named["list"])


async def test_delete_soft_deletes_and_emits(client: AsyncClient, file_ports: FilePorts, tmp_path: Path) -> None:
    """删除：软删元数据、对象保留、发 `file.deleted`；再取址 `50106`。"""
    row = await _upload(client, "report.pdf", PDF_BYTES)
    assert (await client.delete(f"{API}/{row['file_id']}")).status_code == 200
    assert list(file_ports.outbox.events) == ["file.uploaded", "file.deleted"]
    assert any(path.is_file() for path in tmp_path.rglob("*"))

    after = await client.get(f"{API}/{row['file_id']}/download-url")
    assert after.status_code == 404
    assert after.json()["code"] == ErrorCode.FILE_NOT_FOUND

    again = await client.delete(f"{API}/{row['file_id']}")
    assert again.status_code == 404


async def test_endpoints_require_authentication(client: AsyncClient, file_ports: FilePorts) -> None:
    """未带登录态访问受保护端点：401（模块级 `require_auth`）。"""
    resp = await client.get(API, headers={"Authorization": ""})
    assert resp.status_code == 401
