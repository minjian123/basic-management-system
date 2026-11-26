"""文件存储契约与双实现测试（Kiwi 47 / 661 / 662）：契约 / 常量 / local 真实读写 / minio 延迟导入与校验。"""

import logging
import sys
from dataclasses import FrozenInstanceError
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from support import build_snapshot

from bms_core.core.assembly import MinioObjectStorageFactory
from bms_core.core.base import BaseObject
from bms_core.core.capability import BaseCapability, BaseNullObject
from bms_core.core.concurrent import ConcurrentStableDict
from bms_core.core.config import MinioSettings, PluginSelection, Settings
from bms_core.core.exceptions import NotFoundError, PluginError
from bms_core.core.plugin import plugin_registry_snapshot
from bms_core.storage.base import (
    DEFAULT_PRESIGN_TTL,
    NULL_ETAG,
    NULL_PRESIGNED_URL,
    STORAGE_BUCKET,
    BaseObjectStorage,
    PresignedUrl,
    StoredObject,
)
from bms_core.storage.local import LocalObjectStorage
from bms_core.storage.minio import MinioObjectStorage
from bms_core.storage.null import NullObjectStorage


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


class _FakeS3Error(Exception):
    """假 SDK 异常（带 S3 code 属性，替换 `minio.error.S3Error`）。"""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class _FakeBody:
    """假对象响应体（可读 / 可关闭）。"""

    def __init__(self, data: bytes) -> None:
        self._data = data
        self.closed = False
        self.released = False

    def read(self) -> bytes:
        """读取全部内容。"""
        return self._data

    def close(self) -> None:
        """关闭（记录调用）。"""
        self.closed = True

    def release_conn(self) -> None:
        """归还连接（记录调用）。"""
        self.released = True


class _FakeMinioClient:
    """假 MinIO 客户端（内存对象表；不连服务）。"""

    def __init__(self) -> None:
        self.objects: ConcurrentStableDict[tuple[str, str], bytes] = ConcurrentStableDict()

    def put_object(self, bucket: str, key: str, stream: Any, length: int, content_type: str | None = None) -> None:
        """写入对象。"""
        del length, content_type
        self.objects.set((bucket, key), stream.read())

    def get_object(self, bucket: str, key: str) -> _FakeBody:
        """读取对象（未命中抛 NoSuchKey）。"""
        if (bucket, key) not in self.objects:
            raise _FakeS3Error("NoSuchKey")
        return _FakeBody(self.objects[(bucket, key)])

    def remove_object(self, bucket: str, key: str) -> None:
        """删除对象（未命中抛 NoSuchKey）。"""
        if (bucket, key) not in self.objects:
            raise _FakeS3Error("NoSuchKey")
        self.objects.delete((bucket, key))

    def stat_object(self, bucket: str, key: str) -> None:
        """对象存在判定（未命中抛 NoSuchKey）。"""
        if (bucket, key) not in self.objects:
            raise _FakeS3Error("NoSuchKey")

    def presigned_get_object(self, bucket: str, key: str, expires: object) -> str:
        """GET 预签名。"""
        del expires
        return f"http://minio.local/{bucket}/{key}?method=GET"

    def presigned_put_object(self, bucket: str, key: str, expires: object) -> str:
        """PUT 预签名。"""
        del expires
        return f"http://minio.local/{bucket}/{key}?method=PUT"


def _stub_minio_client(monkeypatch: pytest.MonkeyPatch) -> _FakeMinioClient:
    """以假异常 / 假客户端替换 MinIO 交互面（不导入 SDK、不连服务）。

    Args:
        monkeypatch: pytest 补丁夹具。

    Returns:
        _FakeMinioClient: 假客户端实例。
    """
    monkeypatch.setattr("minio.error.S3Error", _FakeS3Error)
    client = _FakeMinioClient()

    def _fake_ensure_client(storage: MinioObjectStorage) -> _FakeMinioClient:
        del storage
        return client

    monkeypatch.setattr(MinioObjectStorage, "_ensure_client", _fake_ensure_client)
    return client


@pytest.mark.kiwi_id(47)
async def test_dependency_provider_resolves(service_app: FastAPI, tmp_path: Path) -> None:
    """依赖解析：装配态对象存储是 `local` 实现，且从应用状态取到的就是它。

    插件实例按应用隔离（13_11）：不比跨应用实例同一性；直接调实例验证读写落盘。
    """
    storage = service_app.state.object_storage
    assert isinstance(storage, LocalObjectStorage)
    assert service_app.state.plugin_providers["object_storage"] == "local"

    stored = await storage.put("probe.txt", b"abc")
    assert stored.size == 3
    assert await storage.get("probe.txt") == b"abc"


@pytest.mark.kiwi_id(661)
async def test_local_storage_real_read_write(tmp_path: Path) -> None:
    """local 真实读写：原子写 / 回读 / 幂等删除 / 未命中 / presign file:// / 键安全。"""
    storage = LocalObjectStorage(root=tmp_path)
    stored = await storage.put("docs/readme.txt", b"hello", content_type="text/plain")
    assert stored.size == 5
    assert stored.content_type == "text/plain"
    assert stored.etag
    assert (tmp_path / "docs" / "readme.txt").read_bytes() == b"hello"
    assert await storage.get("docs/readme.txt") == b"hello"
    assert await storage.exists("docs/readme.txt") is True
    await storage.delete("docs/readme.txt")
    await storage.delete("docs/readme.txt")
    assert await storage.exists("docs/readme.txt") is False
    with pytest.raises(NotFoundError, match="对象不存在"):
        await storage.get("docs/readme.txt")
    presigned = await storage.presign("docs/readme.txt", method="PUT", expires_in=60)
    assert presigned.url.startswith("file://")
    assert presigned.method == "PUT"
    assert presigned.expires_in == 60
    with pytest.raises(ValueError, match="非法对象 key"):
        await storage.put("../escape.txt", b"x")
    with pytest.raises(ValueError, match="非法对象 key"):
        await storage.put("/abs.txt", b"x")


@pytest.mark.kiwi_id(661)
def test_storage_provider_switch_zero_change() -> None:
    """配置切换零改动：minio 配置齐备时**装配工厂**产出 `MinioObjectStorage`，消费方只看基类接口。

    13_11 后装配常驻、配置启动固化，同进程内改配置再装配不是真实形态；这里直接驱动工厂
    （配置 → 实现）这段真实逻辑，不伪造装配流程。
    """
    settings = Settings(
        storage=PluginSelection(provider="minio", options=ConcurrentStableDict({"bucket": "switch-bucket"})),
        multipart_upload=PluginSelection(provider="minio"),
        minio=MinioSettings(endpoint="localhost:9000", access_key="ak", secret_key="sk"),
    )
    produced = MinioObjectStorageFactory(settings).create()

    assert isinstance(produced, MinioObjectStorage)
    assert isinstance(produced, BaseObjectStorage)
    assert produced.key == BaseObjectStorage.key


@pytest.mark.kiwi_id(661)
def test_dual_implementations_enlisted(service_app: FastAPI) -> None:
    """双实现纳管：装配快照与插件注册表均含 local / minio（+ null），当前 provider 为 local。

    插件注册表是进程级全局对象，同进程其他用例可能注册过替身实现（如归档用例的 `fake`），
    故按「必须包含」判定，不锁死集合相等。
    """
    snapshot = build_snapshot()
    assert {"local", "minio", "null"} <= set(snapshot["object_storage"])
    assert isinstance(service_app.state.object_storage, LocalObjectStorage)
    assert {"local", "minio", "null"} <= set(plugin_registry_snapshot()["object_storage"])


@pytest.mark.kiwi_id(662)
def test_minio_module_import_is_lazy(monkeypatch: pytest.MonkeyPatch) -> None:
    """延迟导入：构造实例不拉 SDK（构造后 minio 仍未进入 `sys.modules`）。"""
    for name in [name for name in sys.modules if name == "minio" or name.startswith("minio.")]:
        monkeypatch.delitem(sys.modules, name, raising=False)
    MinioObjectStorage(endpoint="localhost:9000", access_key="ak", secret_key="sk")
    assert not any(name == "minio" or name.startswith("minio.") for name in sys.modules)


@pytest.mark.kiwi_id(662)
def test_minio_rejects_missing_config() -> None:
    """缺配置拒启：端点 / 凭据缺失 → `PluginError`（信息可读、不含密钥值）。"""
    settings = Settings(
        storage=PluginSelection(provider="minio"),
        multipart_upload=PluginSelection(provider="minio"),
        minio=MinioSettings(),
    )
    with pytest.raises(PluginError, match="端点 / 凭据"):
        MinioObjectStorageFactory(settings).create()


@pytest.mark.kiwi_id(662)
def test_minio_secret_not_leaked(caplog: pytest.LogCaptureFixture) -> None:
    """密钥分离：私钥只经配置对象注入，不出现在实例表示与启动日志。"""
    sentinel = "sentinel-secret-662"
    settings = Settings(
        storage=PluginSelection(provider="minio"),
        multipart_upload=PluginSelection(provider="minio"),
        minio=MinioSettings(endpoint="localhost:9000", access_key="ak-662", secret_key=sentinel),
    )
    with caplog.at_level(logging.INFO):
        storage = MinioObjectStorageFactory(settings).create()
        assert sentinel not in repr(storage)
    assert sentinel not in caplog.text


@pytest.mark.kiwi_id(662)
async def test_minio_client_methods_with_stub(monkeypatch: pytest.MonkeyPatch) -> None:
    """客户端方法映射（假客户端，不连通）：未命中转 NotFoundError / 删除幂等 / presign 分派。"""
    storage = MinioObjectStorage(endpoint="localhost:9000", access_key="ak", secret_key="sk")
    client = _stub_minio_client(monkeypatch)
    stored = await storage.put("docs/a.bin", b"data", content_type="application/octet-stream")
    assert stored.size == 4
    assert stored.content_type == "application/octet-stream"
    assert client.objects[(STORAGE_BUCKET, "docs/a.bin")] == b"data"
    assert await storage.get("docs/a.bin") == b"data"
    assert await storage.exists("docs/a.bin") is True
    await storage.delete("docs/a.bin")
    await storage.delete("docs/a.bin")
    assert await storage.exists("docs/a.bin") is False
    with pytest.raises(NotFoundError, match="对象不存在"):
        await storage.get("docs/a.bin")
    get_url = await storage.presign("docs/a.bin")
    put_url = await storage.presign("docs/a.bin", method="PUT", expires_in=120)
    assert get_url.url.endswith("method=GET")
    assert get_url.method == "GET"
    assert put_url.url.endswith("method=PUT")
    assert put_url.expires_in == 120


class _FailingMinioClient(_FakeMinioClient):
    """假客户端：读取 / 删除恒定抛非 `NoSuchKey` 的 S3 错误（透传分支）。"""

    def get_object(self, bucket: str, key: str) -> _FakeBody:
        """恒定抛权限类错误（非未命中）。"""
        del bucket, key
        raise _FakeS3Error("AccessDenied")

    def remove_object(self, bucket: str, key: str) -> None:
        """恒定抛权限类错误（非未命中）。"""
        del bucket, key
        raise _FakeS3Error("AccessDenied")


@pytest.mark.kiwi_id(662)
async def test_minio_ensure_client_builds_sdk_client_once(monkeypatch: pytest.MonkeyPatch) -> None:
    """惰性客户端：首次调用导入 SDK 并构造；再次调用复用同一实例（不重建）。"""
    storage = MinioObjectStorage(endpoint="localhost:9000", access_key="ak", secret_key="sk")
    assert storage._client is None  # pyright: ignore[reportPrivateUsage]

    built = storage._ensure_client()  # pyright: ignore[reportPrivateUsage]

    assert built is storage._ensure_client()  # pyright: ignore[reportPrivateUsage]
    assert type(built).__name__ == "Minio"


@pytest.mark.kiwi_id(662)
async def test_minio_passes_through_non_missing_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    """非 `NoSuchKey` 的 S3 错误原样透传：读取不误判为未命中、删除不静默吞错。"""
    storage = MinioObjectStorage(endpoint="localhost:9000", access_key="ak", secret_key="sk")
    failing = _FailingMinioClient()

    def _ensure(storage: MinioObjectStorage) -> _FailingMinioClient:
        del storage
        return failing

    monkeypatch.setattr("minio.error.S3Error", _FakeS3Error)
    monkeypatch.setattr(MinioObjectStorage, "_ensure_client", _ensure)

    with pytest.raises(_FakeS3Error, match="AccessDenied"):
        await storage.get("docs/x.bin")
    with pytest.raises(_FakeS3Error, match="AccessDenied"):
        await storage.delete("docs/x.bin")
