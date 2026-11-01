"""作业内部契约路由用例：提交 / 详情 / 取消 / 重试的错误码映射。"""

from __future__ import annotations

from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import Any, cast

import pytest

from bms_core.core.exceptions import JobNotCancelableError, JobNotFoundError, JobNotRetryableError
from bms_core.jobs import api as job_api
from bms_core.jobs.api import build_job_internal_router
from bms_core.schemas.job import JobCancelRequest, JobSubmitRequest

pytestmark = pytest.mark.kiwi_id(2375)


class _Record:
    """作业行替身。"""

    id = 42
    job_type = "demo.echo"
    status = "running"
    tenant_id = 9
    progress_done = 1
    progress_total = 2
    attempts = 1
    max_attempts = 3
    error = None
    result = None
    created_at = None
    started_at = None
    finished_at = None


class _Runner:
    """作业提交器替身：按预设返回。"""

    def __init__(
        self, *, submit_record: object = None, cancel_status: str = "canceled", retry_status: str = "retried"
    ) -> None:
        self.submit_record = submit_record or _Record()
        self.cancel_status = cancel_status
        self.retry_status = retry_status

    async def submit(self, session: object, submission: object, *, tenant_id: int | None = None) -> object:
        """返回预设作业行。"""
        del session, submission, tenant_id
        return self.submit_record

    async def cancel(self, session: object, job_id: int, *, reason: str | None = None) -> str:
        """返回预设取消状态。"""
        del session, job_id, reason
        return self.cancel_status

    async def retry(self, session: object, job_id: int) -> str:
        """返回预设重试状态。"""
        del session, job_id
        return self.retry_status


class _Uow:
    """工作单元替身：会话可为任意对象。"""

    session = object()

    @asynccontextmanager
    async def begin(self) -> AsyncGenerator[None]:
        """空事务上下文。"""
        yield


def _endpoint(router: Any, path: str, method: str) -> Callable[..., Any]:
    """按路径后缀与方法取路由处理函数。"""
    for route in router.routes:
        if route.path.endswith(path) and method in route.methods:
            return cast("Callable[..., Any]", route.endpoint)
    raise AssertionError(f"未找到路由：{method} {path}")


@pytest.fixture
def router(monkeypatch: pytest.MonkeyPatch) -> Any:
    """构造路由并固定租户上下文。"""
    monkeypatch.setattr(job_api, "current_tenant_context", lambda: SimpleNamespace(tenant_id=9))
    return build_job_internal_router(runner_factory=lambda: cast("Any", _Runner()))


async def test_submit_returns_job_id(router: Any) -> None:
    """提交：负载转插入序集合，返回字符串作业号。"""
    submit = _endpoint(router, "", "POST")
    request = JobSubmitRequest(job_type="demo.echo", payload={"n": 1}, priority=2, idempotency_key="k")
    response = await submit(cast("Any", _Uow()), request)
    assert response.data == {"job_id": "42"}


async def test_get_job_and_not_found(router: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    """详情：存在返回本地快照；不存在报 71001。"""
    get_job = _endpoint(router, "/{job_id}", "GET")

    async def _found(session: object, job_id: int) -> object:
        del session, job_id
        return _Record()

    monkeypatch.setattr(job_api.store, "get_job", _found)
    response = await get_job(cast("Any", _Uow()), 42)
    assert response.data.job_id == 42

    async def _missing(session: object, job_id: int) -> None:
        del session, job_id
        return None

    monkeypatch.setattr(job_api.store, "get_job", _missing)
    with pytest.raises(JobNotFoundError, match="作业不存在"):
        await get_job(cast("Any", _Uow()), 42)


async def test_cancel_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    """取消：正常返回状态；missing 报 71001；terminal 报 71003。"""
    monkeypatch.setattr(job_api, "current_tenant_context", lambda: SimpleNamespace(tenant_id=9))

    async def _run(status: str, request: JobCancelRequest | None = None) -> Any:
        router = build_job_internal_router(runner_factory=lambda: cast("Any", _Runner(cancel_status=status)))
        return await _endpoint(router, "/{job_id}/cancel", "POST")(cast("Any", _Uow()), 42, request)

    response = await _run("canceled", JobCancelRequest(reason="user"))
    assert response.data.status == "canceled"
    with pytest.raises(JobNotFoundError):
        await _run("missing")
    with pytest.raises(JobNotCancelableError):
        await _run("terminal")


async def test_retry_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    """重试：正常返回 retried；missing 报 71001；其他状态报 71004。"""
    monkeypatch.setattr(job_api, "current_tenant_context", lambda: SimpleNamespace(tenant_id=9))

    async def _run(status: str) -> Any:
        router = build_job_internal_router(runner_factory=lambda: cast("Any", _Runner(retry_status=status)))
        return await _endpoint(router, "/{job_id}/retry", "POST")(cast("Any", _Uow()), 42)

    assert (await _run("retried")).data.status == "retried"
    with pytest.raises(JobNotFoundError):
        await _run("missing")
    with pytest.raises(JobNotRetryableError):
        await _run("terminal")
