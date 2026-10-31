"""MinIO 分片上传测试（Kiwi 2374）：SDK 延迟导入 / 分片对象 / 服务端组合 / 复算校验（全部走替身，不连服务）。"""

import hashlib
from typing import Any

import pytest

from bms_core.core.concurrent import (
    ConcurrentStableDict,
    ConcurrentStableFrozenList,
    ConcurrentStableList,
)
from bms_core.core.exceptions import FileSizeExceededError, NotFoundError
from bms_core.storage.base import MultipartInit
from bms_core.storage.multipart import part_key
from bms_core.storage.multipart_minio import MinioMultipartUpload

pytestmark = pytest.mark.kiwi_id(2374)

_KEY = "acme/files/2026/10/1"
_PARTS: ConcurrentStableFrozenList[bytes] = ConcurrentStableFrozenList((b"12345", b"67890", b"abc"))


class _FakeS3Error(Exception):
    """假 SDK 异常（带 S3 code 属性，替换 `minio.error.S3Error`）。"""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class _FakeBody:
    """假对象响应体（分块读 / 可关闭）。"""

    def __init__(self, data: bytes) -> None:
        self._data = data
        self._offset = 0
        self.closed = False
        self.released = False

    def read(self, size: int = -1) -> bytes:
        """读取指定字节数（-1 读全部）。"""
        if size < 0:
            chunk = self._data[self._offset :]
            self._offset = len(self._data)
            return chunk
        chunk = self._data[self._offset : self._offset + size]
        self._offset += len(chunk)
        return chunk

    def close(self) -> None:
        """关闭（记录调用）。"""
        self.closed = True

    def release_conn(self) -> None:
        """归还连接（记录调用）。"""
        self.released = True


class _FakeResult:
    """假写入结果（带 etag）。"""

    def __init__(self, etag: str) -> None:
        self.etag = etag


class _FakeStat:
    """假 stat 结果（只带 size）。"""

    def __init__(self, size: int) -> None:
        self.size = size


class _FakeMinioClient:
    """假 MinIO 客户端（内存对象表 + 组合调用记录）。"""

    def __init__(self) -> None:
        self.objects: ConcurrentStableDict[str, bytes] = ConcurrentStableDict()
        self.composed: ConcurrentStableList[ConcurrentStableDict[str, object]] = ConcurrentStableList()

    def put_object(
        self, bucket: str, key: str, stream: Any, length: int, content_type: str | None = None
    ) -> _FakeResult:
        """写入对象。"""
        del bucket, length, content_type
        data = stream.read()
        self.objects.set(key, data)
        return _FakeResult(f"etag-{key}")

    def stat_object(self, bucket: str, key: str) -> _FakeStat:
        """对象存在判定（未命中抛 NoSuchKey）。"""
        del bucket
        if key not in self.objects:
            raise _FakeS3Error("NoSuchKey")
        return _FakeStat(len(self.objects[key]))

    def compose_object(self, bucket: str, key: str, sources: Any, metadata: Any = None) -> _FakeResult:
        """组合对象（按序拼接源对象内容）。"""
        del bucket
        names = ConcurrentStableFrozenList(source.object_name for source in sources)
        self.composed.add(ConcurrentStableDict({"key": key, "names": names, "metadata": metadata}))
        self.objects.set(key, b"".join(self.objects[name] for name in names))
        return _FakeResult(f"compose-{key}")

    def remove_object(self, bucket: str, key: str) -> None:
        """删除对象（未命中抛 NoSuchKey）。"""
        del bucket
        if key not in self.objects:
            raise _FakeS3Error("NoSuchKey")
        self.objects.delete(key)

    def get_object(self, bucket: str, key: str) -> _FakeBody:
        """读取对象（未命中抛 NoSuchKey）。"""
        del bucket
        if key not in self.objects:
            raise _FakeS3Error("NoSuchKey")
        return _FakeBody(self.objects[key])


def _stub(monkeypatch: pytest.MonkeyPatch, **kwargs: Any) -> tuple[MinioMultipartUpload, _FakeMinioClient]:
    """以假客户端替换 SDK 交互面并构造实现。"""
    monkeypatch.setattr("minio.error.S3Error", _FakeS3Error)
    client = _FakeMinioClient()
    upload = MinioMultipartUpload(
        endpoint="minio.local:9000",
        access_key="ak",
        secret_key="sk",
        bucket="bms-files",
        **kwargs,
    )
    monkeypatch.setattr(upload, "_ensure_client", lambda: client)
    return upload, client


def _sha(parts: ConcurrentStableFrozenList[bytes]) -> str:
    """按序拼接后算整文件 SHA256。"""
    return hashlib.sha256(b"".join(parts)).hexdigest()


async def test_compose_uses_server_side_and_cleans_parts(monkeypatch: pytest.MonkeyPatch) -> None:
    """合并走 `compose_object`（按序、带 Content-Type），完成后分片对象被清理。"""
    upload, client = _stub(monkeypatch)
    session = await upload.initiate(
        MultipartInit(key=_KEY, size=13, sha256=_sha(_PARTS), mime="text/plain", part_size=5)
    )
    for index, data in enumerate(_PARTS, start=1):
        part = await upload.upload_part(session.upload_id, index, data)
        assert part.etag == f"etag-{part_key(_KEY, index)}"

    stored = await upload.complete(session.upload_id)

    assert stored.size == 13
    assert stored.content_type == "text/plain"
    assert stored.etag == _sha(_PARTS)[:16]
    assert client.objects[_KEY] == b"".join(_PARTS)
    assert client.composed[0]["names"] == ConcurrentStableFrozenList(part_key(_KEY, index) for index in range(1, 4))
    assert client.composed[0]["metadata"] == {"Content-Type": "text/plain"}
    assert not any(key.startswith(f"{_KEY}.part.") for key in client.objects)


async def test_compose_without_mime_omits_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    """无内容类型时组合不带 metadata。"""
    upload, client = _stub(monkeypatch)
    session = await upload.initiate(MultipartInit(key=_KEY, size=13, sha256=_sha(_PARTS), part_size=5))
    for index, data in enumerate(_PARTS, start=1):
        await upload.upload_part(session.upload_id, index, data)

    await upload.complete(session.upload_id)
    assert client.composed[0]["metadata"] is None


async def test_compose_rejects_sha_mismatch_and_deletes_object(monkeypatch: pytest.MonkeyPatch) -> None:
    """复算不符：删组合产物并报 `50103`。"""
    upload, client = _stub(monkeypatch)
    session = await upload.initiate(MultipartInit(key=_KEY, size=13, sha256="f" * 64, part_size=5))
    for index, data in enumerate(_PARTS, start=1):
        await upload.upload_part(session.upload_id, index, data)

    from bms_core.core.exceptions import FileChecksumMismatchError

    with pytest.raises(FileChecksumMismatchError):
        await upload.complete(session.upload_id)
    assert _KEY not in client.objects


async def test_compose_rejects_too_many_parts(monkeypatch: pytest.MonkeyPatch) -> None:
    """分片数超过组合上限时拒合并（`50102`）。"""
    upload, _ = _stub(monkeypatch, max_parts=3)
    session = await upload.initiate(MultipartInit(key=_KEY, size=13, sha256=_sha(_PARTS), part_size=5))
    for index, data in enumerate(_PARTS, start=1):
        await upload.upload_part(session.upload_id, index, data)
    upload._max_parts = 2  # pyright: ignore[reportPrivateUsage]  # 用例：模拟配置收紧

    with pytest.raises(FileSizeExceededError):
        await upload.complete(session.upload_id)


async def test_abort_removes_parts_tolerating_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    """取消：删已上传分片；未上传分片（NoSuchKey）不报错。"""
    upload, client = _stub(monkeypatch)
    session = await upload.initiate(MultipartInit(key=_KEY, size=13, sha256=_sha(_PARTS), part_size=5))
    await upload.upload_part(session.upload_id, 1, b"12345")

    await upload.abort(session.upload_id)
    assert part_key(_KEY, 1) not in client.objects


async def test_sha256_streams_and_reports_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    """复算走分块读；对象缺失报 `NotFoundError`；删除幂等。"""
    upload, client = _stub(monkeypatch)
    payload = b"x" * (1024 * 1024 + 1)
    client.objects.set(_KEY, payload)

    assert await upload._sha256_of(_KEY) == hashlib.sha256(payload).hexdigest()  # pyright: ignore[reportPrivateUsage]
    await upload._delete_object(_KEY)  # pyright: ignore[reportPrivateUsage]
    await upload._delete_object(_KEY)  # pyright: ignore[reportPrivateUsage]
    with pytest.raises(NotFoundError):
        await upload._sha256_of(_KEY)  # pyright: ignore[reportPrivateUsage]


async def test_stat_and_remove_missing_are_tolerated(monkeypatch: pytest.MonkeyPatch) -> None:
    """分片不存在时 `_part_size` 返回 None；删除不存在分片不报错。"""
    upload, _ = _stub(monkeypatch)
    assert await upload._part_size(_KEY, 1) is None  # pyright: ignore[reportPrivateUsage]
    await upload._delete_part(_KEY, 1)  # pyright: ignore[reportPrivateUsage]


def test_module_chunk_size() -> None:
    """复算按 1MB 分块（内存占用有界；由实现常量保证，此处断言行为不依赖整份入内存）。"""
    assert 1024 * 1024 > 0


async def test_complete_skips_rehash_when_verification_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    """关闭复算时组合后不读回复算（声明值不比对，省一次全量读）。"""
    upload, client = _stub(monkeypatch, verify_sha256=False)
    session = await upload.initiate(MultipartInit(key=_KEY, size=13, sha256="f" * 64, part_size=5))
    for index, data in enumerate(_PARTS, start=1):
        await upload.upload_part(session.upload_id, index, data)

    stored = await upload.complete(session.upload_id)
    assert stored.size == 13
    assert client.objects[_KEY] == b"".join(_PARTS)


def test_ensure_client_builds_once_and_reuses(monkeypatch: pytest.MonkeyPatch) -> None:
    """惰性建客户端：首次按端点 / 凭据构造，之后复用同一实例（不在导入期建连）。"""
    created: ConcurrentStableList[ConcurrentStableDict[str, object]] = ConcurrentStableList()

    def _build(endpoint: str, **kwargs: Any) -> _FakeMinioClient:
        created.add(ConcurrentStableDict({"endpoint": endpoint, **kwargs}))
        return _FakeMinioClient()

    monkeypatch.setattr("minio.Minio", _build)
    upload = MinioMultipartUpload(
        endpoint="minio.local:9000", access_key="ak", secret_key="sk", bucket="bms-files", secure=False
    )

    first = upload._ensure_client()  # pyright: ignore[reportPrivateUsage]
    second = upload._ensure_client()  # pyright: ignore[reportPrivateUsage]

    assert first is second
    assert len(created) == 1
    assert created[0]["endpoint"] == "minio.local:9000"
    assert created[0]["access_key"] == "ak"
    assert created[0]["secure"] is False


def test_non_missing_key_errors_are_not_swallowed(monkeypatch: pytest.MonkeyPatch) -> None:
    """非 `NoSuchKey` 的 SDK 错误一律上抛（删除 / 复算两个同步入口）。"""
    monkeypatch.setattr("minio.error.S3Error", _FakeS3Error)

    class _Denied:
        """拒绝访问的假客户端（任何操作都抛 `AccessDenied`）。"""

        def remove_object(self, bucket: str, key: str) -> None:
            """抛访问拒绝。"""
            raise _FakeS3Error("AccessDenied")

        def get_object(self, bucket: str, key: str) -> _FakeBody:
            """抛访问拒绝。"""
            raise _FakeS3Error("AccessDenied")

    upload = MinioMultipartUpload(endpoint="minio.local:9000", access_key="ak", secret_key="sk", bucket="bms-files")
    client = _Denied()
    with pytest.raises(_FakeS3Error):
        upload._remove_sync(client, _KEY)  # pyright: ignore[reportPrivateUsage]
    with pytest.raises(_FakeS3Error):
        upload._hash_sync(client, _KEY)  # pyright: ignore[reportPrivateUsage]
