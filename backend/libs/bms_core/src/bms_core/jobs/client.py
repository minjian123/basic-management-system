"""作业内部契约客户端：服务间提交 / 取消 / 重试 / 详情（服务身份，东西向直连）。

- 契约：各服务 `POST/GET /api/v1/jobs/internal…`；
- 平台转发取消 / 重试时按投影里的 `service_key` 定向调用；
- 业务错误码（`71xxx`）在响应 `code` 中透传并映射回本端异常，用户面拿到一致的 HTTP 状态。
"""

from __future__ import annotations

from typing import cast

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableFrozenDict
from bms_core.core.exceptions import (
    JobHandlerNotRegisteredError,
    JobNotCancelableError,
    JobNotFoundError,
    JobNotRetryableError,
    JobPayloadInvalidError,
    JobTypeNotRegisteredError,
    ServiceUnavailableError,
)
from bms_core.core.objects import BaseFrameworkObject
from bms_core.servicecall.base import BaseServiceClient, ServiceCallPolicy, ServiceRequest

__all__ = ["JOB_INTERNAL_PATH", "JobInternalClient"]

JOB_INTERNAL_PATH = "/api/v1/jobs/internal"
"""作业内部契约根路径。"""

_ERROR_TYPES: dict[int, type[Exception]] = {
    71001: JobNotFoundError,
    71002: JobTypeNotRegisteredError,
    71003: JobNotCancelableError,
    71004: JobNotRetryableError,
    71005: JobPayloadInvalidError,
    71006: JobHandlerNotRegisteredError,
}
"""内部契约业务错误码 → 异常类型。"""


class JobInternalClient(BaseFrameworkObject):
    """作业内部契约客户端（提交 / 取消 / 重试 / 详情）。"""

    def __init__(self, client: BaseServiceClient) -> None:
        """初始化。

        Args:
            client: 服务间调用客户端（`service_client` 能力域）。
        """
        self._client = client

    async def submit(
        self,
        *,
        service_key: str,
        job_type: str,
        payload: ConcurrentStableDict[str, object] | None = None,
        priority: int = 0,
        idempotency_key: str | None = None,
        max_attempts: int | None = None,
        payload_version: str | None = None,
    ) -> int:
        """向目标服务提交作业。

        Args:
            service_key: 目标服务键（作业提供方）。
            job_type: 作业类型（须属于目标服务声明）。
            payload: 负载 JSON 对象。
            priority: 租户内优先级。
            idempotency_key: 幂等键。
            max_attempts: 最大执行次数（None 由目标服务取声明 / 默认）。
            payload_version: 负载版本。

        Returns:
            int: 作业主键。

        Raises:
            ServiceUnavailableError: 下游不可达 / 响应非法。
            JobError: 业务错误码映射（`71xxx`）。
        """
        body: ConcurrentStableDict[str, object] = ConcurrentStableDict(
            {
                "job_type": job_type,
                "payload": payload if payload is not None else ConcurrentStableDict[str, object](),
            }
        )
        if priority:
            body.set("priority", int(priority))
        if idempotency_key:
            body.set("idempotency_key", idempotency_key)
        if max_attempts is not None:
            body.set("max_attempts", int(max_attempts))
        if payload_version:
            body.set("payload_version", payload_version)
        data = await self._call(
            service_key, "POST", JOB_INTERNAL_PATH, json_body=ConcurrentStableFrozenDict(dict(body))
        )
        job_id = data.get("job_id")
        if job_id is None:
            raise ServiceUnavailableError("作业提交响应缺少 job_id")
        return int(str(job_id))

    async def cancel(self, *, service_key: str, job_id: int, reason: str | None = None) -> str:
        """取消作业（按目标服务定向调用）。

        Args:
            service_key: 目标服务键。
            job_id: 作业主键。
            reason: 取消原因。

        Returns:
            str: 对端返回的状态（`canceled` / `requested`）。

        Raises:
            ServiceUnavailableError: 下游不可达 / 响应非法。
            JobError: 业务错误码映射（`71xxx`）。
        """
        body: ConcurrentStableDict[str, object] = ConcurrentStableDict()
        if reason:
            body.set("reason", reason)
        data = await self._call(
            service_key,
            "POST",
            f"{JOB_INTERNAL_PATH}/{job_id}/cancel",
            json_body=ConcurrentStableFrozenDict(dict(body)),
        )
        return str(data.get("status") or "")

    async def retry(self, *, service_key: str, job_id: int) -> str:
        """重试作业（仅 dead / failed）。

        Args:
            service_key: 目标服务键。
            job_id: 作业主键。

        Returns:
            str: 对端返回的状态（`retried`）。

        Raises:
            ServiceUnavailableError: 下游不可达 / 响应非法。
            JobError: 业务错误码映射（`71xxx`）。
        """
        data = await self._call(service_key, "POST", f"{JOB_INTERNAL_PATH}/{job_id}/retry")
        return str(data.get("status") or "")

    async def get(self, *, service_key: str, job_id: int) -> ConcurrentStableDict[str, object]:
        """取目标服务的本地作业详情。

        Args:
            service_key: 目标服务键。
            job_id: 作业主键。

        Returns:
            ConcurrentStableDict[str, object]: 详情数据。

        Raises:
            ServiceUnavailableError: 下游不可达 / 响应非法。
            JobError: 业务错误码映射（`71xxx`）。
        """
        return await self._call(service_key, "GET", f"{JOB_INTERNAL_PATH}/{job_id}")

    async def _call(
        self,
        service_key: str,
        method: str,
        path: str,
        *,
        json_body: ConcurrentStableFrozenDict[str, object] | None = None,
    ) -> ConcurrentStableDict[str, object]:
        """发起内部调用并解析统一响应。

        Args:
            service_key: 目标服务键。
            method: HTTP 方法。
            path: 路径。
            json_body: JSON 请求体。

        Returns:
            ConcurrentStableDict[str, object]: 响应 `data` 对象。

        Raises:
            ServiceUnavailableError: 下游不可达 / 非 2xx / 响应非法。
            JobError: 业务错误码映射（`71xxx`）。
        """
        request = ServiceRequest(
            service=service_key,
            method=method,
            path=path,
            json_body=json_body,
            policy=ServiceCallPolicy(),
        )
        response = await self._client.call(request)
        if not 200 <= response.status_code < 300:
            raise ServiceUnavailableError(f"作业内部调用失败：{service_key} HTTP {response.status_code}")
        payload = response.payload()
        if not isinstance(payload, dict):
            raise ServiceUnavailableError("作业内部响应不是 JSON 对象")
        envelope = cast("dict[str, object]", payload)
        code = envelope.get("code")
        if isinstance(code, int) and code != 0:
            message = str(envelope.get("message") or f"作业内部调用失败：{code}")
            error_type = _ERROR_TYPES.get(code)
            if error_type is not None:
                raise error_type(message)
            raise ServiceUnavailableError(message)
        data = envelope.get("data")
        if not isinstance(data, dict):
            raise ServiceUnavailableError("作业内部响应缺少 data 对象")
        fields = cast("dict[object, object]", data)
        return ConcurrentStableDict({str(key): value for key, value in fields.items()})
