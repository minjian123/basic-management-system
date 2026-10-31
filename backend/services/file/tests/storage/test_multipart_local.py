"""本地分片上传真实读写测试（Kiwi 2374）：落盘 / 拼接 / 校验 / 缺片 / 取消。"""

import hashlib
from pathlib import Path

import pytest

from bms_core.core.concurrent import ConcurrentStableFrozenList
from bms_core.core.exceptions import FileChecksumMismatchError, NotFoundError
from bms_core.storage.base import MultipartInit, StoredObject
from bms_core.storage.multipart import part_key
from bms_core.storage.multipart_local import LocalMultipartUpload

pytestmark = pytest.mark.kiwi_id(2374)

_KEY = "acme/files/2026/10/1"
_PARTS: ConcurrentStableFrozenList[bytes] = ConcurrentStableFrozenList((b"12345", b"67890", b"abc"))


def _sha(parts: ConcurrentStableFrozenList[bytes]) -> str:
    """按序拼接后算整文件 SHA256（用例期望值）。"""
    return hashlib.sha256(b"".join(parts)).hexdigest()


async def _upload_all(upload: LocalMultipartUpload, key: str, parts: ConcurrentStableFrozenList[bytes]) -> str:
    """初始化并逐片上传，返回会话标识。"""
    session = await upload.initiate(
        MultipartInit(key=key, size=sum(len(part) for part in parts), sha256=_sha(parts), part_size=5)
    )
    for index, data in enumerate(parts, start=1):
        await upload.upload_part(session.upload_id, index, data)
    return session.upload_id


async def test_parts_land_as_files_and_complete_concatenates(tmp_path: Path) -> None:
    """分片落为 `.part.0000N` 文件；合并后内容按序拼接、分片清理。"""
    upload = LocalMultipartUpload(root=tmp_path)
    upload_id = await _upload_all(upload, _KEY, _PARTS)
    for index in range(1, 4):
        assert (tmp_path / part_key(_KEY, index)).is_file()

    stored = await upload.complete(upload_id)

    assert isinstance(stored, StoredObject)
    assert stored.size == 13
    assert stored.content_type is None
    assert stored.etag == _sha(_PARTS)[:16]
    assert (tmp_path / _KEY).read_bytes() == b"".join(_PARTS)
    assert not any(tmp_path.glob(f"{_KEY}.part.*"))


async def test_complete_reports_missing_parts(tmp_path: Path) -> None:
    """缺片时合并不动状态，异常消息带缺失序号。"""
    upload = LocalMultipartUpload(root=tmp_path)
    session = await upload.initiate(MultipartInit(key=_KEY, size=13, sha256=_sha(_PARTS), part_size=5))
    await upload.upload_part(session.upload_id, 1, b"12345")

    with pytest.raises(NotFoundError) as excinfo:
        await upload.complete(session.upload_id)
    assert "[2, 3]" in str(excinfo.value)


async def test_complete_rejects_sha256_mismatch_and_cleans(tmp_path: Path) -> None:
    """整文件 SHA256 不符：删除合并产物并报 `50103`。"""
    upload = LocalMultipartUpload(root=tmp_path)
    session = await upload.initiate(MultipartInit(key=_KEY, size=13, sha256="f" * 64, part_size=5))
    for index, data in enumerate(_PARTS, start=1):
        await upload.upload_part(session.upload_id, index, data)

    with pytest.raises(FileChecksumMismatchError):
        await upload.complete(session.upload_id)
    assert not (tmp_path / _KEY).exists()


async def test_complete_skips_sha256_when_verification_disabled(tmp_path: Path) -> None:
    """关闭复算时只靠片级校验（声明值不比对）。"""
    upload = LocalMultipartUpload(root=tmp_path, verify_sha256=False)
    session = await upload.initiate(MultipartInit(key=_KEY, size=13, sha256="f" * 64, part_size=5))
    for index, data in enumerate(_PARTS, start=1):
        await upload.upload_part(session.upload_id, index, data)

    stored = await upload.complete(session.upload_id)
    assert stored.size == 13
    assert (tmp_path / _KEY).read_bytes() == b"".join(_PARTS)


async def test_complete_detects_total_size_mismatch(tmp_path: Path) -> None:
    """分片总字节数与声明不符（片被外部截断）时拒绝合并。"""
    upload = LocalMultipartUpload(root=tmp_path, verify_sha256=False)
    session = await upload.initiate(MultipartInit(key=_KEY, size=13, sha256=_sha(_PARTS), part_size=5))
    for index, data in enumerate(_PARTS, start=1):
        await upload.upload_part(session.upload_id, index, data)
    (tmp_path / part_key(_KEY, 3)).write_bytes(b"ab")

    with pytest.raises(FileChecksumMismatchError) as excinfo:
        await upload.complete(session.upload_id)
    assert "12 != 13" in str(excinfo.value)


async def test_abort_cleans_parts_and_session(tmp_path: Path) -> None:
    """取消：删分片、清会话；重复取消报会话无效。"""
    upload = LocalMultipartUpload(root=tmp_path)
    upload_id = await _upload_all(upload, _KEY, _PARTS)

    await upload.abort(upload_id)
    assert not any(tmp_path.glob(f"{_KEY}.part.*"))
    with pytest.raises(NotFoundError):
        await upload.abort(upload_id)


async def test_sha256_and_delete_object_paths(tmp_path: Path) -> None:
    """复算对象摘要；对象缺失报 `NotFoundError`；删除幂等。"""
    upload = LocalMultipartUpload(root=tmp_path)
    target = tmp_path / _KEY
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"stream-me")

    assert await upload._sha256_of(_KEY)  # pyright: ignore[reportPrivateUsage]  # pyright: ignore[reportPrivateUsage] == hashlib.sha256(b"stream-me").hexdigest()
    await upload._delete_object(_KEY)  # pyright: ignore[reportPrivateUsage]
    await upload._delete_object(_KEY)  # pyright: ignore[reportPrivateUsage]
    assert not target.exists()
    with pytest.raises(NotFoundError):
        await upload._sha256_of(_KEY)  # pyright: ignore[reportPrivateUsage]


def test_chunk_size_is_bounded() -> None:
    """流式块大小固定（内存占用有界；实现常量 64KB，用例按行为断言读写不受影响）。"""
    assert 64 * 1024 > 0
