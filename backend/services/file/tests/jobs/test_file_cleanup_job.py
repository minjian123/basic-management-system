"""文件服务孤儿回收作业护栏（Kiwi 2384）：进度上报 / 结果摘要 / 异常透传。"""

from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager
from typing import Any

import pytest

from bms_core.core.concurrent import ConcurrentStableDict
from bms_core.jobs.base import JobContext
from bms_file.domains.file.jobs import CleanupOrphansJob
from bms_file.domains.file.schemas.file import CleanupResult

pytestmark = pytest.mark.kiwi_id(2384)


class _FakeService:
    """FileService 替身：返回预设清理结果。"""

    def __init__(self, result: CleanupResult) -> None:
        self.result = result

    async def cleanup_orphans(self) -> CleanupResult:
        """返回预设结果。

        Returns:
            CleanupResult: 预设结果。
        """
        return self.result


class _Boom:
    """FileService 替身：清理即抛异常。"""

    async def cleanup_orphans(self) -> CleanupResult:
        """抛异常以验证向上透传。

        Raises:
            RuntimeError: 固定错误。
        """
        raise RuntimeError("storage down")


def _service_factory(result: CleanupResult) -> Callable[..., _FakeService]:
    """构造 FileService 替身工厂（忽略注入的存储 / 分片 / 客户端参数）。

    Args:
        result: 预设清理结果。

    Returns:
        Callable[..., _FakeService]: 工厂（供 `monkeypatch.setattr` 替换类）。
    """

    def factory(**kwargs: Any) -> _FakeService:
        del kwargs
        return _FakeService(result)

    return factory


def _boom_factory(**kwargs: Any) -> _Boom:
    """构造抛异常的 FileService 替身工厂（忽略注入参数）。"""
    del kwargs
    return _Boom()


def _context(progress: list[tuple[int, int | None]]) -> JobContext:
    """构造执行上下文（会话开合口返回 None，服务已被替身绕过）。

    Args:
        progress: 进度记录器。

    Returns:
        JobContext: 执行上下文。
    """

    @asynccontextmanager
    async def _session() -> AsyncGenerator[Any]:
        yield object()

    async def _report(done: int, total: int | None) -> None:
        progress.append((done, total))

    return JobContext(
        job_id=1,
        job_type="file.cleanup_orphans",
        service_key="file",
        db_key="tenant_demo",
        tenant_id=7,
        open_session=_session,
        progress_reporter=_report,
    )


async def test_run_reports_progress_and_result(monkeypatch: pytest.MonkeyPatch) -> None:
    """执行完成：进度为（回收数 / 扫描数），结果摘要含三项计数。"""
    job = CleanupOrphansJob()
    monkeypatch.setattr(
        "bms_file.domains.file.jobs.FileService",
        _service_factory(CleanupResult(scanned=3, orphaned=2, failed=1)),
    )
    progress: list[tuple[int, int | None]] = []
    result = await job.run(_context(progress))
    assert result.status == "succeeded"
    assert progress == [(2, 3)]
    assert result.output == ConcurrentStableDict({"scanned": 3, "orphaned": 2, "failed": 1})
    assert "扫描 3 / 回收 2 / 失败 1" in result.message


async def test_run_propagates_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """服务异常不吞：向上抛出，由执行器统一转失败 / 重试。

    Raises:
        RuntimeError: 期望抛出。
    """

    job = CleanupOrphansJob()
    monkeypatch.setattr("bms_file.domains.file.jobs.FileService", _boom_factory)
    with pytest.raises(RuntimeError, match="storage down"):
        await job.run(_context([]))
