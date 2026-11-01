"""作业中心平台侧单元用例：目录仓储 / 监控仓储 / 目录同步 / 用户面路由。"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest
from sqlalchemy import Table
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.exceptions import JobNotFoundError
from bms_core.events.base import EventEnvelope
from bms_core.models.base import Base
from bms_core.models.platform.job import SysJobMonitor, SysJobType
from bms_core.schemas.pagination import BasePageQuery
from bms_platform.domains.job.api import job as job_api
from bms_platform.domains.job.repositories.job import JobMonitorRepository, JobTypeRepository
from bms_platform.domains.job.services.catalog import JobCatalogService
from bms_platform.domains.job.services.monitor import JobMonitorService

pytestmark = pytest.mark.kiwi_id(2386)

BASE = datetime(2026, 11, 1, 3, 0, 0)


@pytest.fixture
async def session(tmp_path: Path) -> AsyncGenerator[AsyncSession]:
    """建作业目录 / 监控两表并开会话。"""
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'jobdomain.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(
            lambda conn: Base.metadata.create_all(
                conn,
                tables=[cast("Table", SysJobMonitor.__table__), cast("Table", SysJobType.__table__)],
            )
        )
    factory: async_sessionmaker[AsyncSession] = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as opened:
        yield opened
    await engine.dispose()


def _declaration(job_type: str = "demo.echo", *, status: str = "enabled", description: str = "演示") -> Any:
    """构造作业声明替身。"""
    return SimpleNamespace(
        job_type=job_type,
        service="platform",
        domain="job",
        handler="bms_platform.jobs:handler",
        description=description,
        timeout_seconds=60,
        max_attempts=3,
        backoff_seconds=5,
        concurrency=1,
        payload_version="1.0.0",
        status=status,
    )


async def test_catalog_sync_creates_updates_and_retires(session: AsyncSession) -> None:
    """目录同步：新建 → 内容未变 → 内容变更 → 缺失退役。"""
    service = JobCatalogService(JobTypeRepository(session))
    created = await service.sync(ConcurrentStableList([_declaration()]), source="platform")
    assert created.created == 1

    unchanged = await service.sync(ConcurrentStableList([_declaration()]), source="platform")
    assert unchanged.unchanged == 1

    updated = await service.sync(ConcurrentStableList([_declaration(description="改")]), source="platform")
    assert updated.updated == 1

    retired = await service.sync(ConcurrentStableList([]), source="platform")
    assert retired.retired == 1


async def test_catalog_page_and_list_all(session: AsyncSession) -> None:
    """目录查询：分页过滤与全量清单。"""
    service = JobCatalogService(JobTypeRepository(session))
    await service.sync(ConcurrentStableList([_declaration()]), source="platform")
    rows, total = await service.page(page=1, size=10)
    assert total == 1 and len(rows) == 1
    filtered, filtered_total = await service.page(page=1, size=10, service_key="platform", status="enabled")
    assert filtered_total == 1 and len(filtered) == 1
    empty, empty_total = await service.page(page=1, size=10, service_key="absent")
    assert empty_total == 0 and list(empty) == []
    assert len(await service.list_all()) == 1


def _monitor_row(job_id: int, **overrides: object) -> SysJobMonitor:
    """构造监控投影行。"""
    values: ConcurrentStableDict[str, object] = ConcurrentStableDict(
        {
            "job_id": job_id,
            "job_type": "demo.echo",
            "service_key": "platform",
            "tenant_id": 9,
            "status": "queued",
            "last_event_at": BASE,
            "progress_done": 0,
            "progress_total": None,
            "attempts": 0,
            "error": None,
        }
    )
    values.update(overrides)
    return SysJobMonitor(**dict(values))


async def test_monitor_repository_filters_and_purge(session: AsyncSession) -> None:
    """监控仓储：多维过滤分页与按时间清理。"""
    session.add_all(
        [
            _monitor_row(1, status="running", last_event_at=BASE),
            _monitor_row(2, job_type="other.echo", tenant_id=10, last_event_at=BASE + timedelta(minutes=1)),
        ]
    )
    await session.commit()
    repository = JobMonitorRepository(session)
    rows, total = await repository.page_filtered(page=1, size=10)
    assert total == 2 and len(rows) == 2
    filtered, filtered_total = await repository.page_filtered(
        page=1, size=10, job_type="other.echo", status="queued", service_key="platform", tenant_id=10
    )
    assert filtered_total == 1 and int(filtered[0].job_id) == 2
    purged = await repository.delete_expired(cutoff=BASE + timedelta(seconds=30))
    assert purged == 1


async def test_monitor_service_drops_stale_and_missing(session: AsyncSession) -> None:
    """投影服务：旧事件丢弃 / started 置运行 / 无行返回 False。"""
    service = JobMonitorService(JobMonitorRepository(session))
    session.add(_monitor_row(1, last_event_at=BASE + timedelta(minutes=5)))
    await session.commit()

    stale = await service.apply(
        EventEnvelope(
            event_type="sys.job.started",
            payload=ConcurrentStableDict({"job_id": "1", "job_type": "demo.echo", "service_key": "platform"}),
            occurred_at=BASE,
        )
    )
    assert stale is False

    missing = await service.apply(
        EventEnvelope(
            event_type="sys.job.completed",
            payload=ConcurrentStableDict({"job_id": "404", "job_type": "demo.echo", "service_key": "platform"}),
            occurred_at=BASE,
        )
    )
    assert missing is True


class _Uow:
    """工作单元替身。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    @asynccontextmanager
    async def begin(self) -> AsyncGenerator[None]:
        """空事务上下文。"""
        yield


def _endpoint(path: str, method: str) -> Any:
    """按路径后缀与方法取路由处理函数。"""
    for route in cast("Any", job_api.router).routes:
        if route.path.endswith(path) and method in route.methods:
            return route.endpoint
    raise AssertionError(f"未找到路由：{method} {path}")


def _page(page: int = 1, size: int = 10) -> BasePageQuery:
    """构造分页参数。"""
    return BasePageQuery(page=page, size=size)


async def test_api_list_types_and_monitor(session: AsyncSession, monkeypatch: pytest.MonkeyPatch) -> None:
    """用户面：类型目录分页与监控列表分页。"""
    monkeypatch.setattr(job_api, "current_tenant_context", lambda: SimpleNamespace(tenant_id=9))
    await JobCatalogService(JobTypeRepository(session)).sync(ConcurrentStableList([_declaration()]), source="platform")
    session.add(_monitor_row(1))
    await session.commit()

    types = await _endpoint("/types", "GET")(cast("Any", _Uow(session)), _page(), None, None)
    assert types.data.total == 1
    monitor = await _endpoint("/jobs", "GET")(cast("Any", _Uow(session)), _page(), None, None, None)
    assert monitor.data.total == 1


async def test_api_monitor_detail_and_missing(session: AsyncSession, monkeypatch: pytest.MonkeyPatch) -> None:
    """用户面：监控详情存在 / 不存在。"""
    monkeypatch.setattr(job_api, "current_tenant_context", lambda: SimpleNamespace(tenant_id=9))
    session.add(_monitor_row(1))
    await session.commit()
    detail = _endpoint("/jobs/{job_id}", "GET")
    response = await detail(cast("Any", _Uow(session)), 1)
    assert response.data.job_id == 1
    with pytest.raises(JobNotFoundError, match="作业不存在或投影尚未到达"):
        await detail(cast("Any", _Uow(session)), 404)


async def test_api_cancel_and_retry_forward(session: AsyncSession, monkeypatch: pytest.MonkeyPatch) -> None:
    """用户面：取消 / 重试按投影服务键转发内部契约。"""
    monkeypatch.setattr(job_api, "current_tenant_context", lambda: SimpleNamespace(tenant_id=9))
    session.add(_monitor_row(1))
    await session.commit()
    calls: ConcurrentStableList[tuple[str, int]] = ConcurrentStableList()

    class _Client:
        async def cancel(
            self, *, service_key: str, job_id: int, reason: str | None = None, tenant_id: int | None = None
        ) -> str:
            del service_key, reason, tenant_id
            calls.append(("cancel", job_id))
            return "canceled"

        async def retry(self, *, service_key: str, job_id: int, tenant_id: int | None = None) -> str:
            del service_key, tenant_id
            calls.append(("retry", job_id))
            return "retried"

    monkeypatch.setattr(job_api, "_client", lambda: _Client())
    canceled = await _endpoint("/{job_id}/cancel", "POST")(cast("Any", _Uow(session)), 1, None)
    retried = await _endpoint("/{job_id}/retry", "POST")(cast("Any", _Uow(session)), 1)
    assert canceled.data.status == "canceled"
    assert retried.data.status == "retried"
    assert calls == [("cancel", 1), ("retry", 1)]


async def test_api_service_key_of_missing(session: AsyncSession, monkeypatch: pytest.MonkeyPatch) -> None:
    """内部辅助：投影缺失时报 71001。"""
    monkeypatch.setattr(job_api, "current_tenant_context", lambda: SimpleNamespace(tenant_id=9))
    with pytest.raises(JobNotFoundError, match="作业不存在或投影尚未到达"):
        await job_api._service_key_of(cast("Any", _Uow(session)), 404)  # pyright: ignore[reportPrivateUsage]


async def test_monitor_service_progress_without_existing(session: AsyncSession) -> None:
    """进度事件先到：无既有行时建投影并置运行态。"""
    from bms_core.core.concurrent import ConcurrentStableDict
    from bms_core.events.base import EventEnvelope
    from bms_core.jobs.events import JOB_PROGRESS_EVENT

    service = JobMonitorService(JobMonitorRepository(session))
    applied = await service.apply(
        EventEnvelope(
            event_type=JOB_PROGRESS_EVENT,
            payload=ConcurrentStableDict({"job_id": "9", "job_type": "demo.echo", "service_key": "platform"}),
            occurred_at=BASE,
        )
    )
    assert applied is True
    record = await JobMonitorRepository(session).get_by_job_id(9)
    assert record is not None and record.status == "running"


async def test_monitor_service_ignores_unknown_event(session: AsyncSession) -> None:
    """非作业事件：直接忽略（不写投影）。"""
    from bms_core.core.concurrent import ConcurrentStableDict
    from bms_core.events.base import EventEnvelope

    service = JobMonitorService(JobMonitorRepository(session))
    applied = await service.apply(
        EventEnvelope(
            event_type="sys.unknown.event",
            payload=ConcurrentStableDict({"job_id": "9", "job_type": "demo.echo", "service_key": "platform"}),
            occurred_at=BASE,
        )
    )
    assert applied is False


def test_client_builder_wraps_service_client(monkeypatch: pytest.MonkeyPatch) -> None:
    """内部客户端构造：按服务间调用能力构建 `JobInternalClient`。"""
    sentinel = object()
    monkeypatch.setattr(job_api, "build_service_client", lambda: sentinel)
    assert job_api._client()._client is sentinel  # pyright: ignore[reportPrivateUsage]


async def test_monitor_service_ignores_incomplete_payload(session: AsyncSession) -> None:
    """负载缺作业类型 / 服务键：直接忽略（无法定位投影）。"""
    service = JobMonitorService(JobMonitorRepository(session))
    applied = await service.apply(
        EventEnvelope(
            event_type="sys.job.started",
            payload=ConcurrentStableDict({"job_id": "9"}),
            occurred_at=BASE,
        )
    )
    assert applied is False
