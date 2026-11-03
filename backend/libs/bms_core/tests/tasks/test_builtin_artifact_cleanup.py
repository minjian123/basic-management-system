"""产物清理内置任务（04_03）：导出 / 打印两条任务各自提交对应作业。"""

from collections.abc import Callable

import pytest

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.exceptions import ServiceUnavailableError
from bms_core.tasks import builtin
from bms_core.tasks.spec import TaskContext, TaskRunSpec

pytestmark = pytest.mark.kiwi_id(2403)


class _FakeJobClient:
    """作业内部客户端替身（记录提交参数）。"""

    def __init__(self, *, job_id: int = 789, error: Exception | None = None) -> None:
        """初始化。

        Args:
            job_id: 返回的作业号。
            error: 预设异常。
        """
        self.job_id = job_id
        self.error = error
        self.calls: ConcurrentStableList[ConcurrentStableDict[str, object]] = ConcurrentStableList()

    async def submit(self, **kwargs: object) -> int:
        """记录提交并返回作业号（或抛预设异常）。

        Args:
            **kwargs: 提交参数。

        Returns:
            int: 作业号。

        Raises:
            Exception: 构造时预设的错误。
        """
        if self.error is not None:
            raise self.error
        self.calls.add(ConcurrentStableDict(kwargs))
        return self.job_id


def _ctx(*, tenant_id: int | None = 9) -> TaskContext:
    """构造执行上下文。

    Args:
        tenant_id: 租户主键（None 为平台链）。

    Returns:
        TaskContext: 执行上下文。
    """
    return TaskContext(
        run=TaskRunSpec(
            db_key="tenant_demo",
            task_id=1,
            log_id=1,
            run_id="r",
            code="cleanup_print_artifacts",
            handler="m:f",
            tenant_id=tenant_id,
        )
    )


def _factory(fake: _FakeJobClient) -> Callable[[object], _FakeJobClient]:
    """构造作业客户端替身工厂。

    Args:
        fake: 预设替身。

    Returns:
        Callable[[object], _FakeJobClient]: 工厂。
    """

    def build(client: object) -> _FakeJobClient:
        del client
        return fake

    return build


async def test_export_artifacts_submits_platform_cleanup(monkeypatch: pytest.MonkeyPatch) -> None:
    """导出产物清理：提交到 platform 服务的 `platform.export.cleanup`。"""
    fake = _FakeJobClient()
    monkeypatch.setattr(builtin, "JobInternalClient", _factory(fake))
    monkeypatch.setattr(builtin, "build_service_client", lambda: object())

    result = await builtin.run_cleanup_export_artifacts(_ctx(tenant_id=9))

    assert result.status == "success"
    assert result.output == "job_id=789"
    call = fake.calls[0]
    assert call["service_key"] == "platform"
    assert call["job_type"] == "platform.export.cleanup"
    assert call["tenant_id"] == 9
    assert str(call["idempotency_key"]).startswith("platform.export.cleanup:9:")


async def test_print_artifacts_submits_report_cleanup(monkeypatch: pytest.MonkeyPatch) -> None:
    """打印产物清理：提交到 report 服务的 `print.artifact.cleanup`；平台链幂等键用 platform 段。"""
    fake = _FakeJobClient()
    monkeypatch.setattr(builtin, "JobInternalClient", _factory(fake))
    monkeypatch.setattr(builtin, "build_service_client", lambda: object())

    result = await builtin.run_cleanup_print_artifacts(_ctx(tenant_id=None))

    assert result.status == "success"
    call = fake.calls[0]
    assert call["service_key"] == "report"
    assert call["job_type"] == "print.artifact.cleanup"
    assert call["tenant_id"] is None
    assert str(call["idempotency_key"]).startswith("print.artifact.cleanup:platform:")


async def test_cleanup_task_fails_when_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    """下游不可用：返回失败态（由调度器按策略重试提交），不抛异常。"""
    fake = _FakeJobClient(error=ServiceUnavailableError("down"))
    monkeypatch.setattr(builtin, "JobInternalClient", _factory(fake))
    monkeypatch.setattr(builtin, "build_service_client", lambda: object())

    result = await builtin.run_cleanup_print_artifacts(_ctx())

    assert result.status == "failed"
    assert "打印产物清理作业提交失败" in result.message
