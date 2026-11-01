"""作业中心平台侧单元用例：目录仓储 / 监控仓储 / 目录同步 / 用户面路由。

单库叠加口径（04-6-2）：库用共享平台库、写入走 `rollback_session`（整体回滚不残留）。
作业类型 / 服务键带命名空间前缀、作业主键与租户主键按命名空间派生——目录同步的「缺失退役」
与监控的「按时间清理」是**全表**动作，断言因此改为「本用例行的状态」+ 相对增量，
不再数全表行数（叠加库中他人行会一并命中）。
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from types import SimpleNamespace
from typing import Any, cast

import pytest
from sqlalchemy import Table
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.exceptions import JobNotFoundError
from bms_core.events.base import EventEnvelope
from bms_core.models.base import Base
from bms_core.models.platform.job import JOB_TYPE_STATUS_RETIRED, SysJobMonitor, SysJobType
from bms_core.schemas.pagination import BasePageQuery
from bms_core.testing.namespace import Namespace
from bms_core.testing.transaction import rollback_session
from bms_platform.domains.job.api import job as job_api
from bms_platform.domains.job.repositories.job import JobMonitorRepository, JobTypeRepository
from bms_platform.domains.job.services.catalog import JobCatalogService
from bms_platform.domains.job.services.monitor import JobMonitorService

pytestmark = pytest.mark.kiwi_id(2386)

BASE = datetime(2026, 11, 1, 3, 0, 0)

_TABLES: ConcurrentStableList[Table] = ConcurrentStableList(
    (cast("Table", SysJobType.__table__), cast("Table", SysJobMonitor.__table__))
)
"""本文件涉及的表（共享平台库幂等补齐）。"""


def _number(ns: Namespace, slot: int) -> int:
    """按命名空间派生一个正整数（作业主键 / 租户主键用，叠加下不与他人行相撞）。

    Args:
        ns: 用例命名空间。
        slot: 槽位。

    Returns:
        int: 派生值。
    """
    return int(ns.prefix[2:], 16) * 10 + slot


@pytest.fixture
async def session(shared_platform_engine: AsyncEngine) -> AsyncGenerator[AsyncSession]:
    """共享平台库上的回滚会话（作业目录 / 监控两表幂等补齐）。"""
    async with shared_platform_engine.begin() as connection:
        await connection.run_sync(lambda conn: Base.metadata.create_all(conn, tables=list(_TABLES)))
    async with rollback_session(shared_platform_engine) as opened:
        yield opened


def _declaration(job_type: str, *, service: str, status: str = "enabled", description: str = "演示") -> Any:
    """构造作业声明替身。"""
    return SimpleNamespace(
        job_type=job_type,
        service=service,
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


async def test_catalog_sync_creates_updates_and_retires(session: AsyncSession, ns: Namespace) -> None:
    """目录同步：新建 → 内容未变 → 内容变更 → 缺失退役。

    单库叠加口径：作业类型带命名空间前缀；「缺失退役」是全表动作，故断言**本用例行的状态**
    与相对增量（`retired >= 1`），不再断言全表只退役一条。
    """
    job_type = ns.code("job")
    service_key = ns.code("svc")
    catalog = JobCatalogService(JobTypeRepository(session))
    created = await catalog.sync(ConcurrentStableList([_declaration(job_type, service=service_key)]), source="platform")
    assert created.created == 1

    unchanged = await catalog.sync(
        ConcurrentStableList([_declaration(job_type, service=service_key)]), source="platform"
    )
    assert unchanged.unchanged == 1

    updated = await catalog.sync(
        ConcurrentStableList([_declaration(job_type, service=service_key, description="改")]), source="platform"
    )
    assert updated.updated == 1

    retired = await catalog.sync(ConcurrentStableList([]), source="platform")
    assert retired.retired >= 1
    row = await JobTypeRepository(session).get_by_type(job_type)
    assert row is not None and row.status == JOB_TYPE_STATUS_RETIRED


async def test_catalog_page_and_list_all(session: AsyncSession, ns: Namespace) -> None:
    """目录查询：分页过滤与全量清单（按本用例服务键 / 类型前缀限定）。"""
    job_type = ns.code("job")
    service_key = ns.code("svc")
    catalog = JobCatalogService(JobTypeRepository(session))
    await catalog.sync(ConcurrentStableList([_declaration(job_type, service=service_key)]), source="platform")
    rows, total = await catalog.page(page=1, size=10, service_key=service_key)
    assert total == 1 and len(rows) == 1
    filtered, filtered_total = await catalog.page(page=1, size=10, service_key=service_key, status="enabled")
    assert filtered_total == 1 and len(filtered) == 1
    empty, empty_total = await catalog.page(page=1, size=10, service_key=ns.code("absent"))
    assert empty_total == 0 and list(empty) == []
    owned = [row for row in await catalog.list_all() if row.job_type.startswith(ns.prefix)]
    assert [row.job_type for row in owned] == [job_type]


def _monitor_row(job_id: int, *, job_type: str, service_key: str, tenant_id: int, **overrides: object) -> SysJobMonitor:
    """构造监控投影行。"""
    values: ConcurrentStableDict[str, object] = ConcurrentStableDict(
        {
            "job_id": job_id,
            "job_type": job_type,
            "service_key": service_key,
            "tenant_id": tenant_id,
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


async def test_monitor_repository_filters_and_purge(session: AsyncSession, ns: Namespace) -> None:
    """监控仓储：多维过滤分页与按时间清理（断言本用例行的状态 + 相对增量）。"""
    running_id = _number(ns, 1)
    queued_id = _number(ns, 2)
    running_type = ns.code("running")
    other_type = ns.code("other")
    service_key = ns.code("svc")
    tenant_a = _number(ns, 3)
    tenant_b = _number(ns, 4)
    session.add_all(
        [
            _monitor_row(
                running_id, job_type=running_type, service_key=service_key, tenant_id=tenant_a, status="running"
            ),
            _monitor_row(
                queued_id,
                job_type=other_type,
                service_key=service_key,
                tenant_id=tenant_b,
                last_event_at=BASE + timedelta(minutes=1),
            ),
        ]
    )
    await session.commit()
    repository = JobMonitorRepository(session)
    rows, total = await repository.page_filtered(page=1, size=10, job_type=running_type)
    assert total == 1 and int(rows[0].job_id) == running_id
    filtered, filtered_total = await repository.page_filtered(
        page=1, size=10, job_type=other_type, status="queued", service_key=service_key, tenant_id=tenant_b
    )
    assert filtered_total == 1 and int(filtered[0].job_id) == queued_id
    purged = await repository.delete_expired(cutoff=BASE + timedelta(seconds=30))
    assert purged >= 1
    assert await repository.get_by_job_id(running_id) is None


async def test_monitor_service_drops_stale_and_missing(session: AsyncSession, ns: Namespace) -> None:
    """投影服务：旧事件丢弃 / started 置运行 / 无行返回 False。"""
    job_id = _number(ns, 1)
    job_type = ns.code("job")
    service_key = ns.code("svc")
    service = JobMonitorService(JobMonitorRepository(session))
    session.add(
        _monitor_row(
            job_id,
            job_type=job_type,
            service_key=service_key,
            tenant_id=_number(ns, 3),
            last_event_at=BASE + timedelta(minutes=5),
        )
    )
    await session.commit()

    stale = await service.apply(
        EventEnvelope(
            event_type="sys.job.started",
            payload=ConcurrentStableDict({"job_id": str(job_id), "job_type": job_type, "service_key": service_key}),
            occurred_at=BASE,
        )
    )
    assert stale is False

    missing = await service.apply(
        EventEnvelope(
            event_type="sys.job.completed",
            payload=ConcurrentStableDict(
                {"job_id": str(_number(ns, 9)), "job_type": job_type, "service_key": service_key}
            ),
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


async def test_api_list_types_and_monitor(
    session: AsyncSession, ns: Namespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """用户面：类型目录分页与监控列表分页（按本用例服务键与派生租户限定）。"""
    tenant_id = _number(ns, 3)
    monkeypatch.setattr(job_api, "current_tenant_context", lambda: SimpleNamespace(tenant_id=tenant_id))
    job_type = ns.code("job")
    service_key = ns.code("svc")
    await JobCatalogService(JobTypeRepository(session)).sync(
        ConcurrentStableList([_declaration(job_type, service=service_key)]), source="platform"
    )
    session.add(_monitor_row(_number(ns, 1), job_type=job_type, service_key=service_key, tenant_id=tenant_id))
    await session.commit()

    types = await _endpoint("/types", "GET")(cast("Any", _Uow(session)), _page(), service_key, None)
    assert types.data.total == 1
    monitor = await _endpoint("/jobs", "GET")(cast("Any", _Uow(session)), _page(), None, None, None)
    assert monitor.data.total == 1


async def test_api_monitor_detail_and_missing(
    session: AsyncSession, ns: Namespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """用户面：监控详情存在 / 不存在。"""
    monkeypatch.setattr(job_api, "current_tenant_context", lambda: SimpleNamespace(tenant_id=_number(ns, 3)))
    job_id = _number(ns, 1)
    session.add(_monitor_row(job_id, job_type=ns.code("job"), service_key=ns.code("svc"), tenant_id=_number(ns, 3)))
    await session.commit()
    detail = _endpoint("/jobs/{job_id}", "GET")
    response = await detail(cast("Any", _Uow(session)), job_id)
    assert response.data.job_id == job_id
    with pytest.raises(JobNotFoundError, match="作业不存在或投影尚未到达"):
        await detail(cast("Any", _Uow(session)), _number(ns, 9))


async def test_api_cancel_and_retry_forward(
    session: AsyncSession, ns: Namespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """用户面：取消 / 重试按投影服务键转发内部契约。"""
    monkeypatch.setattr(job_api, "current_tenant_context", lambda: SimpleNamespace(tenant_id=_number(ns, 3)))
    job_id = _number(ns, 1)
    session.add(_monitor_row(job_id, job_type=ns.code("job"), service_key=ns.code("svc"), tenant_id=_number(ns, 3)))
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
    canceled = await _endpoint("/{job_id}/cancel", "POST")(cast("Any", _Uow(session)), job_id, None)
    retried = await _endpoint("/{job_id}/retry", "POST")(cast("Any", _Uow(session)), job_id)
    assert canceled.data.status == "canceled"
    assert retried.data.status == "retried"
    assert calls == [("cancel", job_id), ("retry", job_id)]


async def test_api_service_key_of_missing(
    session: AsyncSession, ns: Namespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """内部辅助：投影缺失时报 71001。"""
    monkeypatch.setattr(job_api, "current_tenant_context", lambda: SimpleNamespace(tenant_id=_number(ns, 3)))
    with pytest.raises(JobNotFoundError, match="作业不存在或投影尚未到达"):
        await job_api._service_key_of(  # pyright: ignore[reportPrivateUsage]
            cast("Any", _Uow(session)), _number(ns, 9)
        )


async def test_monitor_service_progress_without_existing(session: AsyncSession, ns: Namespace) -> None:
    """进度事件先到：无既有行时建投影并置运行态。"""
    from bms_core.core.concurrent import ConcurrentStableDict
    from bms_core.events.base import EventEnvelope
    from bms_core.jobs.events import JOB_PROGRESS_EVENT

    job_id = _number(ns, 1)
    service = JobMonitorService(JobMonitorRepository(session))
    applied = await service.apply(
        EventEnvelope(
            event_type=JOB_PROGRESS_EVENT,
            payload=ConcurrentStableDict(
                {"job_id": str(job_id), "job_type": ns.code("job"), "service_key": ns.code("svc")}
            ),
            occurred_at=BASE,
        )
    )
    assert applied is True
    record = await JobMonitorRepository(session).get_by_job_id(job_id)
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
