"""作业存储护栏（Kiwi 2375 / 2376 / 2378 / 2381）：提交幂等 / 抢占 CAS / 进度 / 终态 / 取消 / 重试 / 回收 / 清理。"""

from datetime import timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.jobs import store
from bms_core.jobs.spec import JobSubmission, now_utc, parse_job_payload
from bms_core.jobs.store import (
    CANCEL_MISSING,
    CANCEL_TERMINAL,
    CANCEL_UPDATED,
    RETRY_MISSING,
    RETRY_TERMINAL,
    RETRY_UPDATED,
)
from bms_core.models.job import SysJob, SysJobError

pytestmark = pytest.mark.kiwi_id(2375)


async def _submit(session: AsyncSession, *, key: str | None = None, max_attempts: int = 2) -> int:
    """提交一条测试作业。

    Args:
        session: 会话。
        key: 幂等键。
        max_attempts: 最大执行次数。

    Returns:
        int: 作业主键。
    """
    async with session.begin():
        record, _ = await store.submit_job(
            session,
            submission=JobSubmission(
                job_type="demo.echo",
                payload=ConcurrentStableDict({"n": 1}),
                idempotency_key=key,
            ),
            service_key="platform",
            domain_key="job",
            max_attempts=max_attempts,
        )
        job_id = int(record.id)
    return job_id


async def test_submit_and_idempotency(session: AsyncSession) -> None:
    """提交即持久；同幂等键返回既有作业，不重复插入。"""
    async with session.begin():
        first, created = await store.submit_job(
            session,
            submission=JobSubmission(
                job_type="demo.echo", payload=ConcurrentStableDict({"n": 1}), idempotency_key="k1"
            ),
            service_key="platform",
            domain_key="job",
            max_attempts=2,
        )
        second, created_again = await store.submit_job(
            session,
            submission=JobSubmission(
                job_type="demo.echo", payload=ConcurrentStableDict({"n": 1}), idempotency_key="k1"
            ),
            service_key="platform",
            domain_key="job",
            max_attempts=2,
        )
    assert created is True and created_again is False
    assert first.id == second.id
    async with session.begin():
        rows = (await session.execute(select(SysJob))).scalars().all()
    assert len(rows) == 1
    assert rows[0].status == "queued"
    assert parse_job_payload(rows[0].payload) == {"n": 1}


async def test_claim_is_cas(session: AsyncSession) -> None:
    """条件抢占：第一次成功，第二次（同状态）失败。"""
    job_id = await _submit(session)
    now = now_utc()
    async with session.begin():
        claims = await store.claim_candidates(session, now=now, limit=10)
        assert [item.job_id for item in claims] == [job_id]
        assert await store.claim_job(
            session, job_id=job_id, worker_id="w1", lease_until=now + timedelta(seconds=60), now=now
        )
        assert not await store.claim_job(
            session, job_id=job_id, worker_id="w2", lease_until=now + timedelta(seconds=60), now=now
        )
    async with session.begin():
        record = await store.get_job(session, job_id)
    assert record is not None
    assert record.status == "running"
    assert record.attempts == 1
    assert record.lease_owner == "w1"
    assert record.started_at is not None


async def test_progress_and_finish(session: AsyncSession) -> None:
    """进度可查；终态落库且不可重复收敛。"""
    job_id = await _submit(session)
    now = now_utc()
    async with session.begin():
        await store.claim_job(session, job_id=job_id, worker_id="w1", lease_until=now + timedelta(seconds=60), now=now)
        assert await store.update_progress(session, job_id=job_id, done=3, total=10, now=now)
        assert await store.finish_job(
            session, job_id=job_id, status="succeeded", finished_at=now, result_text='{"ok":true}'
        )
        assert not await store.finish_job(session, job_id=job_id, status="failed", finished_at=now)
    async with session.begin():
        record = await store.get_job(session, job_id)
    assert record is not None
    assert record.progress_done == 3 and record.progress_total == 10
    assert record.status == "succeeded"
    assert record.finished_at is not None


async def test_cancel_paths(session: AsyncSession) -> None:
    """取消：队列直接取消；运行中置标记；终态拒绝；不存在返回 missing。"""
    queued_id = await _submit(session)
    now = now_utc()
    async with session.begin():
        assert await store.request_cancel(session, job_id=queued_id, now=now) == CANCEL_UPDATED
        assert await store.request_cancel(session, job_id=queued_id, now=now) == CANCEL_TERMINAL
        assert await store.request_cancel(session, job_id=999999, now=now) == CANCEL_MISSING

    running_id = await _submit(session)
    async with session.begin():
        await store.claim_job(
            session, job_id=running_id, worker_id="w1", lease_until=now + timedelta(seconds=60), now=now
        )
        assert await store.request_cancel(session, job_id=running_id, now=now) == CANCEL_UPDATED
    async with session.begin():
        record = await store.get_job(session, running_id)
    assert record is not None and record.cancel_requested is True


async def test_retry_paths(session: AsyncSession) -> None:
    """人工重试：仅 dead / failed；重置尝试次数回队；其余拒绝。"""
    job_id = await _submit(session, max_attempts=1)
    now = now_utc()
    async with session.begin():
        assert (await store.retry_job(session, job_id=job_id, now=now)).status == RETRY_TERMINAL
        assert (await store.retry_job(session, job_id=999999, now=now)).status == RETRY_MISSING
        await store.claim_job(session, job_id=job_id, worker_id="w1", lease_until=now - timedelta(seconds=1), now=now)
        await store.reclaim_expired(session, now=now)
        result = await store.retry_job(session, job_id=job_id, now=now)
    assert result.status == RETRY_UPDATED
    async with session.begin():
        record = await store.get_job(session, job_id)
    assert record is not None
    assert record.status == "queued"
    assert record.attempts == 0


async def test_reclaim_requeues_and_dead(session: AsyncSession) -> None:
    """租约过期：未达上限回队；达上限转死信。"""
    now = now_utc()
    dead_tail_id = await _submit(session, max_attempts=1)
    requeue_id = await _submit(session, max_attempts=3)
    dead_id = await _submit(session, max_attempts=1)
    async with session.begin():
        for job_id in (requeue_id, dead_id, dead_tail_id):
            await store.claim_job(
                session, job_id=job_id, worker_id="w", lease_until=now - timedelta(seconds=1), now=now
            )
        result = await store.reclaim_expired(session, now=now)
    assert result.requeued == 1
    assert result.dead == 2
    async with session.begin():
        requeued = await store.get_job(session, requeue_id)
        dead = await store.get_job(session, dead_id)
    assert requeued is not None and requeued.status == "queued"
    assert dead is not None and dead.status == "dead"


async def test_error_rows_and_cleanup(session: AsyncSession) -> None:
    """行级错误可查；保留期清理硬删作业与错误明细。"""
    job_id = await _submit(session)
    now = now_utc()
    async with session.begin():
        await store.add_job_error(session, job_id=job_id, message="行错误", row_no=2, column_key="name")
        await store.claim_job(session, job_id=job_id, worker_id="w", lease_until=now + timedelta(seconds=60), now=now)
        await store.finish_job(session, job_id=job_id, status="failed", finished_at=now, error_text="boom")
    async with session.begin():
        errors = await store.list_job_errors(session, job_id=job_id)
        assert len(errors) == 1
        assert errors[0].row_no == 2
        assert errors[0].column_key == "name"
        removed = await store.cleanup_finished_jobs(session, cutoff=now + timedelta(days=1))
    assert removed == 1
    async with session.begin():
        left = (await session.execute(select(SysJobError))).scalars().all()
    assert left == []


async def test_heartbeat_only_owner(session: AsyncSession) -> None:
    """续租：只有持租约的实例能续；转手 / 非运行态返回 False。"""
    job_id = await _submit(session)
    now = now_utc()
    async with session.begin():
        await store.claim_job(session, job_id=job_id, worker_id="w1", lease_until=now + timedelta(seconds=60), now=now)
        assert await store.heartbeat(
            session, job_id=job_id, worker_id="w1", lease_until=now + timedelta(seconds=120), now=now
        )
        assert not await store.heartbeat(
            session, job_id=job_id, worker_id="w2", lease_until=now + timedelta(seconds=120), now=now
        )


async def test_finish_rejects_non_terminal(session: AsyncSession) -> None:
    """落终态：非终态值直接拒绝（防误把运行中当终态）。"""
    job_id = await _submit(session)
    now = now_utc()
    async with session.begin():
        await store.claim_job(session, job_id=job_id, worker_id="w1", lease_until=now + timedelta(seconds=60), now=now)
        with pytest.raises(ValueError, match="非终态"):
            await store.finish_job(session, job_id=job_id, status="running", finished_at=now)


async def test_claim_candidates_filters_job_types(session: AsyncSession) -> None:
    """候选：可按作业类型过滤（None 取全部）。"""
    await _submit(session)
    now = now_utc()
    async with session.begin():
        all_claims = await store.claim_candidates(session, now=now, limit=10)
        filtered = await store.claim_candidates(
            session, now=now, limit=10, job_types=ConcurrentStableList(["demo.echo"])
        )
        empty = await store.claim_candidates(session, now=now, limit=10, job_types=ConcurrentStableList(["absent"]))
    assert len(all_claims) == 1
    assert len(filtered) == 1
    assert empty == []


async def test_snapshot_of_record(session: AsyncSession) -> None:
    """快照：ORM 行转只读快照，负载重新解析为插入序集合。"""
    job_id = await _submit(session)
    async with session.begin():
        record = await store.get_job(session, job_id)
    assert record is not None
    snapshot = store.snapshot_of(record)
    assert snapshot.id == job_id
    assert snapshot.payload["n"] == 1


async def test_reclaim_skips_rows_taken_by_others(session: AsyncSession, monkeypatch: pytest.MonkeyPatch) -> None:
    """回收：并发下已被他人处理的行（mark_dead / requeue 返回 False）跳过，不计数。"""
    dead_id = await _submit(session, max_attempts=1)
    requeue_id = await _submit(session, max_attempts=3)
    now = now_utc()
    async with session.begin():
        for job_id in (dead_id, requeue_id):
            await store.claim_job(
                session, job_id=job_id, worker_id="w", lease_until=now - timedelta(seconds=1), now=now
            )

    async def _false(*args: object, **kwargs: object) -> bool:
        del args, kwargs
        return False

    monkeypatch.setattr(store, "mark_dead", _false)
    monkeypatch.setattr(store, "requeue_job", _false)
    async with session.begin():
        result = await store.reclaim_expired(session, now=now)
    assert result.requeued == 0 and result.dead == 0
