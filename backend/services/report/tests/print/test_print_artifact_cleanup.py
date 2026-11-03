"""打印产物清理作业用例（04_03）：回收 / 覆盖防护 / 幂等 / 失败 / 分页 / 取消。"""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast

import pytest
import pytest_asyncio
from sqlalchemy import Table, delete
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from bms_core.config.http import HttpConfigSource
from bms_core.config.null import NullConfigSource
from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.config import get_settings
from bms_core.core.exceptions import ServiceUnavailableError
from bms_core.jobs.base import JobContext
from bms_core.models.job import JOB_STATUS_SUCCEEDED, SysJob
from bms_core.print.base import PRINT_CONTENT_TYPE
from bms_core.print.limits import PrintLimits
from bms_core.servicecall.base import BaseServiceClient
from bms_core.servicecall.null import NullServiceClient
from bms_core.storage.base import BaseObjectStorage
from bms_core.storage.local import LocalObjectStorage
from bms_core.testing.schema import ensure_tables
from bms_report.domains.report.artifact_cleanup import (
    JOB_TYPE,
    SOURCE_JOB_TYPE,
    PrintArtifactCleanupJob,
)
from bms_report.domains.report.repositories.job import (
    PrintJobRepository,
    is_expired,
    object_keys_of,
    with_expired,
)

pytestmark = [
    pytest.mark.kiwi_id(2403),
    pytest.mark.own_db("清空 sys_job 才能断言精确计数；本套件独占该表的作业写入"),
    pytest.mark.usefixtures("serial_db_write"),
]

_TTL = 600
"""用例保留期（10 分钟）。"""


@dataclass
class _Env:
    """清理作业测试环境。"""

    factory: async_sessionmaker[AsyncSession]
    storage: LocalObjectStorage
    root: Path


@pytest_asyncio.fixture
async def env(
    shared_tenant_engine: AsyncEngine,
    shared_tenant_db_url: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[_Env]:
    """自建租户库 + 本地对象存储（每个用例前清空 `sys_job`）。"""
    monkeypatch.setenv("BMS_DATABASE__TENANTS__URL", shared_tenant_db_url)
    monkeypatch.setenv("BMS_STORAGE__OPTIONS__ROOT", str(tmp_path / "storage"))
    await ensure_tables(shared_tenant_engine, cast("list[Table]", [SysJob.__table__]))
    factory = async_sessionmaker(shared_tenant_engine, expire_on_commit=False)
    async with factory() as session:
        await session.execute(delete(SysJob).where(SysJob.job_type == SOURCE_JOB_TYPE))
        await session.commit()
    root = tmp_path / "storage"
    yield _Env(factory=factory, storage=LocalObjectStorage(root=root), root=root)


def _result(keys: ConcurrentStableList[str], **extra: object) -> str:
    """构造作业结果 JSON（items 里只保留清理关心的 object_key）。

    Args:
        keys: 产物 key 列表。
        **extra: 追加字段。

    Returns:
        str: 结果 JSON。
    """
    payload: ConcurrentStableDict[str, object] = ConcurrentStableDict(
        {
            "total": len(keys),
            "succeeded": len(keys),
            "failed": 0,
            "items": [
                {"object_key": key, "file_name": "a.pdf", "size": 1, "content_type": PRINT_CONTENT_TYPE} for key in keys
            ],
        }
    )
    for field, value in extra.items():
        payload.set(field, value)
    return json.dumps(dict(payload), ensure_ascii=False)


async def _add_job(
    env: _Env,
    *,
    result: str | None,
    finished_at: datetime | None,
    status: str = JOB_STATUS_SUCCEEDED,
) -> int:
    """插入一条打印作业记录。

    Args:
        env: 测试环境。
        result: 结果 JSON（None 表示无结果）。
        finished_at: 完成时刻（None 表示未完成）。
        status: 作业状态。

    Returns:
        int: 作业主键。
    """
    async with env.factory() as session:
        job = SysJob(
            job_type=SOURCE_JOB_TYPE,
            service_key="report",
            domain_key="report",
            status=status,
            payload="{}",
            result=result,
            finished_at=finished_at,
        )
        session.add(job)
        await session.commit()
        return int(job.id)


async def _result_of(env: _Env, job_id: int) -> str | None:
    """回读作业结果文本。

    Args:
        env: 测试环境。
        job_id: 作业主键。

    Returns:
        str | None: 结果文本。
    """
    async with env.factory() as session:
        row = await session.get(SysJob, job_id)
        return None if row is None else row.result


def _context(env: _Env, *, cancel: bool = False) -> JobContext:
    """构造作业上下文（会话由 factory 开合）。

    Args:
        env: 测试环境。
        cancel: 是否已请求取消。

    Returns:
        JobContext: 作业上下文。
    """

    @asynccontextmanager
    async def _open() -> AsyncGenerator[AsyncSession]:
        async with env.factory() as session:
            yield session

    async def _report(done: int, total: int | None) -> None:
        return None

    async def _cancelled() -> bool:
        return cancel

    return JobContext(
        job_id=1,
        job_type=JOB_TYPE,
        service_key="report",
        db_key="tenant_demo",
        payload=ConcurrentStableDict[str, object](),
        max_attempts=1,
        open_session=_open,
        progress_reporter=_report,
        cancel_checker=_cancelled,
    )


def _job(env: _Env, *, batch: int = 100, storage: LocalObjectStorage | None = None) -> PrintArtifactCleanupJob:
    """构造清理作业（注入本地存储与固定参数）。

    Args:
        env: 测试环境。
        batch: 单批作业数。
        storage: 存储实现（None 用环境默认）。

    Returns:
        PrintArtifactCleanupJob: 作业实例。
    """
    return PrintArtifactCleanupJob(
        storage=storage if storage is not None else env.storage,
        limits=PrintLimits(artifact_ttl=_TTL, cleanup_batch_size=batch),
    )


def _ago(seconds: int) -> datetime:
    """构造相对当前时刻的过期时间（UTC naive）。

    Args:
        seconds: 距今秒数（正数表示更早）。

    Returns:
        datetime: 时间点。
    """
    return datetime.now(UTC).replace(tzinfo=None) - timedelta(seconds=seconds)


async def test_cleanup_deletes_expired_artifact(env: _Env) -> None:
    """主路径：过期作业产物被删并标记；未过期作业产物原样保留。"""
    stale = "demo/prints/generic_document/A001.pdf"
    fresh = "demo/prints/generic_document/A002.pdf"
    await env.storage.put(stale, b"PDF", content_type=PRINT_CONTENT_TYPE)
    await env.storage.put(fresh, b"PDF", content_type=PRINT_CONTENT_TYPE)
    job_id = await _add_job(env, result=_result(ConcurrentStableList((stale,))), finished_at=_ago(_TTL + 60))
    await _add_job(env, result=_result(ConcurrentStableList((fresh,))), finished_at=_ago(60))

    result = await _job(env).run(_context(env))

    assert result.status == "succeeded"
    output = cast("ConcurrentStableDict[str, object]", result.output)
    assert output["scanned"] == 1
    assert output["cleaned"] == 1
    assert output["marked"] == 1
    assert await env.storage.exists(stale) is False
    assert await env.storage.exists(fresh) is True
    assert is_expired(await _result_of(env, job_id)) is True


async def test_cleanup_skips_key_referenced_by_newer_job(env: _Env) -> None:
    """覆盖防护：同一 key 被更晚作业引用时跳过、不删对象、不标记（重打不误删）。"""
    key = "demo/prints/generic_document/A003.pdf"
    await env.storage.put(key, b"PDF-NEW", content_type=PRINT_CONTENT_TYPE)
    old_id = await _add_job(env, result=_result(ConcurrentStableList((key,))), finished_at=_ago(_TTL + 600))
    await _add_job(env, result=_result(ConcurrentStableList((key,))), finished_at=_ago(30))

    result = await _job(env).run(_context(env))

    output = cast("ConcurrentStableDict[str, object]", result.output)
    assert output["cleaned"] == 0
    assert output["skipped"] == 1
    assert output["marked"] == 0
    assert await env.storage.exists(key) is True
    assert is_expired(await _result_of(env, old_id)) is False


async def test_cleanup_skips_already_expired_job(env: _Env) -> None:
    """已标记 `expired_at` 的作业：跳过，不重复删、不重复写。"""
    key = "demo/prints/generic_document/A004.pdf"
    await env.storage.put(key, b"PDF", content_type=PRINT_CONTENT_TYPE)
    marked = _result(ConcurrentStableList((key,)), expired_at="2026-01-01T00:00:00Z")
    job_id = await _add_job(env, result=marked, finished_at=_ago(_TTL + 60))

    result = await _job(env).run(_context(env))

    output = cast("ConcurrentStableDict[str, object]", result.output)
    assert output["skipped"] == 1
    assert output["cleaned"] == 0
    assert await env.storage.exists(key) is True
    assert await _result_of(env, job_id) == marked


async def test_cleanup_marks_job_without_items(env: _Env) -> None:
    """结果无 items：只标记、不删对象。"""
    job_id = await _add_job(env, result='{"total": 0}', finished_at=_ago(_TTL + 60))

    result = await _job(env).run(_context(env))

    output = cast("ConcurrentStableDict[str, object]", result.output)
    assert output["cleaned"] == 0
    assert output["marked"] == 1
    assert is_expired(await _result_of(env, job_id)) is True


async def test_cleanup_fails_fast_and_leaves_unmarked(env: _Env) -> None:
    """删除失败：立即抛出（整作业失败），该作业不写标记（下轮可重试）。"""

    class _Failing(LocalObjectStorage):
        """对指定 key 删除抛错。"""

        async def delete(self, key: str) -> None:
            """删除（指定 key 抛错）。

            Args:
                key: 对象 key。

            Raises:
                OSError: 命中失败 key。
            """
            if key.endswith("A006.pdf"):
                raise OSError("storage down")
            await super().delete(key)

    broken = "demo/prints/generic_document/A006.pdf"
    later = "demo/prints/generic_document/A007.pdf"
    await env.storage.put(broken, b"PDF", content_type=PRINT_CONTENT_TYPE)
    await env.storage.put(later, b"PDF", content_type=PRINT_CONTENT_TYPE)
    job_id = await _add_job(
        env,
        result=_result(ConcurrentStableList((broken, later))),
        finished_at=_ago(_TTL + 60),
    )
    storage = _Failing(root=env.root)

    with pytest.raises(OSError, match="storage down"):
        await _job(env, storage=storage).run(_context(env))

    assert await env.storage.exists(broken) is True
    assert await env.storage.exists(later) is True
    assert is_expired(await _result_of(env, job_id)) is False


async def test_cleanup_handles_multiple_batches(env: _Env) -> None:
    """超过单批上限：分多批处理完（offset 推进）。"""
    keys = ConcurrentStableList(f"demo/prints/generic_document/B00{index}.pdf" for index in range(3))
    for key in keys:
        await env.storage.put(key, b"PDF", content_type=PRINT_CONTENT_TYPE)
        await _add_job(env, result=_result(ConcurrentStableList((key,))), finished_at=_ago(_TTL + 60))

    result = await _job(env, batch=2).run(_context(env))

    output = cast("ConcurrentStableDict[str, object]", result.output)
    assert output["cleaned"] == 3
    for key in keys:
        assert await env.storage.exists(key) is False


async def test_cleanup_canceled_between_batches(env: _Env) -> None:
    """批间发现取消即停止，仍返回已处理汇总。"""
    key = "demo/prints/generic_document/A008.pdf"
    await env.storage.put(key, b"PDF", content_type=PRINT_CONTENT_TYPE)
    await _add_job(env, result=_result(ConcurrentStableList((key,))), finished_at=_ago(_TTL + 60))

    result = await _job(env).run(_context(env, cancel=True))

    assert result.status == "succeeded"
    output = cast("ConcurrentStableDict[str, object]", result.output)
    assert output["cleaned"] == 1


async def test_cleanup_no_expired_jobs(env: _Env) -> None:
    """无过期作业：空批直接返回，全零汇总。"""
    result = await _job(env).run(_context(env))
    output = cast("ConcurrentStableDict[str, object]", result.output)
    assert output == {"scanned": 0, "cleaned": 0, "skipped": 0, "marked": 0}


def test_object_keys_dedup_and_parse_edges() -> None:
    """结果解析：重复 key 去重；空 / 非法 / 非对象 / items 非数组一律空集合。"""
    duplicated = json.dumps({"items": [{"object_key": "k1"}, {"object_key": "k1"}, {"object_key": ""}]})
    assert list(object_keys_of(duplicated)) == ["k1"]
    assert list(object_keys_of(None)) == []
    assert list(object_keys_of("not-json")) == []
    assert list(object_keys_of("[1, 2]")) == []
    assert list(object_keys_of('{"items": "x"}')) == []
    assert list(object_keys_of('{"items": [{"object_key": 1}, "x"]}')) == []


def test_with_expired_is_idempotent() -> None:
    """标记写入：首次追加 `expired_at`；已标记原样返回；空结果补成对象。"""
    created = with_expired('{"a": 1}')
    assert is_expired(created) is True
    assert with_expired(created) == created
    assert is_expired(with_expired(None)) is True
    assert with_expired(None) is not None


async def test_mark_expired_handles_missing_and_marked(env: _Env) -> None:
    """标记：作业不存在返回 False；已标记不重复写。"""
    marked = _result(ConcurrentStableList(("k",)), expired_at="2026-01-01T00:00:00Z")
    job_id = await _add_job(env, result=marked, finished_at=_ago(_TTL + 60))
    async with env.factory() as session, session.begin():
        repository = PrintJobRepository(session)
        assert await repository.mark_expired(999_999_999) is False
        assert await repository.mark_expired(job_id) is False


def test_worker_side_resolvers(monkeypatch: pytest.MonkeyPatch) -> None:
    """worker 侧解析：客户端不可用回落空实现（参数源回落占位）；可用则用 HTTP 参数源。"""
    from bms_report.domains.report import artifact_cleanup as module

    def _raise() -> BaseServiceClient:
        raise ServiceUnavailableError("服务间调用实现未启用")

    monkeypatch.setattr(module, "build_service_client", _raise)
    assert isinstance(module._service_client(), NullServiceClient)  # pyright: ignore[reportPrivateUsage]
    assert isinstance(module._config_source(), NullConfigSource)  # pyright: ignore[reportPrivateUsage]

    fake = cast("BaseServiceClient", object())
    monkeypatch.setattr(module, "build_service_client", lambda: fake)
    assert module._service_client() is fake  # pyright: ignore[reportPrivateUsage]
    assert isinstance(module._config_source(), HttpConfigSource)  # pyright: ignore[reportPrivateUsage]


def test_storage_resolves_plugin(monkeypatch: pytest.MonkeyPatch) -> None:
    """对象存储按配置解析（worker 进程按需装配插件）。"""
    from bms_report.domains.report import artifact_cleanup as module

    fake = cast("BaseObjectStorage", object())

    def _resolve(*args: object, **kwargs: object) -> BaseObjectStorage:
        """解析替身（忽略入参）。

        Args:
            *args: 位置参数。
            **kwargs: 关键字参数。

        Returns:
            BaseObjectStorage: 固定替身。
        """
        del args, kwargs
        return fake

    monkeypatch.setattr(module, "resolve_plugin", _resolve)
    assert module._storage(get_settings()) is fake  # pyright: ignore[reportPrivateUsage]
