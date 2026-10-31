"""文件域服务单元测试（Kiwi 2374）：参数缓存 / 预签名回落 / 无审计与无指标 / 取消与孤儿分支。

与接口用例的分工：这里直接构造 `FileService`，覆盖**接口路径走不到**的分支
（审计 / 指标为空、请求有效期非正、无 `upload_id` 的遗留记录、会话快照已丢失）。
"""

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

import pytest
from file_fixtures import PDF_BYTES, StubConfigSource, StubQuotaClient

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.db.unit_of_work import DbUnitOfWork
from bms_core.outbox.base import BaseOutboxStore
from bms_core.storage.local import LocalObjectStorage
from bms_core.storage.multipart_local import LocalMultipartUpload
from bms_core.tenant_module.quota import TenantQuotaClient
from bms_file.domains.file.limits import FileLimits
from bms_file.domains.file.models.file import SysFile, SysFilePart
from bms_file.domains.file.repositories.file import FileRepository
from bms_file.domains.file.rules import object_key_for
from bms_file.domains.file.services.file import FileService

pytestmark = pytest.mark.kiwi_id(2374)


def _now() -> datetime:
    """UTC 当前时间（naive，与库列口径一致）。"""
    return datetime.now(UTC).replace(tzinfo=None)


class _RecordingOutbox:
    """发件箱替身（只实现 `enqueue`：单元测试不需要真表与投递面）。"""

    def __init__(self) -> None:
        self.events: ConcurrentStableList[str] = ConcurrentStableList()

    async def enqueue(self, session: Any, event: Any) -> str:
        """记录事件类型。"""
        del session
        self.events.add(cast("str", event.event_type))
        return f"evt-{len(self.events)}"


class _Harness:
    """单元测试装配：真 SQLite 会话 + 临时目录对象存储 + 替身配额 / 参数 / 发件箱。"""

    def __init__(self, session: Any, service: FileService, files: FileRepository, root: Path) -> None:
        self.session = session
        self.service = service
        self.files = files
        self.root = root


@pytest.fixture
async def harness(tmp_path: Path) -> AsyncIterator[_Harness]:
    """构造服务实例（审计 / 指标为 None：覆盖「无捕获器」分支）。

    Args:
        tmp_path: 用例临时目录。

    Yields:
        _Harness: 装配结果。
    """
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'unit.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(cast("Any", SysFile.__table__).create)
        await connection.run_sync(cast("Any", SysFilePart.__table__).create)
    factory: async_sessionmaker[AsyncSession] = async_sessionmaker(engine, expire_on_commit=False)
    root = tmp_path / "objects"
    async with factory() as session:
        service = FileService(
            uow=DbUnitOfWork(cast("Any", session)),
            storage=LocalObjectStorage(root=root),
            multipart=LocalMultipartUpload(root=root),
            config=StubConfigSource(),
            quota=TenantQuotaClient(StubQuotaClient(), tenant_id="1001", tenant_code="demo"),
            outbox=cast("BaseOutboxStore", _RecordingOutbox()),
            audit=None,
            metrics=None,
        )
        yield _Harness(session, service, FileRepository(session), root)
    await engine.dispose()


async def _seed_completed(files: FileRepository, root: Path) -> SysFile:
    """写入一条已完成记录并把对象落到本地存储。"""
    file_id = 424242
    key = object_key_for(tenant="demo", file_id=file_id)
    target = root / key
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(PDF_BYTES)
    return await files.create_with_id(
        file_id,
        name="report.pdf",
        ext="pdf",
        bucket="bms-files",
        object_key=key,
        size=len(PDF_BYTES),
        mime_type="application/pdf",
        sha256="a" * 64,
        uploader_id=1001,
        source="upload",
        status="completed",
    )


async def test_limits_are_cached_per_service(harness: _Harness) -> None:
    """参数只在首次访问时加载，之后复用同一份快照（请求内一致）。"""
    first = await harness.service.limits()
    second = await harness.service.limits()

    assert first is second
    assert first.max_upload_size == 20 * 1024 * 1024


async def test_presign_falls_back_when_requested_ttl_not_positive(harness: _Harness) -> None:
    """请求有效期非正（如 0）：回落到参数上限（不产生零期地址）。"""
    row = await _seed_completed(harness.files, harness.root)
    await harness.session.commit()
    harness.service._limits = FileLimits(presign_ttl=30)  # pyright: ignore[reportPrivateUsage]

    result = await harness.service.presign(file_id=row.id, expires_in=0)

    assert result.expires_in == 30


async def test_upload_without_audit_still_completes(harness: _Harness) -> None:
    """未接入审计捕获器时上传照常完成（审计落库归 06；此处只跳过事件）。"""
    row = await harness.service.upload(name="report.pdf", data=PDF_BYTES)

    assert row.status == "completed"
    assert row.sha256
    assert (harness.root / row.object_key).is_file()


async def test_warn_quota_without_metrics_is_safe(harness: _Harness) -> None:
    """未接入指标时配额告警只落日志（不因缺 recorder 抛错）。"""
    await harness.service._warn_quota(1024)  # pyright: ignore[reportPrivateUsage]


async def test_discard_without_upload_id_marks_failed(harness: _Harness) -> None:
    """遗留记录无会话标识：取消只清分片行并置失败（不去中止不存在的会话）。"""
    row = await harness.files.create(
        name="half.pdf",
        ext="pdf",
        bucket="bms-files",
        object_key="demo/files/2026/10/legacy",
        size=10,
        mime_type="application/pdf",
        sha256="b" * 64,
        source="upload",
        status="uploading",
        upload_id=None,
    )
    await harness.session.commit()

    await harness.service._discard(row, "用户取消上传")  # pyright: ignore[reportPrivateUsage]
    await harness.session.commit()

    assert row.status == "failed"
    assert row.remark == "用户取消上传"


async def test_discard_tolerates_lost_session_snapshot(harness: _Harness) -> None:
    """会话快照已丢失（Redis 过期）：取消仍能落失败态（只记告警）。"""
    row = await harness.files.create(
        name="half.pdf",
        ext="pdf",
        bucket="bms-files",
        object_key="demo/files/2026/10/lost",
        size=10,
        mime_type="application/pdf",
        sha256="c" * 64,
        source="upload",
        status="uploading",
        upload_id="gone-session",
        total_parts=2,
        part_size=5,
        expires_at=_now() + timedelta(hours=1),
    )
    await harness.session.commit()

    await harness.service._discard(row, "用户取消上传")  # pyright: ignore[reportPrivateUsage]
    await harness.session.commit()

    assert row.status == "failed"


async def test_orphan_cleanup_handles_row_without_upload_id(harness: _Harness) -> None:
    """超期记录无会话标识：跳过会话中止，仍清分片行、置 `orphan` 并发事件。"""
    expired = await harness.files.create(
        name="stale.pdf",
        ext="pdf",
        bucket="bms-files",
        object_key="demo/files/2026/10/stale",
        size=10,
        mime_type="application/pdf",
        sha256="d" * 64,
        source="upload",
        status="uploading",
        upload_id=None,
        total_parts=2,
        part_size=5,
        expires_at=_now() - timedelta(hours=1),
    )
    await harness.session.commit()

    result = await harness.service.cleanup_orphans()

    await harness.session.refresh(expired)
    assert result.scanned >= 1
    assert result.orphaned >= 1
    assert expired.status == "orphan"
    assert expired.remark == "超期未完成，已回收"
