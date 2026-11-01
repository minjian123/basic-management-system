"""孤儿回收内置任务迁移测试（Kiwi 2374）：由「触发型」改为「提交 file.cleanup_orphans 作业」."""

from collections.abc import Callable

import pytest

from bms_core.core.concurrent import ConcurrentStableDict
from bms_core.core.exceptions import ServiceUnavailableError
from bms_core.jobs.client import build_service_client
from bms_core.servicecall.base import BaseServiceClient
from bms_core.tasks import builtin
from bms_core.tasks.spec import TaskContext, TaskResult, TaskRunSpec

pytestmark = pytest.mark.kiwi_id(2374)


class _FakeJobClient:
    """作业内部客户端替身（记录提交参数）。"""

    def __init__(self, client: object, *, job_id: int = 456, error: Exception | None = None) -> None:
        self.client = client
        self.job_id = job_id
        self.error = error
        self.calls: list[dict[str, object]] = []

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
        self.calls.append(dict(kwargs))
        return self.job_id


def _ctx(*, tenant_id: int | None = 9) -> TaskContext:
    """构造执行上下文（执行体只提交作业）。

    Args:
        tenant_id: 租户主键。

    Returns:
        TaskContext: 执行上下文。
    """
    return TaskContext(
        run=TaskRunSpec(
            db_key="tenant_demo",
            task_id=1,
            log_id=1,
            run_id="r",
            code="cleanup_orphan_parts",
            handler="m:f",
            tenant_id=tenant_id,
        )
    )


def _job_client_factory(fake: _FakeJobClient) -> Callable[[object], _FakeJobClient]:
    """构造作业客户端替身工厂（忽略注入的底层客户端）。

    Args:
        fake: 预设替身。

    Returns:
        Callable[[object], _FakeJobClient]: 工厂。
    """

    def factory(client: object) -> _FakeJobClient:
        del client
        return fake

    return factory


async def test_task_submits_cleanup_job(monkeypatch: pytest.MonkeyPatch) -> None:
    """提交成功：返回成功态并带作业号；提交到 file 服务且带租户 / 幂等键。"""
    fake = _FakeJobClient(object())
    monkeypatch.setattr(builtin, "JobInternalClient", _job_client_factory(fake))
    monkeypatch.setattr(builtin, "build_service_client", lambda: object())

    result = await builtin.run_cleanup_orphan_parts(_ctx(tenant_id=9))

    assert isinstance(result, TaskResult)
    assert result.status == "success"
    assert "456" in result.message
    assert result.output == "job_id=456"
    call = fake.calls[0]
    assert call["service_key"] == "file"
    assert call["job_type"] == "file.cleanup_orphans"
    assert call["tenant_id"] == 9
    assert str(call["idempotency_key"]).startswith("file.cleanup_orphans:9:")


async def test_task_fails_when_submit_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    """提交失败（下游不可用）：返回失败态（由调度器按策略重试提交），不抛异常。"""
    fake = _FakeJobClient(object(), error=ServiceUnavailableError("down"))
    monkeypatch.setattr(builtin, "JobInternalClient", _job_client_factory(fake))
    monkeypatch.setattr(builtin, "build_service_client", lambda: object())

    result = await builtin.run_cleanup_orphan_parts(_ctx())
    assert result.status == "failed"
    assert "提交失败" in result.message


async def test_task_fails_when_client_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    """服务间调用未启用（provider 空）：构建客户端即失败 → 失败态。"""

    def _raise() -> BaseServiceClient:
        raise ServiceUnavailableError("服务间调用实现未启用")

    monkeypatch.setattr(builtin, "build_service_client", _raise)
    result = await builtin.run_cleanup_orphan_parts(_ctx())
    assert result.status == "failed"


def test_build_service_client_requires_provider() -> None:
    """服务间调用未启用（provider 空）：构建即报不可用。

    Raises:
        ServiceUnavailableError: 期望抛出。
    """
    from bms_core.core.config import get_settings

    settings = get_settings()
    original = settings.service_client.provider
    settings.service_client.provider = ""
    try:
        with pytest.raises(ServiceUnavailableError, match="未启用"):
            build_service_client()
    finally:
        settings.service_client.provider = original


def test_build_service_client_resolves_registered_provider() -> None:
    """服务间调用启用时：按 provider 解析出真实客户端（不依赖应用装配）。"""
    from bms_core.core.config import get_settings

    settings = get_settings()
    original = settings.service_client.provider
    settings.service_client.provider = "null"
    try:
        assert isinstance(build_service_client(), BaseServiceClient)
    finally:
        settings.service_client.provider = original


_ = ConcurrentStableDict
