"""分片上传与秒传契约测试（Kiwi 845）。

覆盖：契约与标识 / 数据契约与常量 / 占位会话语义 / 异常处置 / 依赖解析 / 占位路由与幂等接线。
"""

import pytest
from pydantic import ValidationError

from bms_core.application import service_lifespan as lifespan
from bms_core.core.capability import BaseCapability, BaseNullObject
from bms_core.core.exceptions import NotFoundError
from bms_core.core.plugin import BasePluggable, resolve_plugin
from bms_core.storage.base import (
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
from bms_core.storage.multipart_local import LocalMultipartUpload
from bms_core.storage.null import NullMultipartUpload
from bms_file.main import ApplicationFactory

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
    """依赖解析：应用按 `[multipart_upload].provider` 装配真实分片实现；提供者取到同一实例。"""
    app = ApplicationFactory().create(None)
    async with lifespan(app):
        assert isinstance(app.state.multipart_upload, LocalMultipartUpload)
        assert resolve_plugin("multipart_upload", "local") is app.state.multipart_upload
        providers = app.state.plugin_providers
        assert providers["multipart_upload"] == "local"
