"""租户配额内部契约客户端测试（任务 `04_01`；Kiwi 2325）。

覆盖：无租户上下文空操作、占用成功、超限 82005、配额服务不可用 fail-open、释放失败静默。
"""

from typing import cast

import pytest

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.exceptions import TenantQuotaExceededError
from bms_core.core.serialization import stable_json_dumps
from bms_core.servicecall.base import BaseServiceClient, ServiceRequest, ServiceResponse
from bms_core.tenant_module.quota import TenantQuotaClient

pytestmark = pytest.mark.kiwi_id(2325)


class _Client:
    """服务间客户端替身。"""

    def __init__(self, *, code: int = 0, error: Exception | None = None) -> None:
        self.code = code
        self.error = error
        self.calls: ConcurrentStableList[ServiceRequest] = ConcurrentStableList()

    async def call(self, request: ServiceRequest) -> ServiceResponse:
        self.calls.append(request)
        if self.error is not None:
            raise self.error
        body = {"code": self.code, "message": "x", "data": {"quota_key": "user_count", "limit": 1, "used": 1}}
        return ServiceResponse(
            status_code=200 if self.code == 0 else 409,
            content=stable_json_dumps(body).encode(),
        )


async def test_quota_client_noop_without_tenant() -> None:
    """无租户上下文：不发起调用。"""
    client = _Client()
    quota = TenantQuotaClient(client, tenant_id=None, tenant_code=None)  # type: ignore[arg-type]
    await quota.consume("user_count", 1)
    await quota.release("user_count", 1)
    assert client.calls == []


async def test_quota_client_consume_and_release() -> None:
    """占用 / 释放：路径与载荷正确。"""
    client = _Client()
    quota = TenantQuotaClient(client, tenant_id="7", tenant_code="demo")  # type: ignore[arg-type]
    await quota.consume("user_count", 1, ref="bob")
    await quota.release("user_count", 1)
    assert [call.path.rsplit("/", 1)[-1] for call in client.calls] == ["consume", "release"]
    assert client.calls[0].json_body is not None and client.calls[0].json_body["tenant_id"] == 7


async def test_quota_client_exceeded_raises() -> None:
    """82005 → 配额超限异常（带维度 / 限额 / 用量）。"""
    quota = TenantQuotaClient(_Client(code=82005), tenant_id="7", tenant_code="demo")  # type: ignore[arg-type]
    with pytest.raises(TenantQuotaExceededError) as exc:
        await quota.consume("user_count", 1)
    assert exc.value.data is not None


async def test_quota_client_unavailable_fail_open() -> None:
    """配额服务不可用 / 非法响应：占用与释放均不抛（fail-open）。"""
    unavailable = TenantQuotaClient(_Client(code=10007), tenant_id="7", tenant_code="demo")  # type: ignore[arg-type]
    await unavailable.consume("user_count", 1)
    await unavailable.release("user_count", 1)

    broken = TenantQuotaClient(
        cast("BaseServiceClient", _Client(error=RuntimeError("down"))), tenant_id="7", tenant_code="demo"
    )
    await broken.release("user_count", 1)


async def test_quota_client_bad_payload() -> None:
    """非统一响应体（缺 data / code 非 0）：按不可用 fail-open。"""

    class _Bad:
        async def call(self, request: ServiceRequest) -> ServiceResponse:
            del request
            return ServiceResponse(status_code=200, content=b"[]")

    quota = TenantQuotaClient(_Bad(), tenant_id="7", tenant_code="demo")  # type: ignore[arg-type]
    await quota.consume("user_count", 1)
