"""注销租户清理测试（任务 `04_03-02`；Kiwi 2458）。

覆盖：到期清理（逐服务删库 → 删注册行与对照行 → `tenant.purged` 只发一次 + 审计一条）、
未到期 / `purge_at` 为空 / 已被恢复 / 注册行缺失一律 `skipped`（零副作用）、单库失败保留注册行且重试收敛、
重复执行幂等、归档就绪时回填保留期、扫描只取到期目标、两个作业处理器的成功 / 失败 / 提交路径。

测试库：共享平台库 + 回滚会话；租户编码按命名空间生成，事件按本租户 ID 过滤，扫描按编码收敛。
"""

from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from types import SimpleNamespace
from typing import Any, cast

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from bms_core.config.models import SysConfig
from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.config import Settings, get_settings
from bms_core.core.exceptions import ConfigError
from bms_core.db.session import DbSession
from bms_core.jobs.base import JobContext
from bms_core.models.job import SysJob
from bms_core.models.outbox import SysOutbox
from bms_core.models.tenant.tenant import (
    TENANT_STATUS_ACTIVE,
    TENANT_STATUS_DELETED,
    TENANT_STATUS_SUSPENDED,
    SysTenant,
)
from bms_core.models.tenant.tenant_database import SysTenantDatabase
from bms_core.outbox.store import SqlOutboxStore
from bms_core.testing.namespace import Namespace
from bms_core.testing.transaction import write_session
from bms_tenant.domains.tenant.jobs import (
    TENANT_PURGE_JOB_TYPE,
    TENANT_PURGE_SCAN_JOB_TYPE,
    TenantPurgeJob,
    TenantPurgeScanJob,
    _batch_size,  # pyright: ignore[reportPrivateUsage]
)
from bms_tenant.domains.tenant.services import tenant_purge as tenant_purge_module
from bms_tenant.domains.tenant.services.tenant_admin import DELETION_RETENTION_KEY
from bms_tenant.domains.tenant.services.tenant_purge import (
    DEFAULT_PURGE_BATCH_SIZE,
    PURGED_EVENT,
    TenantPurgeService,
)

pytestmark = pytest.mark.kiwi_id(2458)

NOW = datetime(2026, 11, 8, 12, 0, 0)
"""固定「当前时刻」（时间注入，不用 sleep）。"""


@pytest.fixture
async def session(
    shared_platform_engine: AsyncEngine,
) -> AsyncIterator[AsyncSession]:
    """共享平台库上的写会话（不提交，退出即回滚）。

    Args:
        shared_platform_engine: 共享平台库引擎。

    Yields:
        AsyncSession: 数据库会话。
    """
    async with write_session(shared_platform_engine) as db:
        yield db


async def _seed(
    session: AsyncSession,
    ns: Namespace,
    *,
    suffix: str,
    status: str = TENANT_STATUS_DELETED,
    purge_at: datetime | None = None,
) -> SysTenant:
    """写一条租户（含库名对照），返回注册行。

    Args:
        session: 写会话。
        ns: 本用例命名空间。
        suffix: 编码后缀（同用例内区分多个租户）。
        status: 状态。
        purge_at: 保留期截止（None 表示留空待回填）。

    Returns:
        SysTenant: 注册行。
    """
    code = f"{ns.prefix}{suffix}"
    row = SysTenant(code=code, name=code, kind="business", status=status)
    row.deletion_requested_at = NOW - timedelta(days=1) if status == TENANT_STATUS_DELETED else None
    row.purge_at = purge_at
    session.add(row)
    await session.flush()
    session.add(SysTenantDatabase(tenant_id=int(row.id), db_basis=code))
    await session.flush()
    return row


async def _seed_config(session: AsyncSession, *, key: str, value: str) -> None:
    """写一条系统参数。

    Args:
        session: 写会话。
        key: 参数键。
        value: 参数值。
    """
    session.add(SysConfig(form_key="config", config_key=key, name=key, value=value))
    await session.flush()


async def _events(
    session: AsyncSession, event_type: str, tenant_id: int | None = None
) -> ConcurrentStableList[SysOutbox]:
    """按类型（+ 本租户）取发件箱事件（升序）。

    Args:
        session: 写会话。
        event_type: 事件类型。
        tenant_id: 租户主键；None 不按租户过滤（仅用于无租户事件）。

    Returns:
        ConcurrentStableList[SysOutbox]: 事件行。
    """
    statement = select(SysOutbox).where(SysOutbox.event_type == event_type)
    if tenant_id is not None:
        statement = statement.where(SysOutbox.tenant_id == tenant_id)
    rows = await session.execute(statement.order_by(SysOutbox.id))
    return ConcurrentStableList(rows.scalars().all())


async def _tenant_row(session: AsyncSession, tenant_id: int) -> SysTenant | None:
    """直读注册行（校验是否被物理删除）。

    Args:
        session: 写会话。
        tenant_id: 租户主键。

    Returns:
        SysTenant | None: 注册行；已删返回 None。
    """
    return (await session.execute(select(SysTenant).where(SysTenant.id == tenant_id))).scalar_one_or_none()


async def _database_rows(session: AsyncSession, tenant_id: int) -> int:
    """取库名对照行数（清理后应为 0）。

    Args:
        session: 写会话。
        tenant_id: 租户主键。

    Returns:
        int: 行数。
    """
    rows = await session.execute(select(SysTenantDatabase).where(SysTenantDatabase.tenant_id == tenant_id))
    return len(rows.scalars().all())


async def _job_rows(session: AsyncSession, *tenant_ids: int) -> ConcurrentStableList[SysJob]:
    """取本用例提交的作业行（按幂等键中的租户 ID 收敛）。

    Args:
        session: 写会话。
        *tenant_ids: 本用例租户主键。

    Returns:
        ConcurrentStableList[SysJob]: 作业行。
    """
    rows = (
        (await session.execute(select(SysJob).where(SysJob.job_type == TENANT_PURGE_JOB_TYPE).order_by(SysJob.id)))
        .scalars()
        .all()
    )
    prefixes = tuple(f"{TENANT_PURGE_JOB_TYPE}:{tenant_id}:" for tenant_id in tenant_ids)
    return ConcurrentStableList(row for row in rows if str(row.idempotency_key).startswith(prefixes))


class _DropRecorder:
    """删库执行器替身（记录调用序列，可指定失败服务）。"""

    def __init__(self, *, fail: ConcurrentStableList[str] | None = None) -> None:
        self.calls: ConcurrentStableList[tuple[str, str]] = ConcurrentStableList()
        self._fail = fail if fail is not None else ConcurrentStableList[str]()

    async def __call__(self, service: str, basis: str) -> bool:
        """记录一次删库；命中失败清单时抛错。

        Args:
            service: 服务标识。
            basis: 库名基。

        Returns:
            bool: 恒 True（库存在即删）。

        Raises:
            RuntimeError: 该服务被指定为失败。
        """
        self.calls.add((service, basis))
        if service in self._fail:
            raise RuntimeError("db unreachable")
        return True


async def _purge(
    session: AsyncSession,
    tenant_id: int,
    *,
    drop: Any = None,
    services: ConcurrentStableList[str] | None = None,
    settings: Settings | None = None,
    fixed_clock: bool = True,
) -> Any:
    """执行一次单租户清理（复用回滚会话）。

    Args:
        session: 写会话。
        tenant_id: 租户主键。
        drop: 删库替身（None 走运维通道默认实现）。
        services: 服务清单（None 取 platform + file）。
        settings: 应用配置（None 取默认）。
        fixed_clock: 是否注入固定时钟。

    Returns:
        Any: 清理结果。
    """
    resolved: ConcurrentStableList[str] = (
        services if services is not None else ConcurrentStableList[str](("platform", "file"))
    )
    service = TenantPurgeService(
        session=session,
        outbox=SqlOutboxStore(),
        settings=settings,
        services=lambda: resolved,
        drop=drop,
        clock=(lambda: NOW) if fixed_clock else None,
    )
    return await service.purge(tenant_id)


async def _scan(
    session: AsyncSession,
    *,
    settings: Settings | None,
    batch_size: int = 50,
    only_codes: ConcurrentStableList[str] | None = None,
) -> Any:
    """执行一轮扫描（复用回滚会话）。

    Args:
        session: 写会话。
        settings: 应用配置（判归档是否就绪）。
        batch_size: 批大小。
        only_codes: 只扫这些租户编码。

    Returns:
        Any: 扫描结果。
    """
    service = TenantPurgeService(
        session=session,
        outbox=SqlOutboxStore(),
        settings=settings,
        services=lambda: ConcurrentStableList[str](),
        drop=_DropRecorder(),
        clock=lambda: NOW,
    )
    return await service.scan(batch_size=batch_size, only_codes=only_codes)


def _archive_ready_settings() -> Settings:
    """构造「归档已就绪」的配置替身。

    Returns:
        Settings: 配置替身（仅 `archive_policy.provider` 被读取）。
    """
    return cast("Settings", SimpleNamespace(archive_policy=SimpleNamespace(provider="db")))


def _ctx(
    session: AsyncSession,
    *,
    job_type: str,
    payload: ConcurrentStableDict[str, object],
    progress: ConcurrentStableList[tuple[int, int | None]],
) -> JobContext:
    """构造作业执行上下文（会话开合口接回滚会话）。

    Args:
        session: 写会话。
        job_type: 作业类型。
        payload: 作业负载。
        progress: 进度记录器。

    Returns:
        JobContext: 执行上下文。
    """

    @asynccontextmanager
    async def _open() -> AsyncGenerator[AsyncSession]:
        yield session

    async def _report(done: int, total: int | None) -> None:
        progress.add((done, total))

    return JobContext(
        job_id=1,
        job_type=job_type,
        service_key="tenant",
        db_key="platform_tenant",
        tenant_id=None,
        payload=ConcurrentStableDict(payload),
        open_session=_open,
        progress_reporter=_report,
    )


async def test_purge_due_tenant_cleans_all_services(session: AsyncSession, ns: Namespace) -> None:
    """到期清理：逐服务删库、删注册行与对照行、`tenant.purged` 一次、审计一条。"""
    tenant = await _seed(session, ns, suffix="a", purge_at=NOW - timedelta(hours=1))
    tenant_id = int(tenant.id)
    recorder = _DropRecorder()

    outcome = await _purge(session, tenant_id, drop=recorder)

    assert outcome.status == "purged"
    assert list(recorder.calls) == [("platform", tenant.code), ("file", tenant.code)]
    assert len(outcome.dropped_services) == 2
    assert await _tenant_row(session, tenant_id) is None
    assert await _database_rows(session, tenant_id) == 0
    purged = await _events(session, PURGED_EVENT, tenant_id)
    assert len(purged) == 1
    assert purged[0].payload["status"] == "purged"
    assert purged[0].payload["db_key"] == tenant.code
    assert purged[0].payload["dropped_services"] == 2
    assert purged[0].payload["failed_services"] == 0
    audit = await _events(session, "sys.operation.logged", tenant_id)
    assert len(audit) == 1
    assert audit[0].payload["action"] == "tenant:purge"
    assert audit[0].payload["username"] == "system"


async def test_purge_skips_when_not_applicable(session: AsyncSession, ns: Namespace) -> None:
    """未到期 / `purge_at` 空 / 已被恢复 / 注册行缺失：一律跳过且零副作用。"""
    not_due = await _seed(session, ns, suffix="later", purge_at=NOW + timedelta(days=3))
    waiting = await _seed(session, ns, suffix="waiting", purge_at=None)
    restored = await _seed(session, ns, suffix="back", status=TENANT_STATUS_ACTIVE, purge_at=None)
    suspended = await _seed(session, ns, suffix="paused", status=TENANT_STATUS_SUSPENDED)
    recorder = _DropRecorder()

    later = await _purge(session, int(not_due.id), drop=recorder)
    empty = await _purge(session, int(waiting.id), drop=recorder)
    active = await _purge(session, int(restored.id), drop=recorder)
    paused = await _purge(session, int(suspended.id), drop=recorder)
    missing = await _purge(session, 999999, drop=recorder)

    assert (later.status, later.reason) == ("skipped", "not_due")
    assert (empty.status, empty.reason) == ("skipped", "purge_at_empty")
    assert active.status == "skipped" and active.reason == f"status={TENANT_STATUS_ACTIVE}"
    assert paused.status == "skipped" and paused.reason == f"status={TENANT_STATUS_SUSPENDED}"
    assert (missing.status, missing.reason) == ("skipped", "missing")
    assert len(recorder.calls) == 0
    for tenant_id in (int(not_due.id), int(waiting.id), int(restored.id), int(suspended.id)):
        assert await _tenant_row(session, tenant_id) is not None
    assert len(await _events(session, PURGED_EVENT, int(not_due.id))) == 0


async def test_purge_partial_failure_keeps_row_and_retry_converges(session: AsyncSession, ns: Namespace) -> None:
    """单库失败：保留注册行与对照行、失败清单准确、无事件；重试后收敛。"""
    tenant = await _seed(session, ns, suffix="a", purge_at=NOW - timedelta(hours=1))
    tenant_id = int(tenant.id)
    broken = _DropRecorder(fail=ConcurrentStableList(["file"]))

    failed = await _purge(session, tenant_id, drop=broken)

    assert failed.status == "failed"
    assert list(failed.failed_services) == ["file"]
    assert "库删除失败" in failed.reason
    assert await _tenant_row(session, tenant_id) is not None
    assert await _database_rows(session, tenant_id) == 1
    assert len(await _events(session, PURGED_EVENT, tenant_id)) == 0

    healthy = _DropRecorder()
    retried = await _purge(session, tenant_id, drop=healthy)
    assert retried.status == "purged"
    assert await _tenant_row(session, tenant_id) is None
    assert len(await _events(session, PURGED_EVENT, tenant_id)) == 1


async def test_purge_is_idempotent(session: AsyncSession, ns: Namespace) -> None:
    """重复执行：第二次 `skipped`（行已删），不重复发事件。"""
    tenant = await _seed(session, ns, suffix="a", purge_at=NOW - timedelta(minutes=1))
    tenant_id = int(tenant.id)
    recorder = _DropRecorder()

    first = await _purge(session, tenant_id, drop=recorder)
    second = await _purge(session, tenant_id, drop=recorder)

    assert first.status == "purged"
    assert (second.status, second.reason) == ("skipped", "missing")
    assert len(await _events(session, PURGED_EVENT, tenant_id)) == 1
    assert len(recorder.calls) == 2  # 只有第一次真正删库


async def test_scan_backfills_when_archive_ready(session: AsyncSession, ns: Namespace) -> None:
    """归档就绪：`purge_at` 为空的行按当下起算回填（给足新保留期）。"""
    tenant = await _seed(session, ns, suffix="waiting", purge_at=None)
    tenant_id = int(tenant.id)
    await _seed_config(session, key=DELETION_RETENTION_KEY, value="7")

    outcome = await _scan(
        session,
        settings=_archive_ready_settings(),
        only_codes=ConcurrentStableList((tenant.code,)),
    )

    assert outcome.backfilled == 1
    row = await _tenant_row(session, tenant_id)
    assert row is not None and row.purge_at is not None
    assert row.purge_at == NOW + timedelta(days=7)
    assert len(outcome.targets) == 0  # 回填后是未来时点，本轮不清理


async def test_scan_waits_when_archive_not_ready(session: AsyncSession, ns: Namespace) -> None:
    """归档未就绪（settings 未装配）：不回填、不动 `purge_at`。"""
    tenant = await _seed(session, ns, suffix="waiting", purge_at=None)
    tenant_id = int(tenant.id)

    outcome = await _scan(
        session,
        settings=None,
        only_codes=ConcurrentStableList((tenant.code,)),
    )

    assert outcome.backfilled == 0
    row = await _tenant_row(session, tenant_id)
    assert row is not None and row.purge_at is None


async def test_scan_without_scope_and_empty_batch(session: AsyncSession) -> None:
    """未指定编码 + 空批：回填与到期都不扫任何行（覆盖范围过滤的「不传」分支）。"""
    outcome = await _scan(session, settings=_archive_ready_settings(), batch_size=0)
    assert outcome.backfilled == 0
    assert list(outcome.targets) == []


async def test_scan_returns_due_targets_only(session: AsyncSession, ns: Namespace) -> None:
    """扫描目标：只取「已到期」的行，未到期与待回填不进入目标。"""
    due = await _seed(session, ns, suffix="due", purge_at=NOW - timedelta(days=1))
    later = await _seed(session, ns, suffix="later", purge_at=NOW + timedelta(days=1))
    waiting = await _seed(session, ns, suffix="waiting", purge_at=None)

    outcome = await _scan(
        session,
        settings=None,
        only_codes=ConcurrentStableList((due.code, later.code, waiting.code)),
    )

    assert [target.tenant_id for target in outcome.targets] == [int(due.id)]
    assert outcome.targets[0].code == due.code
    assert outcome.targets[0].version >= 1


async def test_purge_job_rejects_bad_payload(session: AsyncSession) -> None:
    """负载缺 `tenant_id`：作业直接失败且不可重试（数据问题，重跑无意义）。"""
    job = TenantPurgeJob()
    result = await job.run(
        _ctx(
            session,
            job_type=TENANT_PURGE_JOB_TYPE,
            payload=ConcurrentStableDict[str, object](),
            progress=ConcurrentStableList(),
        )
    )
    assert result.status == "failed"
    assert result.retryable is False


async def test_purge_job_runs_service(session: AsyncSession, ns: Namespace) -> None:
    """作业成功路径：调用清理服务并按结果收敛（已清理 / 跳过 / 失败三档）。"""
    tenant = await _seed(session, ns, suffix="a", purge_at=NOW - timedelta(hours=1))
    tenant_id = int(tenant.id)

    def _service_factory(db: DbSession) -> TenantPurgeService:
        return TenantPurgeService(
            session=db,
            outbox=SqlOutboxStore(),
            services=lambda: ConcurrentStableList(("platform",)),
            drop=_DropRecorder(),
            clock=lambda: NOW,
        )

    job = TenantPurgeJob(service_factory=_service_factory)
    progress: ConcurrentStableList[tuple[int, int | None]] = ConcurrentStableList()
    result = await job.run(
        _ctx(
            session,
            job_type=TENANT_PURGE_JOB_TYPE,
            payload=ConcurrentStableDict({"tenant_id": str(tenant_id)}),
            progress=progress,
        )
    )
    assert result.status == "succeeded"
    assert result.output is not None and result.output["status"] == "purged"
    assert await _tenant_row(session, tenant_id) is None

    skipped = await job.run(
        _ctx(
            session,
            job_type=TENANT_PURGE_JOB_TYPE,
            payload=ConcurrentStableDict({"tenant_id": str(tenant_id)}),
            progress=progress,
        )
    )
    assert skipped.status == "succeeded"
    assert skipped.output is not None and skipped.output["status"] == "skipped"


async def test_purge_job_reports_failure(session: AsyncSession, ns: Namespace) -> None:
    """作业失败路径：有库删除失败 → `failed`（可重试）并带失败服务清单。"""
    tenant = await _seed(session, ns, suffix="a", purge_at=NOW - timedelta(hours=1))
    tenant_id = int(tenant.id)

    def _service_factory(db: DbSession) -> TenantPurgeService:
        return TenantPurgeService(
            session=db,
            outbox=SqlOutboxStore(),
            services=lambda: ConcurrentStableList(("platform", "file")),
            drop=_DropRecorder(fail=ConcurrentStableList(["file"])),
            clock=lambda: NOW,
        )

    job = TenantPurgeJob(service_factory=_service_factory)
    result = await job.run(
        _ctx(
            session,
            job_type=TENANT_PURGE_JOB_TYPE,
            payload=ConcurrentStableDict({"tenant_id": str(tenant_id)}),
            progress=ConcurrentStableList(),
        )
    )
    assert result.status == "failed"
    assert result.retryable is True
    assert result.output is not None
    assert result.output["failed_service_keys"] == "file"


async def test_scan_job_submits_one_job_per_due_tenant(
    session: AsyncSession, ns: Namespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """扫描作业：到期租户逐个提交 `tenant.purge`（平台链、幂等键含版本与日期）。"""
    first = await _seed(session, ns, suffix="a", purge_at=NOW - timedelta(days=2))
    second = await _seed(session, ns, suffix="b", purge_at=NOW - timedelta(days=1))
    later = await _seed(session, ns, suffix="c", purge_at=NOW + timedelta(days=2))
    codes = ConcurrentStableList((first.code, second.code, later.code))

    original = TenantPurgeService.scan

    async def _scoped(self: TenantPurgeService, *, batch_size: int = DEFAULT_PURGE_BATCH_SIZE) -> Any:
        return await original(self, batch_size=batch_size, only_codes=codes)

    monkeypatch.setattr(TenantPurgeService, "scan", _scoped)

    def _service_factory(db: DbSession) -> TenantPurgeService:
        return TenantPurgeService(
            session=db,
            outbox=SqlOutboxStore(),
            services=lambda: ConcurrentStableList[str](),
            drop=_DropRecorder(),
            clock=lambda: NOW,
        )

    job = TenantPurgeScanJob(service_factory=_service_factory)
    progress: ConcurrentStableList[tuple[int, int | None]] = ConcurrentStableList()
    result = await job.run(
        _ctx(
            session,
            job_type=TENANT_PURGE_SCAN_JOB_TYPE,
            payload=ConcurrentStableDict({"batch_size": "5"}),
            progress=progress,
        )
    )

    assert result.status == "succeeded"
    assert result.output is not None
    assert result.output["due"] == 2 and result.output["submitted"] == 2
    assert list(progress) == [(2, 2)]
    jobs = await _job_rows(session, int(first.id), int(second.id))
    assert len(jobs) == 2
    assert {job.job_type for job in jobs} == {TENANT_PURGE_JOB_TYPE}
    assert {job.tenant_id for job in jobs} == {None}  # 平台链：不能写进即将被删的租户库
    keys = ConcurrentStableList(str(job.idempotency_key) for job in jobs)
    assert any(key.startswith(f"{TENANT_PURGE_JOB_TYPE}:{int(first.id)}:") for key in keys)
    assert any(key.startswith(f"{TENANT_PURGE_JOB_TYPE}:{int(second.id)}:") for key in keys)


def test_job_specs_match_registry_declaration() -> None:
    """作业声明与登记清单口径一致（service / domain / handler 三处不得漂移）。"""
    from bms_tenant.domains.tenant.jobs import job_specs

    specs = job_specs()
    assert set(specs) == {TENANT_PURGE_JOB_TYPE, TENANT_PURGE_SCAN_JOB_TYPE}
    for job_type, spec in specs.items():
        assert spec.job_type == job_type
        assert spec.service_key == "tenant" and spec.domain_key == "tenant"
        assert spec.handler.startswith("bms_tenant.domains.tenant.jobs:")


async def test_purge_requires_configuration(session: AsyncSession, ns: Namespace) -> None:
    """既无删库执行器又无应用配置：装配错误（ConfigError），不是静默跳过。"""
    tenant = await _seed(session, ns, suffix="a", purge_at=NOW - timedelta(hours=1))

    with pytest.raises(ConfigError, match="未装配应用配置"):
        await _purge(session, int(tenant.id), services=ConcurrentStableList(("platform",)))


async def test_purge_uses_ops_channel_by_default(
    session: AsyncSession, ns: Namespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """生产缺省路径：按配置解析各服务租户库连接串后走运维通道删库（时钟用生产缺省）。"""
    tenant = await _seed(session, ns, suffix="a", purge_at=NOW - timedelta(hours=1))
    dropped: ConcurrentStableList[str] = ConcurrentStableList()

    async def _fake_drop(target: Any) -> bool:
        dropped.add(str(target.name))
        return True

    monkeypatch.setattr(tenant_purge_module, "drop_database", _fake_drop)
    outcome = await _purge(
        session,
        int(tenant.id),
        services=ConcurrentStableList(("platform",)),
        settings=get_settings(),
        fixed_clock=False,
    )

    assert outcome.status == "purged"
    assert len(dropped) == 1
    assert await _tenant_row(session, int(tenant.id)) is None


def test_jobs_default_service_wiring() -> None:
    """作业未注入工厂时按缺省能力装配清理服务（不建连）。"""
    outbox = SqlOutboxStore()
    settings = _archive_ready_settings()
    purge_job = TenantPurgeJob(outbox=outbox, settings=settings)
    scan_job = TenantPurgeScanJob(outbox=outbox, settings=settings)

    assert isinstance(purge_job._service(cast("Any", object())), TenantPurgeService)  # pyright: ignore[reportPrivateUsage]
    assert isinstance(scan_job._service(cast("Any", object())), TenantPurgeService)  # pyright: ignore[reportPrivateUsage]


def test_batch_size_fallback_branches() -> None:
    """扫描批大小：缺省 / 非整数 / 非正数一律回落，合法值照用。"""
    assert _batch_size(ConcurrentStableDict[str, object]()) == DEFAULT_PURGE_BATCH_SIZE
    assert _batch_size(ConcurrentStableDict({"batch_size": "abc"})) == DEFAULT_PURGE_BATCH_SIZE
    assert _batch_size(ConcurrentStableDict({"batch_size": 0})) == DEFAULT_PURGE_BATCH_SIZE
    assert _batch_size(ConcurrentStableDict({"batch_size": "9"})) == 9
