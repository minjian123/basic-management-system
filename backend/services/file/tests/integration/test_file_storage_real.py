"""文件存储真机集成用例（Kiwi 2374）：真 MinIO 组合 / 预签名过期 / 会话跨实例共享 / 并发分片。

前置（未配置自动跳过，CI 不受影响）：

```bash
export BMS_TEST_MINIO_ENDPOINT=host:9000
export BMS_TEST_MINIO_ACCESS_KEY=...
export BMS_TEST_MINIO_SECRET_KEY=...
export BMS_TEST_MINIO_BUCKET=bms-files        # 可选
export BMS_REDIS__URL=redis://host:6379/0     # 会话共享用例用
uv run pytest services/file/tests/integration/test_file_storage_real.py -v
```

覆盖《03_01 详细设计》§6 的真机结论项：服务端组合对象正确、预签名过期即不可下载、
会话快照跨实例共享（多实例断点续传）、同片并发重传不破坏合并结果。
"""

# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false
# 说明：minio / redis-py 的客户端方法在严格模式下返回 partially-unknown（stub 未参数化）。

from __future__ import annotations

import asyncio
import hashlib
import os
import time
from collections.abc import Iterator

import pytest

from bms_core.core.concurrent import ConcurrentStableFrozenList
from bms_core.core.context import reset_current_tenant, set_current_tenant
from bms_core.storage.base import DEFAULT_PART_SIZE, MultipartInit
from bms_core.storage.minio import MinioObjectStorage
from bms_core.storage.multipart import UploadSession, UploadSessionStore, part_key
from bms_core.storage.multipart_minio import MinioMultipartUpload

pytestmark = pytest.mark.integration

_ENDPOINT_ENV = "BMS_TEST_MINIO_ENDPOINT"
_ACCESS_KEY_ENV = "BMS_TEST_MINIO_ACCESS_KEY"
_SECRET_KEY_ENV = "BMS_TEST_MINIO_SECRET_KEY"
_BUCKET_ENV = "BMS_TEST_MINIO_BUCKET"
_REQUIRED = (_ENDPOINT_ENV, _ACCESS_KEY_ENV, _SECRET_KEY_ENV)

_REDIS_URL = os.environ.get("BMS_REDIS__URL", "")
"""Redis 连接串（**模块导入期**取快照：测试夹具会清理 `BMS_*` 环境变量）。"""

_KEY = "test-files/2026/10/real"
"""测试对象 key（用后即删；不与业务数据冲突）。"""


def _minio_ready() -> bool:
    """MinIO 凭据是否齐备。

    Returns:
        bool: 齐备为 True。
    """
    return all(os.environ.get(name) for name in _REQUIRED)


def _redis_url() -> str:
    """Redis 连接串（未配置返回空串）。

    Returns:
        str: 连接串。
    """
    return _REDIS_URL


def _bucket() -> str:
    """桶名。

    Returns:
        str: 桶名。
    """
    return os.environ.get(_BUCKET_ENV, "bms-files")


def _storage() -> MinioObjectStorage:
    """构造真实 MinIO 对象存储。

    Returns:
        MinioObjectStorage: 真实实现。
    """
    return MinioObjectStorage(
        endpoint=os.environ[_ENDPOINT_ENV],
        access_key=os.environ[_ACCESS_KEY_ENV],
        secret_key=os.environ[_SECRET_KEY_ENV],
        bucket=_bucket(),
        secure=os.environ.get("BMS_TEST_MINIO_SECURE", "") == "1",
    )


def _parts() -> ConcurrentStableFrozenList[bytes]:
    """构造三片内容（前两片满足 MinIO 组合下限 5MB，末片为一小段）。

    Returns:
        ConcurrentStableFrozenList[bytes]: 分片内容。
    """
    head = b"real-minio-part-"
    filler = b"x" * (DEFAULT_PART_SIZE - len(head))
    return ConcurrentStableFrozenList((head + filler, head + filler, b"tail"))


@pytest.fixture
def real_minio() -> Iterator[MinioObjectStorage]:
    """真 MinIO 夹具（未配置凭据即跳过）。

    Yields:
        MinioObjectStorage: 真实实现。
    """
    if not _minio_ready():
        pytest.skip("未配置 BMS_TEST_MINIO_*（真机用例跳过）")
    yield _storage()


@pytest.fixture
def tenant_scope() -> Iterator[None]:
    """租户上下文夹具（会话 key 需要租户位）。

    Yields:
        None: 用例运行期。
    """
    token = set_current_tenant("real")
    try:
        yield
    finally:
        reset_current_tenant(token)


async def test_multipart_compose_real(real_minio: MinioObjectStorage) -> None:
    """真机：分片落对象 → 服务端组合 → 内容与按序拼接一致 → 分片清理。"""
    parts = _parts()
    data = b"".join(parts)
    upload = MinioMultipartUpload(
        endpoint=os.environ[_ENDPOINT_ENV],
        access_key=os.environ[_ACCESS_KEY_ENV],
        secret_key=os.environ[_SECRET_KEY_ENV],
        bucket=_bucket(),
        part_size=DEFAULT_PART_SIZE,
        verify_sha256=True,
    )
    session = await upload.initiate(
        MultipartInit(key=_KEY, size=len(data), sha256=hashlib.sha256(data).hexdigest(), part_size=DEFAULT_PART_SIZE)
    )
    try:
        for index, chunk in enumerate(parts, start=1):
            await upload.upload_part(session.upload_id, index, chunk)
        stored = await upload.complete(session.upload_id)

        assert stored.size == len(data)
        assert await real_minio.get(_KEY) == data
        assert not await real_minio.exists(part_key(_KEY, 1))
    finally:
        await real_minio.delete(_KEY)


async def test_presign_expires_real(real_minio: MinioObjectStorage) -> None:
    """真机：限时预签名地址过期后不可下载（存储侧返回 403）。"""
    import httpx

    await real_minio.put(_KEY, b"expire-me", content_type="text/plain")
    try:
        presigned = await real_minio.presign(_KEY, expires_in=5)
        async with httpx.AsyncClient(timeout=10) as client:
            fresh = await client.get(presigned.url)
            assert fresh.status_code == 200, fresh.text
            time.sleep(6)
            expired = await client.get(presigned.url)
            assert expired.status_code == 403
    finally:
        await real_minio.delete(_KEY)


async def test_session_shared_across_instances_real(tenant_scope: None) -> None:
    """真机：两套存储实例（独立进程内 L1）共享同一 Redis 会话快照（多实例断点续传）。"""
    url = _redis_url()
    if not url:
        pytest.skip("未配置 BMS_REDIS__URL（会话共享用例跳过）")
    from bms_core.redis.redis import RedisRedisClient

    first = UploadSessionStore(ttl_seconds=60, client=RedisRedisClient(url))
    second = UploadSessionStore(ttl_seconds=60, client=RedisRedisClient(url))
    session = UploadSession(key=_KEY, size=7, sha256="a" * 64, mime=None, part_size=5, total_parts=2)
    try:
        await first.save("real-shared-1", session)
        assert await second.load("real-shared-1") == session
    finally:
        await first.delete("real-shared-1")


async def test_concurrent_part_upload_real(real_minio: MinioObjectStorage) -> None:
    """真机：同片并发重传（两路同时写同一 part）不破坏后续合并。"""
    parts = _parts()
    data = b"".join(parts)
    upload = MinioMultipartUpload(
        endpoint=os.environ[_ENDPOINT_ENV],
        access_key=os.environ[_ACCESS_KEY_ENV],
        secret_key=os.environ[_SECRET_KEY_ENV],
        bucket=_bucket(),
        part_size=DEFAULT_PART_SIZE,
        verify_sha256=False,
    )
    session = await upload.initiate(
        MultipartInit(key=_KEY, size=len(data), sha256="a" * 64, part_size=DEFAULT_PART_SIZE)
    )
    try:
        await asyncio.gather(
            upload.upload_part(session.upload_id, 1, parts[0]),
            upload.upload_part(session.upload_id, 1, parts[0]),
        )
        await upload.upload_part(session.upload_id, 2, parts[1])
        await upload.upload_part(session.upload_id, 3, parts[2])
        stored = await upload.complete(session.upload_id)
        assert stored.size == len(data)
        assert await real_minio.get(_KEY) == data
    finally:
        await real_minio.delete(_KEY)
