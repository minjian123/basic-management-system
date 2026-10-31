"""孤儿回收内置任务测试（Kiwi 2374）：触发型执行体（下游成功 / 不可用 / 未启用）。"""

import pytest

from bms_core.core.concurrent import ConcurrentStableFrozenDict, ConcurrentStableList
from bms_core.core.exceptions import ServiceUnavailableError
from bms_core.core.serialization import stable_json_dumps
from bms_core.servicecall.base import BaseServiceClient, ServiceRequest, ServiceResponse
from bms_core.storage.maintenance import CLEANUP_ORPHANS_PATH, FILE_SERVICE_KEY, FileMaintenanceClient
from bms_core.tasks import builtin
from bms_core.tasks.spec import TaskContext, TaskResult, TaskRunSpec

pytestmark = pytest.mark.kiwi_id(2374)


class _Client(BaseServiceClient):
    """服务调用替身（记录请求；返回预设响应体）。"""

    def __init__(self, *, body: object = None, status_code: int = 200) -> None:
        self.body = body
        self.status_code = status_code
        self.calls: ConcurrentStableList[ServiceRequest] = ConcurrentStableList()

    async def call(self, request: ServiceRequest) -> ServiceResponse:
        """记录并返回预设响应。

        Args:
            request: 调用请求。

        Returns:
            ServiceResponse: 预设响应。
        """
        self.calls.add(request)
        content = b"" if self.body is None else stable_json_dumps(self.body).encode()
        return ServiceResponse(status_code=self.status_code, content=content)


def _ctx() -> TaskContext:
    """构造执行上下文（执行体不使用会话）。"""
    return TaskContext(
        run=TaskRunSpec(
            db_key="tenant_demo", task_id=1, log_id=1, run_id="r", code="cleanup_orphan_parts", handler="m:f"
        )
    )


async def test_task_reports_summary(monkeypatch: pytest.MonkeyPatch) -> None:
    """触发成功：返回成功态并带扫描 / 回收 / 失败摘要；请求打到 file 内部端点。"""
    client = _Client(body={"code": 0, "data": {"scanned": 3, "orphaned": 2, "failed": 1}})
    monkeypatch.setattr(builtin, "build_service_client", lambda: client)

    result = await builtin.run_cleanup_orphan_parts(_ctx())

    assert isinstance(result, TaskResult)
    assert result.status == "success"
    assert "扫描 3 / 回收 2 / 失败 1" in result.message
    assert result.output == "scanned=3 orphaned=2 failed=1"
    assert client.calls[0].path == CLEANUP_ORPHANS_PATH
    assert client.calls[0].service == FILE_SERVICE_KEY
    assert client.calls[0].method == "POST"


async def test_task_fails_when_downstream_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    """下游不可用：返回失败态（由调度器按策略重试），不抛异常。"""
    client = _Client(status_code=503)
    monkeypatch.setattr(builtin, "build_service_client", lambda: client)

    result = await builtin.run_cleanup_orphan_parts(_ctx())
    assert result.status == "failed"
    assert "触发失败" in result.message


async def test_task_fails_when_client_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    """服务间调用未启用（provider 空）：构建客户端即失败 → 失败态。"""

    def _raise() -> BaseServiceClient:
        raise ServiceUnavailableError("服务间调用实现未启用")

    monkeypatch.setattr(builtin, "build_service_client", _raise)
    result = await builtin.run_cleanup_orphan_parts(_ctx())
    assert result.status == "failed"


async def test_maintenance_client_rejects_bad_payload() -> None:
    """响应缺少 data 对象：视为不可用（不静默返回 0）。

    Raises:
        ServiceUnavailableError: 期望抛出。
    """
    with pytest.raises(ServiceUnavailableError):
        await FileMaintenanceClient(_Client(body={"code": 0})).cleanup_orphans()


async def test_maintenance_client_passes_limit() -> None:
    """带上限调用时写入查询参数。"""
    client = _Client(body={"code": 0, "data": {"scanned": 0, "orphaned": 0, "failed": 0}})
    summary = await FileMaintenanceClient(client).cleanup_orphans(limit=50)
    assert summary.scanned == 0
    assert client.calls[0].query == ConcurrentStableFrozenDict({"limit": "50"})


async def test_maintenance_client_rejects_non_object_payload() -> None:
    """响应体不是 JSON 对象：视为不可用（不按缺字段静默补 0）。

    Raises:
        ServiceUnavailableError: 期望抛出。
    """
    with pytest.raises(ServiceUnavailableError):
        await FileMaintenanceClient(_Client(body=[1, 2, 3])).cleanup_orphans()


def test_build_service_client_requires_provider() -> None:
    """服务间调用未启用（provider 空）：构建即报不可用（离线执行体据此转失败态）。

    Raises:
        ServiceUnavailableError: 期望抛出。
    """
    from bms_core.core.config import get_settings

    settings = get_settings()
    original = settings.service_client.provider
    settings.service_client.provider = ""
    try:
        with pytest.raises(ServiceUnavailableError, match="未启用"):
            builtin.build_service_client()
    finally:
        settings.service_client.provider = original


def test_build_service_client_resolves_registered_provider() -> None:
    """服务间调用启用时：按 provider 解析出真实客户端（不依赖应用装配）。"""
    from bms_core.core.config import get_settings

    settings = get_settings()
    original = settings.service_client.provider
    settings.service_client.provider = "null"
    try:
        assert isinstance(builtin.build_service_client(), BaseServiceClient)
    finally:
        settings.service_client.provider = original
