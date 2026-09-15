"""MinIO 真实连通集成用例（Kiwi 676）：需 `BMS_TEST_MINIO_*` 环境变量，未配置自动跳过。

激活方式（本地开发机，凭据见本地资源文档；CI 无凭据跳过）：

```bash
export BMS_TEST_MINIO_ENDPOINT=host:9000
export BMS_TEST_MINIO_ACCESS_KEY=...
export BMS_TEST_MINIO_SECRET_KEY=...
export BMS_TEST_MINIO_BUCKET=bms-files   # 可选，缺省 bms-files
uv run pytest tests/integration/test_minio_integration.py -q
```
"""

import os
import uuid

import pytest

from app.storage.base import STORAGE_BUCKET
from app.storage.minio import MinioObjectStorage

pytestmark = pytest.mark.integration

_ENDPOINT_ENV = "BMS_TEST_MINIO_ENDPOINT"
_ACCESS_KEY_ENV = "BMS_TEST_MINIO_ACCESS_KEY"
_SECRET_KEY_ENV = "BMS_TEST_MINIO_SECRET_KEY"
_BUCKET_ENV = "BMS_TEST_MINIO_BUCKET"
_SECURE_ENV = "BMS_TEST_MINIO_SECURE"
_REQUIRED_ENV = (_ENDPOINT_ENV, _ACCESS_KEY_ENV, _SECRET_KEY_ENV)


def _bucket() -> str:
    """桶名（测试环境变量，缺省 `bms-files`）。

    Returns:
        str: 桶名。
    """
    return os.environ.get(_BUCKET_ENV, STORAGE_BUCKET)


def _secure() -> bool:
    """是否 HTTPS。

    Returns:
        bool: 是否安全连接。
    """
    return os.environ.get(_SECURE_ENV, "false").lower() == "true"


def _storage_from_env() -> MinioObjectStorage:
    """从测试环境变量构造 MinIO 实现（真实端点 / 凭据）。

    Returns:
        MinioObjectStorage: 真实实现实例。
    """
    return MinioObjectStorage(
        endpoint=os.environ[_ENDPOINT_ENV],
        access_key=os.environ[_ACCESS_KEY_ENV],
        secret_key=os.environ[_SECRET_KEY_ENV],
        bucket=_bucket(),
        secure=_secure(),
    )


def _ensure_bucket(bucket: str) -> None:
    """桶不存在时创建（幂等）。

    Args:
        bucket: 桶名。
    """
    from minio import Minio
    from minio.error import S3Error

    client = Minio(
        os.environ[_ENDPOINT_ENV],
        access_key=os.environ[_ACCESS_KEY_ENV],
        secret_key=os.environ[_SECRET_KEY_ENV],
        secure=_secure(),
    )
    try:
        client.make_bucket(bucket)
    except S3Error as exc:
        if exc.code != "BucketAlreadyOwnedByYou":
            raise


@pytest.mark.kiwi_id(676)
async def test_minio_real_roundtrip() -> None:
    """真实连通：put / get 回读一致 / exists / presign / delete 幂等（唯一前缀 + 收尾清理）。"""
    if any(not os.environ.get(name) for name in _REQUIRED_ENV):
        pytest.skip("未配置 BMS_TEST_MINIO_*（端点 / 凭据），集成用例跳过")
    storage = _storage_from_env()
    _ensure_bucket(_bucket())
    key = f"bms-it/{uuid.uuid4().hex}.txt"
    data = b"bms-minio-integration"
    try:
        stored = await storage.put(key, data, content_type="text/plain")
        assert stored.size == len(data)
        assert await storage.exists(key) is True
        assert await storage.get(key) == data
        presigned = await storage.presign(key, expires_in=60)
        assert presigned.url.startswith(("http://", "https://"))
        assert presigned.method == "GET"
    finally:
        await storage.delete(key)
    await storage.delete(key)
    assert await storage.exists(key) is False
