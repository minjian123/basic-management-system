"""作业内部契约客户端用例：提交 / 取消 / 重试 / 详情与统一响应解析。"""

from __future__ import annotations

import json
from typing import cast

import pytest

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.exceptions import (
    JobNotFoundError,
    ServiceUnavailableError,
)
from bms_core.jobs import client as job_client
from bms_core.jobs.client import JOB_INTERNAL_PATH, JobInternalClient, build_service_client
from bms_core.servicecall.base import BaseServiceClient, ServiceRequest, ServiceResponse

pytestmark = pytest.mark.kiwi_id(2375)


def _response(status_code: int = 200, payload: object = None) -> ServiceResponse:
    """构造调用响应（`payload` 为 None 表示空体）。"""
    content = b"" if payload is None else json.dumps(payload).encode()
    return ServiceResponse(status_code=status_code, content=content)


class _FakeClient:
    """服务间调用客户端替身：记录请求并返回预设响应。"""

    def __init__(self, response: ServiceResponse) -> None:
        self.response = response
        self.requests: ConcurrentStableList[ServiceRequest] = ConcurrentStableList()

    async def call(self, request: ServiceRequest) -> ServiceResponse:
        """记录请求并返回预设响应。"""
        self.requests.append(request)
        return self.response


def _client(response: ServiceResponse) -> tuple[JobInternalClient, _FakeClient]:
    """构造被测客户端与替身。"""
    fake = _FakeClient(response)
    return JobInternalClient(cast("BaseServiceClient", fake)), fake


class _Settings:
    """设置替身（只需 `service_client.provider`）。"""

    def __init__(self, provider: str) -> None:
        self.service_client = type("S", (), {"provider": provider})()


def test_build_service_client_requires_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    """provider 为空：拒绝构建并提示配置键。"""
    monkeypatch.setattr(job_client, "get_settings", lambda: _Settings(""))
    with pytest.raises(ServiceUnavailableError, match="provider 为空"):
        build_service_client()


def test_build_service_client_resolves_plugin(monkeypatch: pytest.MonkeyPatch) -> None:
    """provider 有值：导入实现模块、构建注册表并解析插件。"""
    sentinel = object()
    monkeypatch.setattr(job_client, "get_settings", lambda: _Settings("http"))
    monkeypatch.setattr(job_client, "build_plugin_registry", lambda: None)

    def _resolve(*args: object, **kwargs: object) -> object:
        del args, kwargs
        return sentinel

    monkeypatch.setattr(job_client, "resolve_plugin", _resolve)
    assert build_service_client() is sentinel


async def test_submit_builds_body_and_parses_id() -> None:
    """提交：全参数进入请求体，响应 `job_id` 转 int；租户 ID 以字符串随请求传递。"""
    client, fake = _client(_response(payload={"code": 0, "data": {"job_id": "42"}}))
    job_id = await client.submit(
        service_key="file",
        job_type="file.cleanup_orphans",
        payload=ConcurrentStableDict({"n": 1}),
        priority=3,
        idempotency_key="k1",
        max_attempts=5,
        payload_version="2.0.0",
        tenant_id=9,
    )
    assert job_id == 42
    request = fake.requests[0]
    assert request.service == "file" and request.method == "POST" and request.path == JOB_INTERNAL_PATH
    assert request.tenant_id == "9"
    body = cast("ConcurrentStableDict[str, object]", request.json_body)
    assert body["priority"] == 3
    assert body["idempotency_key"] == "k1"
    assert body["max_attempts"] == 5
    assert body["payload_version"] == "2.0.0"
    assert body["payload"] == ConcurrentStableDict({"n": 1})


async def test_submit_defaults_and_missing_job_id() -> None:
    """提交：缺省负载为空对象；响应缺 `job_id` 视为下游不可用。"""
    client, fake = _client(_response(payload={"code": 0, "data": {"job_id": "7"}}))
    assert await client.submit(service_key="file", job_type="file.cleanup_orphans") == 7
    body = cast("ConcurrentStableDict[str, object]", fake.requests[0].json_body)
    assert body == ConcurrentStableDict[str, object](
        {"job_type": "file.cleanup_orphans", "payload": ConcurrentStableDict[str, object]()}
    )

    client, _ = _client(_response(payload={"code": 0, "data": {}}))
    with pytest.raises(ServiceUnavailableError, match="缺少 job_id"):
        await client.submit(service_key="file", job_type="file.cleanup_orphans")


async def test_cancel_with_and_without_reason() -> None:
    """取消：带原因写入请求体，缺省为空对象；返回对端状态。"""
    client, fake = _client(_response(payload={"code": 0, "data": {"status": "canceled"}}))
    assert await client.cancel(service_key="file", job_id=5, reason="user") == "canceled"
    assert fake.requests[0].path == f"{JOB_INTERNAL_PATH}/5/cancel"
    assert fake.requests[0].json_body == ConcurrentStableDict({"reason": "user"})

    client, fake = _client(_response(payload={"code": 0, "data": {"status": "requested"}}))
    assert await client.cancel(service_key="file", job_id=6) == "requested"
    assert fake.requests[0].json_body == ConcurrentStableDict()


async def test_retry_and_get() -> None:
    """重试与详情：路径与返回状态 / 数据对象。"""
    client, fake = _client(_response(payload={"code": 0, "data": {"status": "retried"}}))
    assert await client.retry(service_key="file", job_id=8, tenant_id=3) == "retried"
    assert fake.requests[0].path == f"{JOB_INTERNAL_PATH}/8/retry"
    assert fake.requests[0].tenant_id == "3"

    client, fake = _client(_response(payload={"code": 0, "data": {"status": "running"}}))
    assert await client.get(service_key="file", job_id=8) == ConcurrentStableDict({"status": "running"})
    assert fake.requests[0].method == "GET"


async def test_call_rejects_non_2xx() -> None:
    """非 2xx：按下游不可用处理。"""
    client, _ = _client(_response(status_code=503))
    with pytest.raises(ServiceUnavailableError, match="HTTP 503"):
        await client.get(service_key="file", job_id=1)


async def test_call_rejects_non_object_payload() -> None:
    """响应体不是 JSON 对象：视为响应非法。"""
    client, _ = _client(_response(payload=["not", "object"]))
    with pytest.raises(ServiceUnavailableError, match="不是 JSON 对象"):
        await client.get(service_key="file", job_id=1)


async def test_call_maps_business_codes() -> None:
    """业务错误码：已知码映射到对应异常，未知码按服务不可用。"""
    client, _ = _client(_response(payload={"code": 71001, "message": "作业不存在"}))
    with pytest.raises(JobNotFoundError, match="作业不存在"):
        await client.get(service_key="file", job_id=1)

    client, _ = _client(_response(payload={"code": 71999}))
    with pytest.raises(ServiceUnavailableError, match="71999"):
        await client.get(service_key="file", job_id=1)


async def test_call_requires_data_object() -> None:
    """响应缺 `data` 对象：视为响应非法。"""
    client, _ = _client(_response(payload={"code": 0, "data": "bad"}))
    with pytest.raises(ServiceUnavailableError, match="缺少 data 对象"):
        await client.get(service_key="file", job_id=1)


async def test_call_ignores_non_int_code() -> None:
    """`code` 非整数：不按业务错误处理（继续取 data）。"""
    client, _ = _client(_response(payload={"code": "0", "data": {"ok": True}}))
    assert await client.get(service_key="file", job_id=1) == ConcurrentStableDict({"ok": True})
