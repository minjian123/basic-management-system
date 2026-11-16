"""归档查询与销毁：租户隔离、时间窗、下载与二次确认。"""

# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false, reportUnknownParameterType=false, reportMissingParameterType=false, reportAttributeAccessIssue=false, reportArgumentType=false, reportCallIssue=false, reportIndexIssue=false, reportGeneralTypeIssues=false, reportUnknownLambdaType=false, reportIncompatibleMethodOverride=false, reportDeprecated=false

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from bms_core.core.config import get_settings
from bms_core.core.context import set_current_tenant_id
from bms_core.core.exceptions import (
    ArchiveDataNotFoundError,
    ArchiveDestroyConfirmRequiredError,
    ArchiveQueryRangeExceededError,
    ParamError,
)
from bms_core.models.platform.archive import (
    ARCHIVE_LOG_STATUS_SUCCESS,
    ARCHIVE_TARGET_MINIO,
    SysArchiveLog,
    SysArchiveRecord,
)
from bms_platform.domains.archive.schemas.archive import ArchiveDataQuery
from bms_platform.domains.archive.services.dispose import ArchiveDisposeService
from bms_platform.domains.archive.services.query import ArchiveQueryService
from tests.archive.helpers import FakeStorage, new_pair, utc

pytestmark = pytest.mark.kiwi_id(2516)


@pytest.fixture
async def pair(tmp_path: Path) -> AsyncIterator[tuple[AsyncSession, AsyncSession, AsyncEngine, AsyncEngine]]:
    """平台库 / 归档库双会话。"""
    platform_session, archive_session, platform_engine, archive_engine = await new_pair(tmp_path)
    try:
        yield platform_session, archive_session, platform_engine, archive_engine
    finally:
        await platform_session.close()
        await archive_session.close()
        await platform_engine.dispose()
        await archive_engine.dispose()


async def _seed_records(archive: AsyncSession) -> None:
    archive.add_all(
        [
            SysArchiveRecord(
                tenant_id=42,
                source_table="sys_operation_log",
                source_id="1",
                source_month="202601",
                policy_id=1,
                batch_id=1,
                payload='{"id": "1", "tenant_id": 42, "action": "login"}',
                archived_at=utc(2026, 2),
            ),
            SysArchiveRecord(
                tenant_id=77,
                source_table="sys_operation_log",
                source_id="2",
                source_month="202601",
                policy_id=1,
                batch_id=1,
                payload='{"id": "2", "tenant_id": 77, "action": "logout"}',
                archived_at=utc(2026, 3),
            ),
        ]
    )
    await archive.commit()


async def test_query_tenant_isolation(pair) -> None:
    """普通用户强制本租户；审计管理员可跨租户；payload 可反序列化。"""
    platform, archive, _, _ = pair
    await _seed_records(archive)
    service = ArchiveQueryService(platform, archive, settings=get_settings(), storage=FakeStorage())

    token = set_current_tenant_id("42")
    try:
        rows, total = await service.query_data(
            ArchiveDataQuery(source_table="sys_operation_log", stored_from=utc(2026, 1), stored_to=utc(2026, 12)),
            page=1,
            size=10,
            allow_cross_tenant=False,
        )
        assert total == 1
        assert rows[0].tenant_id == 42
        assert service.decode(rows[0])["action"] == "login"
    finally:
        set_current_tenant_id(token)

    all_rows, all_total = await service.query_data(
        ArchiveDataQuery(source_table="sys_operation_log", stored_from=utc(2026, 1), stored_to=utc(2026, 12)),
        page=1,
        size=10,
        allow_cross_tenant=True,
    )
    assert all_total == 2
    assert len(all_rows) == 2


async def test_query_window_and_errors(pair) -> None:
    """时间窗缺省 / 超限 / 逆序 / 缺租户上下文。"""
    platform, archive, _, _ = pair
    await _seed_records(archive)
    service = ArchiveQueryService(platform, archive, settings=get_settings(), storage=FakeStorage())
    rows, total = await service.query_data(
        ArchiveDataQuery(stored_from=utc(2026, 1), stored_to=utc(2026, 12)),
        page=1,
        size=10,
        allow_cross_tenant=True,
    )
    assert total == 2
    assert rows
    default_rows, default_total = await service.query_data(ArchiveDataQuery(), page=1, size=10, allow_cross_tenant=True)
    assert default_total == 0
    assert default_rows == []

    with pytest.raises(ArchiveQueryRangeExceededError):
        await service.query_data(
            ArchiveDataQuery(stored_from=utc(2024, 1), stored_to=utc(2026, 8)),
            page=1,
            size=10,
            allow_cross_tenant=True,
        )
    with pytest.raises(ParamError):
        await service.query_data(
            ArchiveDataQuery(stored_from=utc(2026, 5), stored_to=utc(2026, 1)),
            page=1,
            size=10,
            allow_cross_tenant=True,
        )
    token = set_current_tenant_id(None)
    try:
        with pytest.raises(ParamError):
            await service.query_data(ArchiveDataQuery(), page=1, size=10, allow_cross_tenant=False)
    finally:
        set_current_tenant_id(token)


async def test_download_and_destroy(pair) -> None:
    """冷化文件下载 / 批次销毁 / 单条归档行销毁与二次确认。"""
    platform, archive, _, _ = pair
    await _seed_records(archive)
    storage = FakeStorage()
    storage.objects["archive/42/sys_operation_log/202601/1.ndjson.gz"] = b"data"
    platform.add(
        SysArchiveLog(
            policy_id=1,
            table_name="sys_operation_log",
            batch_key="b1",
            target=ARCHIVE_TARGET_MINIO,
            tenant_id=42,
            archived_count=1,
            file_key="archive/42/sys_operation_log/202601/1.ndjson.gz",
            status=ARCHIVE_LOG_STATUS_SUCCESS,
            started_at=utc(2026, 2),
            retention_until=utc(2027, 2),
        )
    )
    await platform.commit()
    query = ArchiveQueryService(platform, archive, settings=get_settings(), storage=storage)
    log = (await platform.execute(select(SysArchiveLog))).scalars().first()
    assert log is not None
    download = await query.download(int(log.id))
    assert download.url.startswith("https://fake/")

    dispose = ArchiveDisposeService(platform, archive, storage=storage, clock=utc(2026, 6, 1))
    with pytest.raises(ArchiveDestroyConfirmRequiredError):
        await dispose.destroy_log(int(log.id), confirm=False, operator_id=None)
    record = await dispose.destroy_log(int(log.id), confirm=True, operator_id=42)
    assert record.target == "destroy"
    assert storage.objects == {}
    with pytest.raises(ArchiveDataNotFoundError):
        await query.download(int(log.id))

    with pytest.raises(ArchiveDestroyConfirmRequiredError):
        await dispose.destroy_record(source_table="sys_operation_log", source_id="1", confirm=False, operator_id=42)
    destroy = await dispose.destroy_record(
        source_table="sys_operation_log", source_id="1", confirm=True, operator_id=42
    )
    assert destroy.target == "destroy"
    remaining = (await archive.execute(select(SysArchiveRecord))).scalars().all()
    assert [row.source_id for row in remaining] == ["2"]
    with pytest.raises(ArchiveDataNotFoundError):
        await dispose.destroy_record(source_table="sys_operation_log", source_id="1", confirm=True, operator_id=42)


async def test_log_list_detail_and_missing(pair) -> None:
    """执行记录列表 / 详情 / 不存在。"""
    platform, archive, _, _ = pair
    platform.add(
        SysArchiveLog(
            policy_id=1,
            table_name="sys_table_ownership",
            batch_key="b2",
            target="archive_db",
            status=ARCHIVE_LOG_STATUS_SUCCESS,
            started_at=utc(2026, 2),
        )
    )
    await platform.commit()
    service = ArchiveQueryService(platform, archive, settings=get_settings(), storage=FakeStorage())
    rows, total = await service.list_logs(page=1, size=10, target="archive_db", status="success")
    assert total == 1
    assert len(rows) == 1
    detail = await service.get_log(int(rows[0].id))
    assert detail.table_name == "sys_table_ownership"
    with pytest.raises(ArchiveDataNotFoundError):
        await service.get_log(999)
