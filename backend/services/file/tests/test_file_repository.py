"""文件域仓储测试（Kiwi 2374）：筛选分页 / 内容判活 / 分片覆盖写 / 批量硬删。

单库叠加口径（04-6-2）：库用共享平台库、写入走 `rollback_session`（整体回滚不残留）；
上传人主键 / 内容摘要 / 文件主键带命名空间派生，断言只落到本用例自造的行
（禁止「按状态全表计数」「分页总数 == 固定值」）。

**写路径串行（04-6-2 §13 风险 3 处置）**：分片覆盖写是「先查后写」（`upsert_part` 先 SELECT
再 INSERT/UPDATE），SQLite 下两个 worker 同时把读事务升级为写会立即 `SQLITE_BUSY`（`busy_timeout`
只对等锁生效、对升级死锁不等待）。用例统一经 `serial_db_write` 取跨进程文件锁串行——
不靠「重跑就过」，也不回退「每用例建库」。
"""

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import cast

import pytest
from sqlalchemy import Table
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.testing.namespace import Namespace
from bms_core.testing.schema import ensure_tables
from bms_core.testing.transaction import rollback_session
from bms_file.domains.file.models.file import SysFile, SysFilePart
from bms_file.domains.file.repositories.file import FilePartRepository, FileRepository

pytestmark = pytest.mark.kiwi_id(2374)

_TABLES: ConcurrentStableList[Table] = ConcurrentStableList(
    (cast("Table", SysFile.__table__), cast("Table", SysFilePart.__table__))
)
"""本文件涉及的表（幂等建表集）。"""


@pytest.fixture(autouse=True)
def _serial_db_write(serial_db_write: None) -> None:  # pyright: ignore[reportUnusedFunction]
    """整个文件串行写：本文件用例全部「先读后写」（仓储 upsert / 软删 / 批量硬删）。

    单库叠加下 SQLite 的读→写升级冲突不等待，靠 `serial_db_write` 跨进程排队。

    Args:
        serial_db_write: 共享库写路径串行夹具（工程根 / 套件 conftest 提供）。
    """


def _now() -> datetime:
    """UTC 当前时间（naive，与库列口径一致）。"""
    return datetime.now(UTC).replace(tzinfo=None)


def _uid(ns: Namespace) -> int:
    """按命名空间派生上传人主键（叠加下不与他人文件行相撞）。

    Args:
        ns: 用例命名空间。

    Returns:
        int: 上传人主键。
    """
    return int(ns.prefix[2:], 16)


def _sha(ns: Namespace, salt: str = "a") -> str:
    """按命名空间派生 64 位内容摘要（`count_live_by_content` 的判据唯一化）。

    Args:
        ns: 用例命名空间。
        salt: 同用例内的多个摘要变体。

    Returns:
        str: 64 位十六进制串。
    """
    return (salt + ns.prefix).ljust(64, "0")[:64]


@pytest.fixture
async def session(shared_platform_engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    """共享平台库上的回滚会话（文件域两张表幂等补齐）。

    Args:
        shared_platform_engine: 共享平台库引擎。

    Yields:
        AsyncSession: 回滚会话。
    """
    await ensure_tables(shared_platform_engine, list(_TABLES))
    async with rollback_session(shared_platform_engine) as current:
        yield current


async def _seed(repository: FileRepository, ns: Namespace, **overrides: object) -> SysFile:
    """写入一条代表记录（缺省：已完成的 PDF，归属本用例上传人）。"""
    values: ConcurrentStableDict[str, object] = ConcurrentStableDict(
        {
            "name": "report.pdf",
            "ext": "pdf",
            "bucket": "bms-files",
            "object_key": f"{ns.prefix}/files/2026/10/1",
            "size": 100,
            "mime_type": "application/pdf",
            "sha256": _sha(ns),
            "uploader_id": _uid(ns),
            "source": "upload",
            "status": "completed",
        }
    )
    values.update(overrides)
    return await repository.create(**values)


async def test_page_filtered_by_each_condition(session: AsyncSession, ns: Namespace) -> None:
    """筛选：上传人 / 状态 / 创建时间上下界各自收窄结果集（断言只看本用例的行）。"""
    repository = FileRepository(session)
    uploader = _uid(ns)
    now = _now()
    first = await _seed(repository, ns, name="a.pdf")
    second = await _seed(
        repository, ns, name="b.pdf", uploader_id=uploader, status="uploading", size=5, sha256=_sha(ns, "b")
    )
    await session.commit()

    by_uploader, count = await repository.page_filtered(page=1, size=10, uploader_id=uploader)
    assert {row.id for row in by_uploader} >= {first.id, second.id}
    assert count >= 2

    by_status, _status_count = await repository.page_filtered(page=1, size=10, status="uploading")
    status_ids = {row.id for row in by_status}
    assert second.id in status_ids
    assert first.id not in status_ids

    lower_bound, _ = await repository.page_filtered(
        page=1, size=10, created_from=now - timedelta(days=1), created_to=now + timedelta(days=1)
    )
    assert {first.id, second.id} <= {row.id for row in lower_bound}

    outside, _outside_count = await repository.page_filtered(
        page=1, size=10, created_from=now + timedelta(days=1), created_to=now + timedelta(days=2)
    )
    assert {first.id, second.id}.isdisjoint({row.id for row in outside})


async def test_count_live_by_content_ignores_soft_deleted(session: AsyncSession, ns: Namespace) -> None:
    """内容判活：按 `sha256 + size` 统计未软删行（回收站物理清理的交接判据）。"""
    repository = FileRepository(session)
    digest = _sha(ns)
    first = await _seed(repository, ns, object_key=ns.code("shared-key"), name="a.pdf", sha256=digest)
    await _seed(repository, ns, object_key=ns.code("shared-key"), name="b.pdf", sha256=digest)
    await session.commit()
    assert await repository.count_live_by_content(sha256=digest, size=100) == 2

    await repository.soft_delete(first.id)
    await session.commit()
    assert await repository.count_live_by_content(sha256=digest, size=100) == 1
    assert await repository.count_live_by_content(sha256=_sha(ns, "c"), size=100) == 0


async def test_upsert_part_inserts_then_overwrites(session: AsyncSession, ns: Namespace) -> None:
    """分片覆盖写：首次插入、重传同一序号改写摘要与 etag（不新增行）。"""
    parts = FilePartRepository(session)
    file_id = _uid(ns)
    created = await parts.upsert_part(file_id=file_id, part_no=1, size=5, sha256=_sha(ns), etag=ns.code("etag-1"))
    await session.commit()

    updated = await parts.upsert_part(file_id=file_id, part_no=1, size=6, sha256=_sha(ns, "b"), etag=ns.code("etag-2"))
    await session.commit()

    assert updated.id == created.id
    assert updated.sha256 == _sha(ns, "b")
    assert updated.etag == ns.code("etag-2")
    assert await parts.count_by_file(file_id) == 1


async def test_delete_by_file_removes_rows_physically(session: AsyncSession, ns: Namespace) -> None:
    """分片行只硬删：批量删除后行不留痕（唯一约束 `(file_id, part_no)` 可复用）。"""
    parts = FilePartRepository(session)
    file_id = _uid(ns) + 1
    await parts.upsert_part(file_id=file_id, part_no=1, size=5, sha256=_sha(ns), etag="e1")
    await parts.upsert_part(file_id=file_id, part_no=2, size=5, sha256=_sha(ns, "b"), etag="e2")
    await session.commit()

    assert await parts.delete_by_file(file_id) == 2
    await session.commit()
    assert await parts.list_by_file(file_id) == []
