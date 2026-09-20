"""分片上传与秒传契约测试（Kiwi 845）。

覆盖：契约与标识 / 数据契约与常量 / 占位会话语义 / 异常处置 / 依赖解析 / 占位路由与幂等接线。
"""

from datetime import UTC, datetime

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError

from app.api.deps import get_idempotency_store, get_multipart_upload
from app.core.capability import BaseCapability, BaseNullObject
from app.core.error_codes import ErrorCode
from app.core.exceptions import NotFoundError
from app.core.plugin import BasePluggable, resolve_plugin
from app.idempotency.base import (
    DEFAULT_IDEMPOTENCY_TTL,
    IDEMPOTENCY_HEADER,
    IDEMPOTENCY_PAYLOAD_TYPE,
    IdempotencyStore,
    build_idempotency_key,
)
from app.main import ApplicationFactory, lifespan
from app.storage.base import (
    DEFAULT_PART_SIZE,
    NULL_ETAG,
    NULL_UPLOAD_ID,
    BaseMultipartUpload,
    ExistingObjectRef,
    MultipartInit,
    MultipartPart,
    MultipartSession,
    StoredObject,
)
from app.storage.null import NullMultipartUpload

API = "/api/v1/files"
"""占位路由前缀（`BaseRouter` 前缀 + 统一 API 前缀）。"""


def _init(
    key: str = "files/a.bin",
    size: int = 11 * 1024 * 1024,
    *,
    mime: str | None = None,
    part_size: int | None = None,
) -> MultipartInit:
    """构造初始化参数对象。

    Args:
        key: 目标对象 key。
        size: 文件字节数。
        mime: 内容类型。
        part_size: 分片大小（字节）。

    Returns:
        MultipartInit: 初始化参数对象。
    """
    return MultipartInit(key=key, size=size, sha256="a" * 64, mime=mime, part_size=part_size)


@pytest.mark.kiwi_id(845)
def test_contract_inheritance_and_identity() -> None:
    """契约继承链、占位标记与能力域标识。"""
    assert issubclass(BaseMultipartUpload, BasePluggable)
    assert issubclass(BaseMultipartUpload, BaseCapability)
    assert issubclass(NullMultipartUpload, BaseMultipartUpload)
    assert issubclass(NullMultipartUpload, BaseNullObject)
    assert BaseMultipartUpload.key == "multipart_upload"
    assert BaseMultipartUpload.plugin_key == "multipart_upload"

    upload = NullMultipartUpload()
    assert upload.placeholder is True
    assert "占位实现" in upload.describe()


@pytest.mark.kiwi_id(845)
def test_constants() -> None:
    """分片缺省大小与会话标识前缀常量。"""
    assert DEFAULT_PART_SIZE == 5 * 1024 * 1024
    assert NULL_UPLOAD_ID == "null-upload-id"


@pytest.mark.kiwi_id(845)
def test_data_contracts_defaults_and_validation() -> None:
    """数据契约字段默认值与取值校验（分片大小 / 字节数须大于 0）。"""
    init = _init()
    assert init.mime is None
    assert init.part_size is None

    session = MultipartSession(upload_id="u1", key="files/a.bin", part_size=DEFAULT_PART_SIZE, total_parts=3)
    assert session.part_size == DEFAULT_PART_SIZE
    assert MultipartPart(part_no=1, etag=NULL_ETAG, size=5).part_no == 1

    ref = ExistingObjectRef(key="files/a.bin", size=5)
    assert ref.content_type is None
    assert ref.etag is None
    assert ref.stored_at is None

    with pytest.raises(ValidationError):
        _init(size=0)
    with pytest.raises(ValidationError):
        _init(part_size=0)


@pytest.mark.kiwi_id(845)
async def test_null_initiate_session() -> None:
    """占位初始化：会话标识递增、key 回显、分片粒度缺省与覆盖、分片总数取整。"""
    upload = NullMultipartUpload()
    first = await upload.initiate(_init())
    assert first.upload_id == f"{NULL_UPLOAD_ID}-1"
    assert first.key == "files/a.bin"
    assert first.part_size == DEFAULT_PART_SIZE
    assert first.total_parts == 3

    second = await upload.initiate(_init(key="files/small.bin", size=DEFAULT_PART_SIZE))
    assert second.upload_id == f"{NULL_UPLOAD_ID}-2"
    assert second.total_parts == 1

    override = await upload.initiate(_init(key="files/c.bin", size=10 * 1024 * 1024, part_size=1024 * 1024))
    assert override.upload_id == f"{NULL_UPLOAD_ID}-3"
    assert override.part_size == 1024 * 1024
    assert override.total_parts == 10


@pytest.mark.kiwi_id(845)
async def test_null_part_complete_abort() -> None:
    """占位分片回显、合并回显会话 key / size，合并或取消后会话失效。"""
    upload = NullMultipartUpload()
    session = await upload.initiate(_init(key="files/b.bin", size=9, mime="text/plain"))
    part = await upload.upload_part(session.upload_id, 1, b"hello")
    assert part == MultipartPart(part_no=1, etag=NULL_ETAG, size=5)

    stored = await upload.complete(session.upload_id)
    assert stored == StoredObject(key="files/b.bin", size=9, content_type="text/plain", etag=NULL_ETAG)
    with pytest.raises(NotFoundError):
        await upload.complete(session.upload_id)
    with pytest.raises(NotFoundError):
        await upload.upload_part(session.upload_id, 1, b"hello")

    aborted = await upload.initiate(_init(key="files/c.bin", size=9))
    await upload.abort(aborted.upload_id)
    with pytest.raises(NotFoundError):
        await upload.abort(aborted.upload_id)


@pytest.mark.kiwi_id(845)
async def test_null_session_errors() -> None:
    """占位异常处置：未知会话与越界分片均抛 `NotFoundError`（10002）。"""
    upload = NullMultipartUpload()
    session = await upload.initiate(_init(key="files/a.bin", size=2 * DEFAULT_PART_SIZE))

    for upload_id in ("missing", f"{NULL_UPLOAD_ID}-99"):
        with pytest.raises(NotFoundError):
            await upload.upload_part(upload_id, 1, b"x")
        with pytest.raises(NotFoundError):
            await upload.complete(upload_id)
        with pytest.raises(NotFoundError):
            await upload.abort(upload_id)

    assert session.total_parts == 2
    for part_no in (0, session.total_parts + 1):
        with pytest.raises(NotFoundError):
            await upload.upload_part(session.upload_id, part_no, b"x")


@pytest.mark.kiwi_id(845)
async def test_null_check_always_miss() -> None:
    """占位秒传判定恒定未命中（不判定、不跳过上传）。"""
    upload = NullMultipartUpload()
    assert await upload.check("a" * 64, 1024) is None


@pytest.mark.kiwi_id(845)
async def test_dependency_provider_resolves() -> None:
    """依赖解析：应用装配缺省分片上传；提供者取到同一实例；插件清单登记该能力。"""
    app = ApplicationFactory().create(None)
    async with lifespan(app), AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        assert isinstance(app.state.multipart_upload, NullMultipartUpload)
        assert resolve_plugin("multipart_upload", None) is app.state.multipart_upload
        providers = app.state.plugin_providers
        assert providers["multipart_upload"] == "null"

        resp = await client.get("/api/v1/plugins")
    assert resp.status_code == 200
    groups = resp.json()["data"]
    group = next(item for item in groups if item["plugin_key"] == "multipart_upload")
    assert group["provider"] == "null"
    assert [item["plugin_name"] for item in group["implementations"]] == ["null"]


@pytest.mark.kiwi_id(845)
async def test_placeholder_routes(client: AsyncClient) -> None:
    """占位路由：初始化 / 分片 / 合并 / 取消 / 秒传查询与异常分支。"""
    body = {"key": "files/a.bin", "size": 11 * 1024 * 1024, "sha256": "a" * 64}
    created = await client.post(f"{API}/uploads", json=body)
    assert created.status_code == 200
    session = created.json()["data"]
    assert session["part_size"] == DEFAULT_PART_SIZE
    assert session["total_parts"] == 3
    upload_id = session["upload_id"]

    part = await client.put(
        f"{API}/uploads/{upload_id}/parts/1",
        files={"data": ("part1.bin", b"hello", "application/octet-stream")},
    )
    assert part.status_code == 200
    assert part.json()["data"] == {"part_no": 1, "etag": NULL_ETAG, "size": 5}

    crossed = await client.put(
        f"{API}/uploads/{upload_id}/parts/4",
        files={"data": ("part4.bin", b"x", "application/octet-stream")},
    )
    assert crossed.status_code == 404
    assert crossed.json()["code"] == ErrorCode.NOT_FOUND

    completed = await client.post(f"{API}/uploads/{upload_id}/complete")
    assert completed.status_code == 200
    assert completed.json()["data"] == {
        "key": "files/a.bin",
        "size": 11 * 1024 * 1024,
        "content_type": None,
        "etag": NULL_ETAG,
    }

    again = await client.post(f"{API}/uploads/{upload_id}/complete")
    assert again.status_code == 404
    assert again.json()["code"] == ErrorCode.NOT_FOUND

    aborted = await client.post(f"{API}/uploads", json={"key": "files/d.bin", "size": 1024, "sha256": "d" * 64})
    delete = await client.delete(f"{API}/uploads/{aborted.json()['data']['upload_id']}")
    assert delete.status_code == 200
    assert delete.json()["data"] is None

    dedup = await client.get(f"{API}/dedup", params={"sha256": "b" * 64, "size": 1024})
    assert dedup.status_code == 200
    assert dedup.json() == {"code": 0, "message": "ok", "data": None}

    bad_sha256 = await client.get(f"{API}/dedup", params={"sha256": "ZZ", "size": 1024})
    assert bad_sha256.status_code == 200
    assert bad_sha256.json()["code"] == ErrorCode.PARAM

    bad_size = await client.get(f"{API}/dedup", params={"sha256": "b" * 64, "size": 0})
    assert bad_size.json()["code"] == ErrorCode.PARAM

    bad_body = await client.post(f"{API}/uploads", json={"key": "files/a.bin", "size": 0, "sha256": "a" * 64})
    assert bad_body.json()["code"] == ErrorCode.PARAM


class _FakeIdempotencyStore(IdempotencyStore):
    """测试用幂等存储替身（记录 `begin` / `save` 调用；可模拟重复请求返回首次会话）。"""

    def __init__(self, *, payload: IDEMPOTENCY_PAYLOAD_TYPE | None = None) -> None:
        """初始化。

        Args:
            payload: 首次会话载荷；非 None 时模拟「非首次」（`begin` 返回 False）。
        """
        self.payload = payload
        self.begun: list[str] = []
        self.saved: list[str] = []

    async def begin(self, key: str, *, ttl: int = DEFAULT_IDEMPOTENCY_TTL) -> bool:
        """记录调用并返回是否首次。

        Args:
            key: 幂等键。
            ttl: 键有效期（忽略）。

        Returns:
            bool: 首次为 True。
        """
        del ttl
        self.begun.append(key)
        return self.payload is None

    async def load(self, key: str) -> IDEMPOTENCY_PAYLOAD_TYPE | None:
        """返回首次会话载荷。

        Args:
            key: 幂等键（忽略）。

        Returns:
            IDEMPOTENCY_PAYLOAD_TYPE | None: 首次会话载荷。
        """
        del key
        return self.payload

    async def save(self, key: str, payload: IDEMPOTENCY_PAYLOAD_TYPE, *, ttl: int = DEFAULT_IDEMPOTENCY_TTL) -> None:
        """记录首次结果写入。

        Args:
            key: 幂等键。
            payload: 首次结果载荷（忽略）。
            ttl: 键有效期（忽略）。
        """
        del payload, ttl
        self.saved.append(key)


@pytest.mark.kiwi_id(845)
async def test_placeholder_route_idempotency() -> None:
    """初始化入口的幂等接线：带幂等键经幂等基座（首次写入、重复复用首次会话）。"""
    store = _FakeIdempotencyStore()
    app = ApplicationFactory().create(None)
    app.dependency_overrides[get_idempotency_store] = lambda: store
    body = {"key": "files/a.bin", "size": 1024, "sha256": "a" * 64}
    async with lifespan(app), AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        plain = await client.post(f"{API}/uploads", json=body)
        assert plain.status_code == 200
        assert store.begun == []

        first = await client.post(f"{API}/uploads", json=body, headers={IDEMPOTENCY_HEADER: "case-845"})
        assert first.status_code == 200
        assert store.begun == [build_idempotency_key(key="case-845")]
        assert store.saved == store.begun

    replay = _FakeIdempotencyStore(
        payload={"upload_id": "replayed", "key": "files/a.bin", "part_size": DEFAULT_PART_SIZE, "total_parts": 1}
    )
    app = ApplicationFactory().create(None)
    app.dependency_overrides[get_idempotency_store] = lambda: replay
    async with lifespan(app), AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        repeated = await client.post(f"{API}/uploads", json=body, headers={IDEMPOTENCY_HEADER: "case-845"})

    assert repeated.status_code == 200
    assert repeated.json()["data"]["upload_id"] == "replayed"


class _HitMultipartUpload(BaseMultipartUpload):
    """测试用分片上传替身：委托占位实现，仅覆盖秒传判定（命中）以验证命中响应映射。

    未声明 `plugin_name` → 不自动登记进插件注册表（不污染能力域实现清单）。
    """

    def __init__(self) -> None:
        """初始化（内层委托占位实现）。"""
        self._inner = NullMultipartUpload()

    async def initiate(self, init: MultipartInit) -> MultipartSession:
        """委托占位初始化。

        Args:
            init: 初始化参数对象。

        Returns:
            MultipartSession: 会话。
        """
        return await self._inner.initiate(init)

    async def upload_part(self, upload_id: str, part_no: int, data: bytes) -> MultipartPart:
        """委托占位分片上传。

        Args:
            upload_id: 会话标识。
            part_no: 分片序号。
            data: 分片内容。

        Returns:
            MultipartPart: 分片结果。
        """
        return await self._inner.upload_part(upload_id, part_no, data)

    async def complete(self, upload_id: str) -> StoredObject:
        """委托占位合并。

        Args:
            upload_id: 会话标识。

        Returns:
            StoredObject: 合并产物元数据。
        """
        return await self._inner.complete(upload_id)

    async def abort(self, upload_id: str) -> None:
        """委托占位取消。

        Args:
            upload_id: 会话标识。
        """
        await self._inner.abort(upload_id)

    async def check(self, sha256: str, size: int) -> ExistingObjectRef | None:
        """恒定命中（返回既有对象引用）。

        Args:
            sha256: 整文件 SHA256（忽略）。
            size: 文件字节数（回显）。

        Returns:
            ExistingObjectRef | None: 既有对象引用。
        """
        del sha256
        return ExistingObjectRef(
            key="files/existing.bin",
            size=size,
            content_type="application/octet-stream",
            etag="etag-hit",
            stored_at=datetime(2026, 9, 20, 8, 0, tzinfo=UTC),
        )


@pytest.mark.kiwi_id(845)
async def test_dedup_route_maps_hit() -> None:
    """秒传命中：路由把既有对象引用映射为命中响应（含对象写入时间）。"""
    app = ApplicationFactory().create(None)
    app.dependency_overrides[get_multipart_upload] = lambda: _HitMultipartUpload()
    async with lifespan(app), AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(f"{API}/dedup", params={"sha256": "c" * 64, "size": 2048})

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["key"] == "files/existing.bin"
    assert data["size"] == 2048
    assert data["content_type"] == "application/octet-stream"
    assert data["etag"] == "etag-hit"
    assert data["stored_at"].startswith("2026-09-20T08:00:00")
