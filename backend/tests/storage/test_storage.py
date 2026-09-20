"""文件存储契约与双实现测试（Kiwi 47 / 661 / 662）：契约 / 常量 / local 真实读写 / minio 延迟导入与校验。"""

import importlib
import logging
import pkgutil
import sys
from dataclasses import FrozenInstanceError
from pathlib import Path
from typing import Annotated, Any, cast

import pytest
from fastapi import Depends
from httpx import ASGITransport, AsyncClient

import app as app_pkg
from app.api.deps import get_object_storage
from app.core import plugin as plugin_module
from app.core.base import BaseObject
from app.core.capability import BaseCapability, BaseNullObject
from app.core.config import MinioSettings, PluginSelection, Settings
from app.core.exceptions import NotFoundError, PluginError
from app.core.plugin import BasePluggable, PluginRegistry, resolve_plugin
from app.main import ApplicationFactory, lifespan
from app.storage.base import (
    DEFAULT_PRESIGN_TTL,
    NULL_ETAG,
    NULL_PRESIGNED_URL,
    STORAGE_BUCKET,
    BaseObjectStorage,
    PresignedUrl,
    StoredObject,
)
from app.storage.local import LocalObjectStorage
from app.storage.minio import MinioObjectStorage
from app.storage.null import NullObjectStorage
from tests.contracts.support import build_snapshot


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
async def test_dependency_provider_resolves(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """依赖解析：应用装配缺省对象存储（local）；路由经 get_object_storage 取到同一实例。"""
    monkeypatch.setattr(
        "app.main.get_settings",
        lambda: Settings(storage=PluginSelection(provider="local", options={"root": str(tmp_path)})),
    )
    _isolated_registry(monkeypatch)
    app = ApplicationFactory().create(None)
    async with lifespan(app):
        assert isinstance(app.state.object_storage, LocalObjectStorage)

        @app.get("/object-storage-probe")
        async def probe(  # pyright: ignore[reportUnusedFunction]
            storage: Annotated[BaseObjectStorage, Depends(get_object_storage)],
        ) -> dict[str, object]:
            stored = await storage.put("probe.txt", b"abc")
            return {"key": storage.key, "type": type(storage).__name__, "size": stored.size}

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/object-storage-probe")

        assert resp.status_code == 200
        assert resp.json() == {"key": "object_storage", "type": "LocalObjectStorage", "size": 3}
        assert (tmp_path / "probe.txt").read_bytes() == b"abc"


def _isolated_registry(monkeypatch: pytest.MonkeyPatch) -> None:
    """导入 app 全量模块并把插件子类收集进隔离注册表（替换进程级默认实例）。

    Args:
        monkeypatch: pytest 补丁夹具。
    """
    for info in pkgutil.walk_packages(app_pkg.__path__, prefix="app."):
        if ".tests" in info.name or info.name.endswith("main"):
            continue
        importlib.import_module(info.name)
    registry = PluginRegistry()
    monkeypatch.setattr(plugin_module, "_DEFAULT_REGISTRY", registry)
    pending = list(BasePluggable.__subclasses__())
    while pending:
        cls = pending.pop()
        if cls.__module__.startswith("app."):
            registry.collect(cls)
        pending.extend(cls.__subclasses__())


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
        self.objects: dict[tuple[str, str], bytes] = {}

    def put_object(self, bucket: str, key: str, stream: Any, length: int, content_type: str | None = None) -> None:
        """写入对象。"""
        del length, content_type
        self.objects[(bucket, key)] = stream.read()

    def get_object(self, bucket: str, key: str) -> _FakeBody:
        """读取对象（未命中抛 NoSuchKey）。"""
        if (bucket, key) not in self.objects:
            raise _FakeS3Error("NoSuchKey")
        return _FakeBody(self.objects[(bucket, key)])

    def remove_object(self, bucket: str, key: str) -> None:
        """删除对象（未命中抛 NoSuchKey）。"""
        if (bucket, key) not in self.objects:
            raise _FakeS3Error("NoSuchKey")
        del self.objects[(bucket, key)]

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
async def test_storage_provider_switch_zero_change(monkeypatch: pytest.MonkeyPatch) -> None:
    """配置切换零改动：provider=minio 后既有路由（消费方未改）取到 MinIO 实现。"""
    _isolated_registry(monkeypatch)
    monkeypatch.setattr(
        "app.main.get_settings",
        lambda: Settings(
            storage=PluginSelection(provider="minio", options={"bucket": "switch-bucket"}),
            minio=MinioSettings(endpoint="localhost:9000", access_key="ak", secret_key="sk"),
        ),
    )
    app = ApplicationFactory().create(None)
    async with lifespan(app):
        assert isinstance(app.state.object_storage, MinioObjectStorage)
        assert resolve_plugin("object_storage", "minio") is app.state.object_storage

        @app.get("/storage-switch-probe")
        async def probe(  # pyright: ignore[reportUnusedFunction]
            storage: Annotated[BaseObjectStorage, Depends(get_object_storage)],
        ) -> dict[str, object]:
            return {"type": type(storage).__name__}

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/storage-switch-probe")

        assert resp.status_code == 200
        assert resp.json() == {"type": "MinioObjectStorage"}


@pytest.mark.kiwi_id(661)
async def test_dual_implementations_enlisted() -> None:
    """双实现纳管：装配快照与插件清单均含 local / minio（+ null），状态齐备。"""
    snapshot = build_snapshot()
    assert set(snapshot["object_storage"]) == {"local", "minio", "null"}

    app = ApplicationFactory().create(None)
    async with lifespan(app), AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/v1/plugins")

    assert resp.status_code == 200
    groups = cast("list[dict[str, object]]", resp.json()["data"])
    storage = next(group for group in groups if str(group["plugin_key"]) == "object_storage")
    assert storage["provider"] == "local"
    implementations = cast("list[dict[str, str]]", storage["implementations"])
    assert [(item["plugin_name"], item["status"]) for item in implementations] == [
        ("local", "active"),
        ("minio", "registered"),
        ("null", "registered"),
    ]


@pytest.mark.kiwi_id(662)
def test_minio_module_import_is_lazy(monkeypatch: pytest.MonkeyPatch) -> None:
    """延迟导入：构造实例不拉 SDK（构造后 minio 仍未进入 `sys.modules`）。"""
    for name in [name for name in sys.modules if name == "minio" or name.startswith("minio.")]:
        monkeypatch.delitem(sys.modules, name, raising=False)
    MinioObjectStorage(endpoint="localhost:9000", access_key="ak", secret_key="sk")
    assert not any(name == "minio" or name.startswith("minio.") for name in sys.modules)


@pytest.mark.kiwi_id(662)
async def test_minio_rejects_missing_config(monkeypatch: pytest.MonkeyPatch) -> None:
    """缺配置拒启：端点 / 凭据缺失 → `PluginError`（信息可读、不含密钥值）。"""
    for env in ("BMS_MINIO__ENDPOINT", "BMS_MINIO__ACCESS_KEY", "BMS_MINIO__SECRET_KEY"):
        monkeypatch.delenv(env, raising=False)
    _isolated_registry(monkeypatch)
    monkeypatch.setattr(
        "app.main.get_settings",
        lambda: Settings(storage=PluginSelection(provider="minio"), minio=MinioSettings()),
    )
    app = ApplicationFactory().create(None)
    with pytest.raises(PluginError, match="端点 / 凭据"):
        async with lifespan(app):
            pass


@pytest.mark.kiwi_id(662)
async def test_minio_secret_not_leaked(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    """密钥分离：哨兵私钥经环境变量注入后不出现在启动日志与插件清单响应。"""
    sentinel = "sentinel-secret-662"
    monkeypatch.setenv("BMS_MINIO__ENDPOINT", "localhost:9000")
    monkeypatch.setenv("BMS_MINIO__ACCESS_KEY", "ak-662")
    monkeypatch.setenv("BMS_MINIO__SECRET_KEY", sentinel)
    monkeypatch.setenv("BMS_STORAGE__PROVIDER", "minio")
    _isolated_registry(monkeypatch)
    app = ApplicationFactory().create(None)
    with caplog.at_level(logging.INFO):
        async with lifespan(app):
            assert isinstance(app.state.object_storage, MinioObjectStorage)
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.get("/api/v1/plugins")
            assert resp.status_code == 200
            assert sentinel not in resp.text
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
