"""文件域仓储测试（Kiwi 2374）：筛选分页 / 内容判活 / 分片覆盖写 / 批量硬删。

口径：真 SQLite 会话（只建 `sys_file` / `sys_file_part` 两张表），不连租户库。
"""

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast

import pytest
from sqlalchemy import Table
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from bms_core.core.concurrent import ConcurrentStableDict
from bms_file.domains.file.models.file import SysFile, SysFilePart
from bms_file.domains.file.repositories.file import FilePartRepository, FileRepository

pytestmark = pytest.mark.kiwi_id(2374)


def _now() -> datetime:
    """UTC 当前时间（naive，与库列口径一致）。"""
    return datetime.now(UTC).replace(tzinfo=None)


@pytest.fixture
async def session(tmp_path: Path) -> AsyncIterator[AsyncSession]:
    """SQLite 真库会话：仅建文件域两张表。

    Args:
        tmp_path: 用例临时目录。

    Yields:
        AsyncSession: 会话。
    """
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'file_repo.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(cast("Table", SysFile.__table__).create)
        await connection.run_sync(cast("Table", SysFilePart.__table__).create)
    factory: async_sessionmaker[AsyncSession] = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as current:
        yield current
    await engine.dispose()


async def _seed(repository: FileRepository, **overrides: object) -> SysFile:
    """写入一条代表记录（缺省：已完成的 PDF）。"""
    values: ConcurrentStableDict[str, object] = ConcurrentStableDict(
        {
            "name": "report.pdf",
            "ext": "pdf",
            "bucket": "bms-files",
            "object_key": "demo/files/2026/10/1",
            "size": 100,
            "mime_type": "application/pdf",
            "sha256": "a" * 64,
            "uploader_id": 1001,
            "source": "upload",
            "status": "completed",
        }
    )
    values.update(overrides)
    return await repository.create(**values)


async def test_page_filtered_by_each_condition(session: AsyncSession) -> None:
    """筛选：上传人 / 状态 / 创建时间上下界各自收窄结果集（分页总数同步）。"""
    repository = FileRepository(session)
    now = _now()
    await _seed(repository, name="a.pdf", uploader_id=1001)
    await _seed(repository, name="b.pdf", uploader_id=1002, status="uploading", size=5, sha256="b" * 64)
    await session.commit()

    by_uploader, count = await repository.page_filtered(page=1, size=10, uploader_id=1001)
    assert count == 1
    assert [row.name for row in by_uploader] == ["a.pdf"]

    by_status, status_count = await repository.page_filtered(page=1, size=10, status="uploading")
    assert status_count == 1
    assert [row.name for row in by_status] == ["b.pdf"]

    lower_bound, _ = await repository.page_filtered(
        page=1, size=10, created_from=now - timedelta(days=1), created_to=now + timedelta(days=1)
    )
    assert len(lower_bound) == 2

    outside, outside_count = await repository.page_filtered(
        page=1, size=10, created_from=now + timedelta(days=1), created_to=now + timedelta(days=2)
    )
    assert outside_count == 0
    assert not outside


async def test_count_live_by_content_ignores_soft_deleted(session: AsyncSession) -> None:
    """内容判活：按 `sha256 + size` 统计未软删行（回收站物理清理的交接判据）。"""
    repository = FileRepository(session)
    first = await _seed(repository, object_key="shared/key", name="a.pdf")
    await _seed(repository, object_key="shared/key", name="b.pdf")
    await session.commit()
    assert await repository.count_live_by_content(sha256="a" * 64, size=100) == 2

    await repository.soft_delete(first.id)
    await session.commit()
    assert await repository.count_live_by_content(sha256="a" * 64, size=100) == 1
    assert await repository.count_live_by_content(sha256="c" * 64, size=100) == 0


async def test_upsert_part_inserts_then_overwrites(session: AsyncSession) -> None:
    """分片覆盖写：首次插入、重传同一序号改写摘要与 etag（不新增行）。"""
    parts = FilePartRepository(session)
    created = await parts.upsert_part(file_id=11, part_no=1, size=5, sha256="a" * 64, etag="etag-1")
    await session.commit()

    updated = await parts.upsert_part(file_id=11, part_no=1, size=6, sha256="b" * 64, etag="etag-2")
    await session.commit()

    assert updated.id == created.id
    assert updated.sha256 == "b" * 64
    assert updated.etag == "etag-2"
    assert await parts.count_by_file(11) == 1


async def test_delete_by_file_removes_rows_physically(session: AsyncSession) -> None:
    """分片行只硬删：批量删除后行不留痕（唯一约束 `(file_id, part_no)` 可复用）。"""
    parts = FilePartRepository(session)
    await parts.upsert_part(file_id=12, part_no=1, size=5, sha256="a" * 64, etag="e1")
    await parts.upsert_part(file_id=12, part_no=2, size=5, sha256="b" * 64, etag="e2")
    await session.commit()

    assert await parts.delete_by_file(12) == 2
    await session.commit()
    assert await parts.list_by_file(12) == []
