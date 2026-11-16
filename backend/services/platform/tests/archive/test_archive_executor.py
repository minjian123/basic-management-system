"""归档执行器：普通表两段式、直冷、审计分片整月归档与链尾、清理。"""

# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false, reportUnknownParameterType=false, reportMissingParameterType=false, reportAttributeAccessIssue=false, reportArgumentType=false, reportCallIssue=false, reportIndexIssue=false, reportGeneralTypeIssues=false, reportUnknownLambdaType=false, reportIncompatibleMethodOverride=false, reportDeprecated=false

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from bms_core.audit.sha256 import Sha256HashChain
from bms_core.audit.shards import build_shard_table
from bms_core.audit.verifier import AuditChainVerifier
from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.config import get_settings
from bms_core.lock.null import NullDistributedLock
from bms_core.models.platform.archive import (
    ARCHIVE_LOG_STATUS_SUCCESS,
    ARCHIVE_TARGET_MINIO,
    SysArchiveChainTail,
    SysArchiveLog,
    SysArchiveRecord,
)
from bms_core.models.platform.log import SysAuditShard
from bms_platform.domains.archive.schemas.archive import ArchivePolicyCreateRequest
from bms_platform.domains.archive.services.executor import ArchiveExecutor
from bms_platform.domains.archive.services.policy import ArchivePolicyService
from tests.archive.helpers import FakeStorage, new_pair, seed_chain_rows, seed_ownership, utc

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


async def _executor(
    platform: AsyncSession,
    archive: AsyncSession,
    *,
    storage: FakeStorage,
    clock,
) -> ArchiveExecutor:
    return ArchiveExecutor(
        platform,
        archive,
        settings=get_settings(),
        storage=storage,
        chain=Sha256HashChain(),
        lock=NullDistributedLock(),
        clock=clock,
    )


async def _create_policy(
    session: AsyncSession,
    *,
    table_name: str = "sys_table_ownership",
    time_field: str = "created_at",
    target: str = "archive_db",
    threshold_days: int = 30,
    retention_days: int = 0,
    require_chain: bool = False,
) -> int:
    service = ArchivePolicyService(session, get_settings())
    policy = await service.create(
        ArchivePolicyCreateRequest(
            table_name=table_name,
            time_field=time_field,
            threshold_days=threshold_days,
            retention_days=retention_days,
            target=target,
            batch_size=10,
            require_chain=require_chain,
        )
    )
    await session.commit()
    return int(policy.id)


async def test_normal_table_two_stage(pair) -> None:
    """普通表：到期迁归档库 + 满保留期冷化，热表行删除、文件与记录齐备。"""
    platform, archive, _, _ = pair
    await seed_ownership(platform, created_at=utc(2026, 1, 1))
    policy_id = await _create_policy(platform, retention_days=0)
    storage = FakeStorage()
    executor = await _executor(platform, archive, storage=storage, clock=lambda: utc(2026, 6, 1))
    summary = await executor.run(policy_ids=ConcurrentStableList((policy_id,)))
    assert summary["archived"] == 1
    assert summary["cold"] == 1

    assert (await archive.execute(select(SysArchiveRecord))).scalars().all() == []
    assert len(storage.objects) == 2  # 数据 + 清单
    logs = (await platform.execute(select(SysArchiveLog).order_by(SysArchiveLog.started_at))).scalars().all()
    assert {log.target for log in logs} == {"archive_db", "minio"}
    assert all(log.status == ARCHIVE_LOG_STATUS_SUCCESS for log in logs)
    assert any(log.retention_until is not None for log in logs)

    # 重复执行：无到期数据，不再新增归档行
    again = await executor.run(policy_ids=ConcurrentStableList((policy_id,)))
    assert again["archived"] == 0


async def test_direct_cold(pair) -> None:
    """直冷：热表直接导出对象存储，不写归档库。"""
    platform, archive, _, _ = pair
    await seed_ownership(platform, created_at=utc(2026, 1, 1))
    policy_id = await _create_policy(platform, target="minio", threshold_days=30)
    storage = FakeStorage()
    executor = await _executor(platform, archive, storage=storage, clock=lambda: utc(2026, 6, 1))
    summary = await executor.run(policy_ids=ConcurrentStableList((policy_id,)))
    assert summary["cold"] == 1
    assert (await archive.execute(select(SysArchiveRecord))).scalars().all() == []
    assert len(storage.objects) == 2


async def test_audit_shard_archive_and_cross_verified(pair) -> None:
    """审计分片：链校验 → 整月迁出 → 写链尾 → 删表；后续月份经链尾校验通过。"""
    platform, archive, _, _ = pair
    march_tail = await seed_chain_rows(
        platform, log_type="operation", month="202603", tenant_id=42, count=2, starting_prev="0" * 64
    )
    await seed_chain_rows(
        platform,
        log_type="operation",
        month="202605",
        tenant_id=42,
        count=1,
        starting_prev=march_tail,
    )
    platform.add_all(
        [
            SysAuditShard(log_type="operation", shard_month="202603", physical_table="sys_operation_log_202603"),
            SysAuditShard(log_type="operation", shard_month="202605", physical_table="sys_operation_log_202605"),
        ]
    )
    await platform.commit()
    policy_id = await _create_policy(
        platform,
        table_name="sys_operation_log",
        time_field="occurred_at",
        threshold_days=15,
        retention_days=180,
        require_chain=True,
    )
    storage = FakeStorage()
    executor = await _executor(platform, archive, storage=storage, clock=lambda: utc(2026, 6, 1))
    summary = await executor.run(policy_ids=ConcurrentStableList((policy_id,)))
    assert summary["archived"] == 2

    records = (await archive.execute(select(SysArchiveRecord))).scalars().all()
    assert {row.source_month for row in records} == {"202603"}
    tail = (
        await platform.execute(select(SysArchiveChainTail).where(SysArchiveChainTail.shard_month == "202603"))
    ).scalar_one()
    assert tail.tenant_key == "42"
    assert tail.record_count == 2
    ledger = (await platform.execute(select(SysAuditShard).order_by(SysAuditShard.shard_month))).scalars().all()
    assert [(row.shard_month, row.status) for row in ledger] == [("202603", "archived"), ("202605", "active")]

    verified = await AuditChainVerifier(platform, Sha256HashChain()).verify("operation", None)
    assert verified.valid is True

    tail.last_record_hash = "f" * 64
    await platform.commit()
    broken = await AuditChainVerifier(platform, Sha256HashChain()).verify("operation", None)
    assert broken.valid is False
    assert broken.broken_month == "202605"


async def test_chain_broken_aborts(pair) -> None:
    """链不完整：中止归档、不删表、写失败记录。"""
    platform, archive, _, _ = pair
    await seed_chain_rows(platform, log_type="operation", month="202603", tenant_id=42, count=2, starting_prev="0" * 64)
    platform.add(SysAuditShard(log_type="operation", shard_month="202603", physical_table="sys_operation_log_202603"))
    await platform.commit()
    table = build_shard_table("operation", "sys_operation_log_202603")
    await platform.execute(update(table).where(table.c.id == int("2026030001")).values(record_hash="bad"))
    await platform.commit()
    policy_id = await _create_policy(
        platform,
        table_name="sys_operation_log",
        time_field="occurred_at",
        threshold_days=15,
        retention_days=180,
        require_chain=True,
    )
    executor = await _executor(platform, archive, storage=FakeStorage(), clock=lambda: utc(2026, 6, 1))
    summary = await executor.run(policy_ids=ConcurrentStableList((policy_id,)))
    assert summary["failed"] == 1
    ledger = (await platform.execute(select(SysAuditShard))).scalar_one()
    assert ledger.status == "active"
    assert (await archive.execute(select(SysArchiveRecord))).scalars().all() == []
    log = (await platform.execute(select(SysArchiveLog))).scalar_one()
    assert log.status == "failed"
    assert "month=202603" in (log.error_msg or "")


async def test_cleanup_disposes_expired_files(pair) -> None:
    """清理：到期冷化文件（数据 + 清单）删除并回写处置。"""
    platform, archive, _, _ = pair
    storage = FakeStorage()
    storage.objects["archive/42/sys_table_ownership/202601/1.ndjson.gz"] = b"data"
    storage.objects["archive/42/sys_table_ownership/202601/1.ndjson.gz.manifest.json"] = b"{}"
    platform.add(
        SysArchiveLog(
            policy_id=1,
            table_name="sys_table_ownership",
            batch_key="cleanup:1",
            target=ARCHIVE_TARGET_MINIO,
            archived_count=1,
            file_key="archive/42/sys_table_ownership/202601/1.ndjson.gz",
            status=ARCHIVE_LOG_STATUS_SUCCESS,
            started_at=utc(2026, 1),
            retention_until=utc(2026, 2),
        )
    )
    await platform.commit()
    executor = await _executor(platform, archive, storage=storage, clock=lambda: utc(2026, 6, 1))
    assert await executor.cleanup() == 1
    assert storage.objects == {}
    log = (await platform.execute(select(SysArchiveLog))).scalar_one()
    assert log.disposed_at is not None
    assert log.dispose_type == "cleanup"
    assert await executor.cleanup() == 0


async def test_verifier_reads_earlier_active_month(pair) -> None:
    """校验第二个活跃月份时向前扫描更早活跃分片取链尾（覆盖校验器分支）。"""
    platform, _, _, _ = pair
    jan_tail = await seed_chain_rows(
        platform, log_type="operation", month="202601", tenant_id=7, count=1, starting_prev="0" * 64
    )
    await seed_chain_rows(platform, log_type="operation", month="202602", tenant_id=7, count=1, starting_prev=jan_tail)
    platform.add_all(
        [
            SysAuditShard(log_type="operation", shard_month="202601", physical_table="sys_operation_log_202601"),
            SysAuditShard(log_type="operation", shard_month="202602", physical_table="sys_operation_log_202602"),
        ]
    )
    await platform.commit()
    verifier = AuditChainVerifier(platform, Sha256HashChain())
    tails = await verifier._tails_before("operation", "202602")  # pyright: ignore[reportPrivateUsage]
    assert tails["7"] == jan_tail
    outcome = await verifier.verify("operation", None)
    assert outcome.valid is True
    assert outcome.checked_months == ["202601", "202602"]
