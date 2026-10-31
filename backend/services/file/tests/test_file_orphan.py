"""孤儿回收接口测试（Kiwi 2374）：扫描超期上传 / 置 orphan / 清分片 / 幂等。

内部端点只接受服务身份（`require_service`），用例以校验器替身提供该身份。
"""

import hashlib
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from file_fixtures import FilePorts
from httpx import AsyncClient

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableFrozenList
from bms_core.oauth.verify import BaseTokenVerifier, VerifiedToken, get_token_verifier

pytestmark = pytest.mark.kiwi_id(2374)

API = "/api/v1/files"
INTERNAL = "/api/v1/files/internal/cleanup-orphans"


class _ServiceVerifier(BaseTokenVerifier):
    """服务身份替身：任何令牌都视为 `platform` 服务（仅用于内部端点用例）。"""

    async def verify(self, token: str, *, audience: str) -> VerifiedToken:
        """返回服务身份声明。

        Args:
            token: 令牌（忽略）。
            audience: 期望受众（忽略）。

        Returns:
            VerifiedToken: 服务身份。
        """
        del token, audience
        return VerifiedToken(
            subject="platform",
            token_type="service",
            audience=ConcurrentStableFrozenList(("service",)),
            service="platform",
        )


async def _cleanup(client: AsyncClient, app: FastAPI, **params: Any) -> ConcurrentStableDict[str, Any]:
    """以服务身份调用内部清理端点（仅本次请求替换校验器，随后恢复用户登录态）。"""
    app.dependency_overrides[get_token_verifier] = lambda: _ServiceVerifier()
    try:
        resp = await client.post(INTERNAL, params=params)
        assert resp.status_code == 200, resp.text
        return ConcurrentStableDict(resp.json()["data"])
    finally:
        app.dependency_overrides.pop(get_token_verifier, None)


async def _initiate(client: AsyncClient, size: int = 25) -> ConcurrentStableDict[str, Any]:
    """发起一个分片上传（留下 `uploading` 记录）。"""
    data = b"%PDF-1.4\n" + b"x" * (size - 9)
    resp = await client.post(
        f"{API}/multipart",
        json={"name": "orphan.pdf", "size": size, "sha256": hashlib.sha256(data).hexdigest()},
    )
    assert resp.status_code == 200, resp.text
    return ConcurrentStableDict(resp.json()["data"])


async def test_cleanup_marks_expired_uploads_as_orphan(
    client: AsyncClient, file_ports: FilePorts, service_app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    """超期上传：清理分片、置 `orphan`、发弃传事件；重复调用不再计入。"""
    from bms_file.domains.file.services import file as service_module

    session = await _initiate(client)
    future = datetime(2099, 1, 1)
    monkeypatch.setattr(service_module, "_now", lambda: future)

    data = await _cleanup(client, service_app)
    assert data["scanned"] >= 1
    assert data["orphaned"] >= 1
    assert data["failed"] == 0

    status = (await client.get(f"{API}/multipart/{session['upload_id']}")).json()["data"]
    assert status["status"] == "orphan"
    assert "file.upload.abandoned" in list(file_ports.outbox.events)

    again = await _cleanup(client, service_app)
    assert again["orphaned"] == 0


async def test_cleanup_requires_service_identity(client: AsyncClient, file_ports: FilePorts) -> None:
    """不带服务身份调用内部端点：拒绝（401/403）。"""
    resp = await client.post(INTERNAL)
    assert resp.status_code in (401, 403)


async def test_cleanup_removes_part_objects(
    client: AsyncClient, file_ports: FilePorts, service_app: FastAPI, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """超期上传的分片对象被物理清理。"""
    from bms_core.core.config import get_settings
    from bms_file.domains.file.services import file as service_module

    monkeypatch.setattr(get_settings().file_options, "part_size", 10)
    session = await _initiate(client, size=25)
    upload_id = str(session["upload_id"])
    chunk = b"%PDF-1.4\n" + b"x" * 1
    assert (
        await client.put(
            f"{API}/multipart/{upload_id}/parts/1",
            files={"data": ("part.bin", chunk, "application/octet-stream")},
            headers={"X-Part-Sha256": hashlib.sha256(chunk).hexdigest()},
        )
    ).status_code == 200
    assert [path for path in tmp_path.rglob("*") if ".part." in path.name]

    monkeypatch.setattr(service_module, "_now", lambda: datetime(2099, 1, 1))
    await _cleanup(client, service_app)

    assert not [path for path in tmp_path.rglob("*") if ".part." in path.name]


async def test_cleanup_tolerates_lost_session(
    client: AsyncClient, file_ports: FilePorts, service_app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    """会话快照已丢失（Redis 淘汰）：仍置 `orphan`，不因缺快照失败。"""
    from bms_core.core.exceptions import NotFoundError
    from bms_file.domains.file.services import file as service_module

    session = await _initiate(client)

    async def _raise(upload_id: str) -> None:
        del upload_id
        raise NotFoundError("session gone")

    monkeypatch.setattr(file_ports.multipart, "abort", _raise)
    monkeypatch.setattr(service_module, "_now", lambda: datetime(2099, 1, 1))

    data = await _cleanup(client, service_app)
    assert data["orphaned"] >= 1
    status = (await client.get(f"{API}/multipart/{session['upload_id']}")).json()["data"]
    assert status["status"] == "orphan"


async def test_cleanup_counts_single_failure(
    client: AsyncClient, file_ports: FilePorts, service_app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    """单条清理抛错只计失败数，不影响整批返回。"""
    from bms_file.domains.file.services import file as service_module

    await _initiate(client)

    async def _boom(row: object) -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr(service_module.FileService, "_mark_orphan", _boom)

    def _later() -> datetime:
        return datetime(2099, 1, 1) + timedelta(days=1)

    monkeypatch.setattr(service_module, "_now", _later)

    data = await _cleanup(client, service_app, limit=1000)
    assert data["failed"] >= 1
