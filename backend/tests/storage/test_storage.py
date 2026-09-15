"""文件存储基座契约测试（Kiwi 47）：契约 / 标识 / 常量 / 数据契约 / 占位固定返回 / 依赖解析。"""

from dataclasses import FrozenInstanceError
from typing import Annotated

import pytest
from fastapi import Depends
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_object_storage
from app.core.base import BaseObject
from app.core.capability import BaseCapability, BaseNullObject
from app.main import create_app, lifespan
from app.storage.base import (
    DEFAULT_PRESIGN_TTL,
    NULL_ETAG,
    NULL_PRESIGNED_URL,
    STORAGE_BUCKET,
    BaseObjectStorage,
    PresignedUrl,
    StoredObject,
)
from app.storage.null import NullObjectStorage


@pytest.mark.kiwi_id(47)
def test_inheritance_and_key() -> None:
    """契约继承链、占位标记与能力域标识。"""
    assert issubclass(BaseCapability, BaseObject)
    assert issubclass(BaseObjectStorage, BaseCapability)
    assert issubclass(NullObjectStorage, BaseObjectStorage)
    assert issubclass(NullObjectStorage, BaseNullObject)
    assert BaseObjectStorage.key == "object_storage"

    storage = NullObjectStorage()
    assert storage.placeholder is True
    assert "占位实现" in storage.describe()


@pytest.mark.kiwi_id(47)
def test_constants() -> None:
    """桶名与预签名默认有效期常量。"""
    assert STORAGE_BUCKET == "bms-files"
    assert DEFAULT_PRESIGN_TTL == 3600


@pytest.mark.kiwi_id(47)
def test_data_contracts_defaults_and_frozen() -> None:
    """`StoredObject` / `PresignedUrl` 默认值正确且不可变。"""
    stored = StoredObject(key="a/b.txt", size=3)
    assert stored.content_type is None
    assert stored.etag is None

    presigned = PresignedUrl(url="http://x/y", expires_in=60)
    assert presigned.method == "GET"

    field = "size"
    with pytest.raises(FrozenInstanceError):
        setattr(stored, field, 9)


@pytest.mark.kiwi_id(47)
async def test_null_put_echoes() -> None:
    """占位 put 回显对象元数据（不落盘）。"""
    storage = NullObjectStorage()
    stored = await storage.put("a/b.txt", b"hello", content_type="text/plain")
    assert stored == StoredObject(key="a/b.txt", size=5, content_type="text/plain", etag=NULL_ETAG)


@pytest.mark.kiwi_id(47)
async def test_null_get_exists_delete() -> None:
    """占位 get 空字节、exists 恒 True、delete 空操作。"""
    storage = NullObjectStorage()
    assert await storage.get("a/b.txt") == b""
    assert await storage.exists("a/b.txt") is True
    assert await storage.delete("a/b.txt") is None


@pytest.mark.kiwi_id(47)
async def test_null_presign_fixed() -> None:
    """占位 presign 固定返回（url 常量、expires_in / method 回显）。"""
    storage = NullObjectStorage()
    presigned = await storage.presign("a/b.txt", method="PUT", expires_in=120)
    assert presigned == PresignedUrl(url=NULL_PRESIGNED_URL, expires_in=120, method="PUT")
    assert presigned.url == "null-presigned-url"


@pytest.mark.kiwi_id(47)
async def test_dependency_provider_resolves() -> None:
    """依赖解析：应用装配占位对象存储；路由经 get_object_storage 取到同一实例。"""
    app = create_app()
    async with lifespan(app):
        assert isinstance(app.state.object_storage, NullObjectStorage)

        @app.get("/object-storage-probe")
        async def probe(  # pyright: ignore[reportUnusedFunction]
            storage: Annotated[BaseObjectStorage, Depends(get_object_storage)],
        ) -> dict[str, object]:
            stored = await storage.put("probe.txt", b"abc")
            return {"key": storage.key, "type": type(storage).__name__, "size": stored.size}

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/object-storage-probe")

        assert resp.status_code == 200
        assert resp.json() == {"key": "object_storage", "type": "NullObjectStorage", "size": 3}
