"""文件上传存储配额接线测试（任务 `04_01`；Kiwi 2325）。

覆盖：合并完成占存储配额（成功）、超限 82005 时清理已合并对象、配额服务不可用时 fail-open。
"""

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from bms_core.api.deps import get_multipart_upload, get_object_storage, get_service_client
from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.serialization import stable_json_dumps
from bms_core.servicecall.base import BaseServiceClient, ServiceRequest, ServiceResponse
from bms_core.storage.base import (
    DEFAULT_PRESIGN_TTL,
    BaseMultipartUpload,
    BaseObjectStorage,
    ExistingObjectRef,
    MultipartInit,
    MultipartPart,
    MultipartSession,
    PresignedUrl,
    StoredObject,
)

pytestmark = pytest.mark.kiwi_id(2325)

API = "/api/v1/files/uploads/u1/complete"


class _StubStore(BaseMultipartUpload):
    async def complete(self, upload_id: str) -> StoredObject:
        del upload_id
        return StoredObject(key="k1", size=123, content_type="text/plain", etag="e1")

    async def initiate(self, init: MultipartInit) -> MultipartSession:
        raise NotImplementedError

    async def upload_part(self, upload_id: str, part_no: int, data: bytes) -> MultipartPart:
        raise NotImplementedError

    async def abort(self, upload_id: str) -> None:
        raise NotImplementedError

    async def check(self, sha256: str, size: int) -> ExistingObjectRef | None:
        raise NotImplementedError


class _StubStorage(BaseObjectStorage):
    def __init__(self) -> None:
        self.deleted: ConcurrentStableList[str] = ConcurrentStableList()

    async def put(self, key: str, data: bytes, *, content_type: str | None = None) -> StoredObject:
        raise NotImplementedError

    async def get(self, key: str) -> bytes:
        raise NotImplementedError

    async def delete(self, key: str) -> None:
        self.deleted.append(key)

    async def exists(self, key: str) -> bool:
        return False

    async def presign(self, key: str, *, method: str = "GET", expires_in: int = DEFAULT_PRESIGN_TTL) -> PresignedUrl:
        raise NotImplementedError


class _QuotaClient(BaseServiceClient):
    def __init__(self, *, code: int = 0) -> None:
        self.code = code
        self.calls: ConcurrentStableList[str] = ConcurrentStableList()

    async def call(self, request: ServiceRequest) -> ServiceResponse:
        self.calls.append(request.path)
        return ServiceResponse(
            status_code=409 if self.code else 200,
            content=stable_json_dumps(
                {"code": self.code, "message": "x", "data": {"quota_key": "storage_bytes", "limit": 1, "used": 1}}
            ).encode(),
        )


def _wire(app: FastAPI, client: _QuotaClient) -> _StubStorage:
    storage = _StubStorage()
    app.dependency_overrides[get_multipart_upload] = lambda: _StubStore()
    app.dependency_overrides[get_object_storage] = lambda: storage
    app.dependency_overrides[get_service_client] = lambda: client
    return storage


async def test_complete_upload_consumes_storage(client: AsyncClient, service_app: FastAPI) -> None:
    """成功：占用存储配额一次。"""
    quota = _QuotaClient()
    _wire(service_app, quota)
    resp = await client.post(API)
    assert resp.status_code == 200
    assert quota.calls and quota.calls[0].endswith("/quotas/consume")


async def test_complete_upload_rejects_and_cleans_on_exceeded(client: AsyncClient, service_app: FastAPI) -> None:
    """超限：82005 + 删除已合并对象。"""
    storage = _wire(service_app, _QuotaClient(code=82005))
    resp = await client.post(API)
    assert resp.status_code == 409 and resp.json()["code"] == 82005
    assert storage.deleted == ["k1"]


async def test_complete_upload_fail_open_when_quota_unavailable(client: AsyncClient, service_app: FastAPI) -> None:
    """配额服务不可用：fail-open 放行（不删除对象）。"""
    client_stub = _QuotaClient(code=10007)
    storage = _wire(service_app, client_stub)
    resp = await client.post(API)
    assert resp.status_code == 200
    assert storage.deleted == []
