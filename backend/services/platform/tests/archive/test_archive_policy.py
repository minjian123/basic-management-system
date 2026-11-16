"""归档策略：校验、CRUD 与执行中互斥。"""

# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false, reportUnknownParameterType=false, reportMissingParameterType=false, reportAttributeAccessIssue=false, reportArgumentType=false, reportCallIssue=false, reportIndexIssue=false, reportGeneralTypeIssues=false, reportUnknownLambdaType=false, reportIncompatibleMethodOverride=false, reportDeprecated=false

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bms_core.core.config import get_settings
from bms_core.core.exceptions import (
    ArchiveBatchFailedError,
    ArchiveChainIncompleteError,
    ArchiveDataNotFoundError,
    ArchiveDestroyConfirmRequiredError,
    ArchivePolicyDisabledError,
    ArchivePolicyDuplicateError,
    ArchivePolicyRunningError,
    ArchiveQueryRangeExceededError,
    ConcurrentConflictError,
    ParamError,
)
from bms_core.models.platform.archive import (
    ARCHIVE_LOG_STATUS_RUNNING,
    ARCHIVE_LOG_STATUS_SKIPPED,
    SysArchiveLog,
)
from bms_platform.domains.archive.schemas.archive import (
    ArchivePolicyCreateRequest,
    ArchivePolicyUpdateRequest,
)
from bms_platform.domains.archive.services.policy import ArchivePolicyService
from tests.archive.helpers import new_pair, utc

pytestmark = pytest.mark.kiwi_id(2516)


def test_archive_error_classes_carry_codes() -> None:
    """归档错误码：每个异常类携带稳定错误码与 HTTP 状态。"""
    cases = (
        (ArchivePolicyDuplicateError(), 93001, 409),
        (ArchivePolicyRunningError(), 93002, 409),
        (ArchiveChainIncompleteError(), 93003, 409),
        (ArchiveBatchFailedError(), 93004, 500),
        (ArchiveDataNotFoundError(), 93005, 404),
        (ArchiveDestroyConfirmRequiredError(), 93006, 400),
        (ArchivePolicyDisabledError(), 93007, 409),
        (ArchiveQueryRangeExceededError(), 93008, 400),
    )
    for exc, code, status in cases:
        assert exc.code == code
        assert exc.http_status == status


@pytest.fixture
async def sessions(tmp_path: Path) -> AsyncIterator[AsyncSession]:
    """平台库会话（附带归档库用于建表）。"""
    platform_session, archive_session, platform_engine, archive_engine = await new_pair(tmp_path)
    try:
        yield platform_session
    finally:
        await platform_session.close()
        await archive_session.close()
        await platform_engine.dispose()
        await archive_engine.dispose()


async def _service(session: AsyncSession) -> ArchivePolicyService:
    return ArchivePolicyService(session, get_settings())


def _request(**overrides: object) -> ArchivePolicyCreateRequest:
    data = {
        "table_name": "sys_table_ownership",
        "time_field": "created_at",
        "threshold_days": 30,
        "retention_days": 10,
        "target": "archive_db",
        "batch_size": 10,
        "status": "enabled",
        "require_chain": False,
        "remark": "测试",
    }
    data.update(overrides)
    return ArchivePolicyCreateRequest(**data)


async def test_create_and_validate(sessions: AsyncSession) -> None:
    """新增策略：正常 / 重复 / 非平台表 / 非时间字段 / 审计表约束。"""
    service = await _service(sessions)
    policy = await service.create(_request())
    assert policy.table_name == "sys_table_ownership"
    assert policy.status == "enabled"

    with pytest.raises(ArchivePolicyDuplicateError):
        await service.create(_request())

    with pytest.raises(ParamError):
        await service.create(_request(table_name="sys_task"))
    with pytest.raises(ParamError):
        await service.create(_request(table_name="not_exists"))
    with pytest.raises(ParamError):
        await service.create(_request(time_field="owner"))
    with pytest.raises(ParamError):
        await service.create(_request(time_field="not_exists"))
    with pytest.raises(ParamError):
        await service.create(_request(batch_size=100000))
    with pytest.raises(ParamError):
        await service.create(_request(target="s3"))

    with pytest.raises(ParamError):
        await service.create(
            _request(
                table_name="sys_operation_log",
                time_field="occurred_at",
                target="minio",
                require_chain=True,
            )
        )
    with pytest.raises(ParamError):
        await service.create(
            _request(
                table_name="sys_operation_log",
                time_field="created_at",
                target="archive_db",
                require_chain=True,
            )
        )
    with pytest.raises(ParamError):
        await service.create(
            _request(
                table_name="sys_operation_log",
                time_field="occurred_at",
                target="archive_db",
                require_chain=False,
            )
        )


async def test_update_and_delete_guards(sessions: AsyncSession) -> None:
    """修改 / 删除：版本冲突、执行中、仅停用可删。"""
    service = await _service(sessions)
    policy = await service.create(_request())
    updated = await service.update(
        int(policy.id),
        ArchivePolicyUpdateRequest(status="disabled", threshold_days=5, version=policy.version),
    )
    assert updated.status == "disabled"
    assert updated.threshold_days == 5

    with pytest.raises(ConcurrentConflictError):
        await service.update(
            int(policy.id),
            ArchivePolicyUpdateRequest(status="enabled", version=policy.version - 1),
        )
    with pytest.raises(ParamError):
        await service.update(
            int(policy.id),
            ArchivePolicyUpdateRequest(status="bad", version=policy.version),
        )
    with pytest.raises(ParamError):
        await service.update(
            int(policy.id),
            ArchivePolicyUpdateRequest(time_field="owner", version=policy.version),
        )

    sessions.add(
        SysArchiveLog(
            policy_id=int(policy.id),
            table_name=policy.table_name,
            batch_key="k",
            target="archive_db",
            status=ARCHIVE_LOG_STATUS_RUNNING,
            started_at=utc(2026, 1),
        )
    )
    await sessions.commit()
    with pytest.raises(ArchivePolicyRunningError):
        await service.update(int(policy.id), ArchivePolicyUpdateRequest(remark="x", version=policy.version))
    with pytest.raises(ArchivePolicyRunningError):
        await service.delete(int(policy.id))

    running = (await sessions.execute(select(SysArchiveLog).where(SysArchiveLog.batch_key == "k"))).scalar_one()
    running.status = ARCHIVE_LOG_STATUS_SKIPPED
    await sessions.commit()

    await service.delete(int(policy.id))
    with pytest.raises(ArchiveDataNotFoundError):
        await service.delete(int(policy.id))


async def test_list_and_missing(sessions: AsyncSession) -> None:
    """列表筛选与不存在策略。"""
    service = await _service(sessions)
    await service.create(_request())
    meta, rows = await service.list(page=1, size=10, table_name="sys_table_ownership", status="enabled")
    assert int(str(meta["total"])) == 1
    assert len(rows) == 1
    with pytest.raises(ArchiveDataNotFoundError):
        await service.update(999, ArchivePolicyUpdateRequest(version=1))
