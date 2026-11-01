"""秒传登记接口测试（Kiwi 2374）：命中复用对象 / 未命中 / 对象丢失 / 配额不重复占用。

单库叠加（04-6-2）：秒传按「内容摘要 + 大小」命中，**上传内容必须按用例命名空间派生**——固定字节在
共享库里会命中前序用例留下的行（其对象可能已被别的用例删掉），表现为 `data` 为 None 而非本用例的命中。
"""

import hashlib
from pathlib import Path
from typing import Any

import pytest
from file_fixtures import PDF_BYTES, FilePorts
from httpx import AsyncClient

from bms_core.core.concurrent import ConcurrentStableDict
from bms_core.core.error_codes import ErrorCode
from bms_core.testing.namespace import Namespace
from bms_file.domains.file.limits import MAX_FILE_SIZE_KEY

pytestmark = pytest.mark.kiwi_id(2374)

API = "/api/v1/files"


def _payload(ns: Namespace) -> bytes:
    """本用例的上传内容（PDF 尾部追加注释行，使内容摘要与他人不同）。

    Args:
        ns: 用例命名空间。

    Returns:
        bytes: PDF 字节（尾部带命名空间标记）。
    """
    return PDF_BYTES + f"\n%{ns.prefix}\n".encode()


def _sha(payload: bytes) -> str:
    """内容摘要。

    Args:
        payload: 上传字节。

    Returns:
        str: 64 位十六进制摘要。
    """
    return hashlib.sha256(payload).hexdigest()


async def _upload(client: AsyncClient, payload: bytes) -> ConcurrentStableDict[str, Any]:
    """先落一个已完成文件（供秒传命中）。

    Args:
        client: 测试客户端。
        payload: 上传字节。

    Returns:
        ConcurrentStableDict[str, Any]: 上传结果 data。
    """
    resp = await client.post(API, files={"file": ("report.pdf", payload, "application/octet-stream")})
    assert resp.status_code == 200, resp.text
    return ConcurrentStableDict(resp.json()["data"])


async def test_dedup_hit_reuses_object_without_quota(
    client: AsyncClient, file_ports: FilePorts, tmp_path: Path, ns: Namespace
) -> None:
    """命中：建新元数据行、复用同一对象、不重复占配额、发上传事件。"""
    payload = _payload(ns)
    original = await _upload(client, payload)
    calls_before = len(file_ports.quota.calls)

    resp = await client.post(API + "/dedup", json={"name": "copy.pdf", "size": len(payload), "sha256": _sha(payload)})
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


async def test_dedup_object_missing_treated_as_miss(
    client: AsyncClient, file_ports: FilePorts, tmp_path: Path, ns: Namespace
) -> None:
    """候选元数据在但对象已丢：视为未命中（不建死引用）。"""
    payload = _payload(ns)
    await _upload(client, payload)
    for path in tmp_path.rglob("*"):
        if path.is_file():
            path.unlink()
    resp = await client.post(API + "/dedup", json={"name": "copy.pdf", "size": len(payload), "sha256": _sha(payload)})
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
