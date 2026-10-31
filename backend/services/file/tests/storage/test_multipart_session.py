"""分片会话快照与上传模板测试（Kiwi 2374）：key 口径 / 载荷往返 / 会话失效 / 配对校验。"""

from pathlib import Path

import pytest
from redis.asyncio import Redis

from bms_core.core.config import get_settings
from bms_core.core.context import reset_current_tenant, set_current_tenant
from bms_core.core.exceptions import FileSizeExceededError, NotFoundError, ParamError, PluginError
from bms_core.storage.base import MultipartInit
from bms_core.storage.multipart import (
    UPLOAD_SESSION_DOMAIN,
    UploadSession,
    UploadSessionStore,
    build_upload_session_key,
    part_key,
)
from bms_core.storage.multipart_local import LocalMultipartUpload

pytestmark = pytest.mark.kiwi_id(2374)

_KEY = "acme/files/2026/10/1"


def _init(size: int, *, part_size: int = 5, sha256: str = "a" * 64, upload_id: str | None = None) -> MultipartInit:
    """构造初始化参数（小分片便于用例）。"""
    return MultipartInit(
        key=_KEY, size=size, sha256=sha256, mime="text/plain", part_size=part_size, upload_id=upload_id
    )


def test_session_key_follows_naming_spec() -> None:
    """会话 key 符合 `bms:{租户|global}:files:upload:{upload_id}`。"""
    assert UPLOAD_SESSION_DOMAIN == "files"
    assert build_upload_session_key(tenant=None, upload_id="u1") == "bms:global:files:upload:u1"
    assert build_upload_session_key(tenant="acme", upload_id="u1") == "bms:acme:files:upload:u1"


def test_part_key_is_zero_padded() -> None:
    """分片 key 为 `{object_key}.part.00001`（字典序即数值序）。"""
    assert part_key("a/b", 1) == "a/b.part.00001"
    assert part_key("a/b", 12) == "a/b.part.00012"


async def test_session_store_roundtrip_and_ttl() -> None:
    """会话快照可往返；写入带 TTL；删除后读不到。"""
    store = UploadSessionStore(ttl_seconds=120)
    token = set_current_tenant("acme")
    try:
        session = UploadSession(key=_KEY, size=10, sha256="b" * 64, mime=None, part_size=5, total_parts=2)
        await store.save("u1", session)
        loaded = await store.load("u1")
        assert loaded == session
        client: Redis = store.redis_client().async_client()
        assert await client.ttl(store.key_of("u1")) > 0
        await store.delete("u1")
        assert await store.load("u1") is None
    finally:
        reset_current_tenant(token)


async def test_session_store_tolerates_broken_payload() -> None:
    """载荷非法（缺字段 / 非 JSON）按会话不存在处理，不抛错。"""
    store = UploadSessionStore(ttl_seconds=60)
    client: Redis = store.redis_client().async_client()
    await client.set(store.key_of("bad"), "not-json")
    assert await store.load("bad") is None


async def test_initiate_computes_total_parts(tmp_path: Path) -> None:
    """初始化按 size / part_size 上取整算分片总数，并回显会话。"""
    upload = LocalMultipartUpload(root=tmp_path)
    session = await upload.initiate(_init(12, part_size=5))
    assert session.total_parts == 3
    assert session.part_size == 5
    assert session.key == _KEY
    assert session.upload_id


async def test_initiate_respects_upload_id_and_max_parts(tmp_path: Path) -> None:
    """指定会话标识时沿用（断点重建）；片数超上限抛 `50102`。"""
    upload = LocalMultipartUpload(root=tmp_path, max_parts=2)
    session = await upload.initiate(_init(8, part_size=5, upload_id="keep-me"))
    assert session.upload_id == "keep-me"
    with pytest.raises(FileSizeExceededError):
        await upload.initiate(_init(100, part_size=5))


async def test_upload_part_rejects_unknown_session_and_bounds(tmp_path: Path) -> None:
    """未知会话 / 序号越界 / 尺寸不符分别拒绝。"""
    upload = LocalMultipartUpload(root=tmp_path)
    with pytest.raises(NotFoundError):
        await upload.upload_part("nope", 1, b"12345")
    session = await upload.initiate(_init(12, part_size=5))
    with pytest.raises(NotFoundError):
        await upload.upload_part(session.upload_id, 4, b"12345")
    with pytest.raises(ParamError):
        await upload.upload_part(session.upload_id, 1, b"1234")


def test_init_schema_rejects_non_positive_part_size() -> None:
    """分片大小非法在契约层就被拒（`MultipartInit` 校验，不产生不可达分支）。"""
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        MultipartInit(key=_KEY, size=10, sha256="c" * 64, part_size=0)


async def test_factories_enforce_storage_pairing(monkeypatch: pytest.MonkeyPatch) -> None:
    """分片 provider 与存储 provider 不配对时装配期拒启（`PluginError`）。"""
    from bms_core.core.assembly import LocalMultipartUploadFactory, MinioMultipartUploadFactory
    from bms_core.core.config import Settings

    settings = get_settings()
    monkeypatch.setattr(settings.storage, "provider", "minio", raising=False)
    with pytest.raises(PluginError):
        LocalMultipartUploadFactory(settings).create(None)

    monkeypatch.setattr(settings.storage, "provider", "local", raising=False)
    with pytest.raises(PluginError):
        MinioMultipartUploadFactory(settings).create(None)

    assert isinstance(settings, Settings)
