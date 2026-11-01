"""作业监控消费组与平台目录启动钩子用例：注册表缓存 / 消费者 / 清单定位 / 降级。"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import Any, cast

import pytest
from sqlalchemy.exc import SQLAlchemyError

from bms_core.core.concurrent import ConcurrentStableList
from bms_platform.domains.job import jobs as job_jobs
from bms_platform.domains.job.services import bootstrap as job_bootstrap
from bms_platform.domains.task.services import task as task_service

pytestmark = pytest.mark.kiwi_id(2386)


def test_monitor_registry_cache_and_reset() -> None:
    """引擎注册表懒建并缓存；重置后重建。"""
    job_jobs.reset_monitor_registry()
    first = job_jobs._monitor_registry()  # pyright: ignore[reportPrivateUsage]
    assert job_jobs._monitor_registry() is first  # pyright: ignore[reportPrivateUsage]
    job_jobs.reset_monitor_registry()
    assert job_jobs._monitor_registry() is not first  # pyright: ignore[reportPrivateUsage]


def test_consumer_event_type_and_factory() -> None:
    """消费者：事件类型可读；工厂每次返回独立实例。"""
    consumer = job_jobs.JobMonitorConsumer("sys.job.started")
    assert consumer.event_type == "sys.job.started"
    build = job_jobs._factory("sys.job.started")  # pyright: ignore[reportPrivateUsage]
    assert build() is not build()


def test_event_consumer_records_cover_four_events() -> None:
    """消费组声明：四条生命周期事件各一条，均有序。"""
    records = job_jobs.event_consumer_records()
    assert len(records) == 4
    assert {record.event_type for record in records} == {
        "sys.job.submitted",
        "sys.job.started",
        "sys.job.progress",
        "sys.job.completed",
    }
    assert all(record.ordered for record in records)


async def test_consumer_consume_applies_projection(monkeypatch: pytest.MonkeyPatch) -> None:
    """消费：打开平台库会话并应用投影。"""
    applied: ConcurrentStableList[object] = ConcurrentStableList()

    @asynccontextmanager
    async def _scope(*args: object, **kwargs: object) -> AsyncGenerator[Any]:
        del args, kwargs

        class _Session:
            def begin(self) -> Any:
                @asynccontextmanager
                async def _tx() -> AsyncGenerator[None]:
                    yield None

                return _tx()

        yield _Session()

    class _Service:
        def __init__(self, repository: object) -> None:
            del repository

        async def apply(self, event: object) -> bool:
            applied.append(event)
            return True

    monkeypatch.setattr(job_jobs, "session_scope", _scope)
    monkeypatch.setattr(job_jobs, "JobMonitorService", _Service)
    event = SimpleNamespace(event_type="sys.job.started")
    await job_jobs.JobMonitorConsumer("sys.job.started").consume(cast("Any", event))
    assert applied == [event]


def test_platform_manifest_path_found_and_missing(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
    """清单定位：按服务名命中；缺失即拒启。"""
    target = tmp_path / "platform.toml"
    target.write_text("", encoding="utf-8")

    def _paths() -> ConcurrentStableList[Any]:
        return ConcurrentStableList([target])

    monkeypatch.setattr(job_bootstrap, "local_manifest_paths", _paths)
    assert job_bootstrap._platform_manifest_path("platform") == target  # pyright: ignore[reportPrivateUsage]
    with pytest.raises(Exception, match="平台自身清单缺失"):
        job_bootstrap._platform_manifest_path("absent")  # pyright: ignore[reportPrivateUsage]


async def test_bootstrap_skips_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    """启动钩子：未启用注册时直接跳过。"""
    app = SimpleNamespace(
        state=SimpleNamespace(settings=SimpleNamespace(registry=SimpleNamespace(register_on_startup=False)))
    )
    await job_bootstrap.bootstrap_job_types(cast("Any", app))


async def test_bootstrap_skips_without_declarations(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
    """启动钩子：清单无作业声明时跳过。"""
    target = tmp_path / "platform.toml"
    target.write_text("", encoding="utf-8")

    def _paths() -> ConcurrentStableList[Any]:
        return ConcurrentStableList([target])

    def _manifest(path: object) -> Any:
        del path
        return SimpleNamespace(jobs=[])

    monkeypatch.setattr(job_bootstrap, "local_manifest_paths", _paths)
    monkeypatch.setattr(job_bootstrap, "load_product_manifest", _manifest)
    app = SimpleNamespace(
        state=SimpleNamespace(
            settings=SimpleNamespace(
                registry=SimpleNamespace(register_on_startup=True),
                app=SimpleNamespace(service="platform"),
            )
        )
    )
    await job_bootstrap.bootstrap_job_types(cast("Any", app))


async def test_bootstrap_degrades_when_database_unavailable(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
    """启动钩子：平台库不可用时降级放行（目录下次启动补齐）。"""
    target = tmp_path / "platform.toml"
    target.write_text("", encoding="utf-8")

    def _paths() -> ConcurrentStableList[Any]:
        return ConcurrentStableList([target])

    def _manifest(path: object) -> Any:
        del path
        return SimpleNamespace(jobs=[SimpleNamespace(job_type="x")])

    monkeypatch.setattr(job_bootstrap, "local_manifest_paths", _paths)
    monkeypatch.setattr(job_bootstrap, "load_product_manifest", _manifest)

    @asynccontextmanager
    async def _scope(*args: object, **kwargs: object) -> AsyncGenerator[Any]:
        del args, kwargs
        raise SQLAlchemyError("db down")
        yield  # pragma: no cover

    monkeypatch.setattr(job_bootstrap, "session_scope", _scope)
    app = SimpleNamespace(
        state=SimpleNamespace(
            settings=SimpleNamespace(
                registry=SimpleNamespace(register_on_startup=True),
                app=SimpleNamespace(service="platform"),
            ),
            engine_registry=object(),
            session_factory=object(),
        )
    )
    await job_bootstrap.bootstrap_job_types(cast("Any", app))


def test_task_service_db_key_reads_context(monkeypatch: pytest.MonkeyPatch) -> None:
    """任务服务：作业负载库键取自当前租户上下文。"""
    monkeypatch.setattr(task_service, "current_tenant_context", lambda: SimpleNamespace(db_key="tenant_demo_platform"))
    service = task_service.TaskService.__new__(task_service.TaskService)
    assert service._db_key() == "tenant_demo_platform"  # pyright: ignore[reportPrivateUsage]


async def test_bootstrap_syncs_declarations(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
    """启动钩子：正常路径同步目录并记录结果。"""
    target = tmp_path / "platform.toml"
    target.write_text("", encoding="utf-8")

    def _paths() -> ConcurrentStableList[Any]:
        return ConcurrentStableList([target])

    def _manifest(path: object) -> Any:
        del path
        return SimpleNamespace(jobs=[SimpleNamespace(job_type="x")])

    monkeypatch.setattr(job_bootstrap, "local_manifest_paths", _paths)
    monkeypatch.setattr(job_bootstrap, "load_product_manifest", _manifest)
    synced: ConcurrentStableList[object] = ConcurrentStableList()

    class _Service:
        def __init__(self, repository: object) -> None:
            del repository

        async def sync(self, declarations: object, *, source: str) -> object:
            del source
            synced.append(declarations)
            return SimpleNamespace(created=1, updated=0, unchanged=0, retired=0)

    @asynccontextmanager
    async def _scope(*args: object, **kwargs: object) -> AsyncGenerator[Any]:
        del args, kwargs

        class _Session:
            def begin(self) -> Any:
                @asynccontextmanager
                async def _tx() -> AsyncGenerator[None]:
                    yield None

                return _tx()

        yield _Session()

    monkeypatch.setattr(job_bootstrap, "JobCatalogService", _Service)
    monkeypatch.setattr(job_bootstrap, "session_scope", _scope)
    app = SimpleNamespace(
        state=SimpleNamespace(
            settings=SimpleNamespace(
                registry=SimpleNamespace(register_on_startup=True),
                app=SimpleNamespace(service="platform"),
            ),
            engine_registry=object(),
            session_factory=object(),
        )
    )
    await job_bootstrap.bootstrap_job_types(cast("Any", app))
    assert synced
