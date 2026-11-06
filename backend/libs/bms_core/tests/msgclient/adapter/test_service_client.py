"""07B `06_01` 步 2 用例（Kiwi 2441）：`MsgServiceClient` 的请求映射 / 身份 / 限流 / 错误分派。

传输用 `ScriptedRpcTransport`（与生产同一 `RpcTransport` 契约，只换「字节往哪送」），
帧头与载荷用真实 `decode_frame` 解出来断言——不 mock 帧编解码，否则「映射对了但编不出来」
这类问题测不到。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import cast

import pytest
from msgclient_support.rpc_retry import error_response, result_response
from msgclient_support.rpc_transport import ScriptedRpcTransport

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableFrozenDict, ConcurrentStableList
from bms_core.core.exceptions import BizError, ParamError, RateLimitError, ServiceUnavailableError
from bms_core.msgclient.adapter.policy import default_circuit
from bms_core.msgclient.adapter.service_client import MsgServiceClient
from bms_core.msgclient.frame import decode_frame
from bms_core.msgclient.rpc import RpcClient, StaticInstanceProvider
from bms_core.msgclient.transport import RpcHttpRequest, RpcHttpResponse, RpcTransportError
from bms_core.oauth.token import BaseServiceTokenIssuer, ServiceTokenSpec
from bms_core.ratelimit.base import BaseRateLimiter, RateLimitRule
from bms_core.ratelimit.memory import MemoryRateLimiter
from bms_core.ratelimit.null import NullRateLimiter
from bms_core.servicecall.base import ServiceCallPolicy, ServiceRequest

pytestmark = pytest.mark.kiwi_id(2441)

BASE_URL = "http://msg:8000"


@dataclass(frozen=True)
class _Issued:
    """签发结果替身（只带 `access_token`）。"""

    access_token: str


class _StubIssuer:
    """服务 JWT 签发者替身（记录 spec，返回固定令牌）。"""

    def __init__(self, token: str = "svc-jwt") -> None:
        self.token = token
        self.specs: ConcurrentStableList[ServiceTokenSpec] = ConcurrentStableList()

    async def issue(self, spec: ServiceTokenSpec) -> _Issued:
        """记录并返回固定令牌。"""
        self.specs.add(spec)
        return _Issued(self.token)


class _Recorder:
    """记录出站请求并按脚本返回响应 / 抛传输异常。"""

    def __init__(
        self,
        response: RpcHttpResponse | None = None,
        error: BaseException | None = None,
    ) -> None:
        self.requests: ConcurrentStableList[RpcHttpRequest] = ConcurrentStableList()
        self._response = response
        self._error = error

    async def __call__(self, request: RpcHttpRequest) -> RpcHttpResponse:
        """记录请求后返回脚本响应。"""
        self.requests.add(request)
        if self._error is not None:
            raise self._error
        return self._response if self._response is not None else result_response()


def _client(
    recorder: _Recorder,
    *,
    rate_limiter: BaseRateLimiter | None = None,
    token_issuer: object | None = None,
    attach_service_token: bool = False,
    caller: str = "platform",
    tenant: str | None = None,
) -> MsgServiceClient:
    """构造带脚本传输的 `MsgServiceClient`（缺省空限流器）。"""
    rpc = RpcClient(
        StaticInstanceProvider([BASE_URL]),
        transport=ScriptedRpcTransport(handler=recorder),
        circuit=default_circuit(),
    )
    return MsgServiceClient(
        rpc_client=rpc,
        rate_limiter=rate_limiter or NullRateLimiter(),
        token_issuer=cast("BaseServiceTokenIssuer | None", token_issuer),
        attach_service_token=attach_service_token,
        caller=caller,
        tenant=tenant,
    )


def _request(**overrides: object) -> ServiceRequest:
    """构造一次默认调用（POST JSON 到 `/api/v1/modules/list`）。"""
    payload: ConcurrentStableDict[str, object] = ConcurrentStableDict(
        {
            "service": "platform",
            "method": "POST",
            "path": "/api/v1/modules/list",
            "json_body": ConcurrentStableFrozenDict({"a": 1}),
        }
    )
    for name, value in overrides.items():
        payload.set(name, value)
    return ServiceRequest(**dict(payload.items()))  # pyright: ignore[reportArgumentType]


async def test_call_maps_request_to_frame_and_back() -> None:
    """`ServiceRequest` → 帧（方法名 / 预算 / 载荷）→ `ServiceResponse`（载荷 / 头）。"""
    recorder = _Recorder(result_response(b'{"ok": true}'))
    client = _client(recorder)
    response = await client.call(_request())
    assert response.status_code == 200
    assert response.payload() == {"ok": True}
    request = recorder.requests[0]
    assert request.target == "/rpc/platform/modules.list"
    frame = decode_frame(request.body)
    assert frame.header["service"] == "platform"
    assert frame.header["method"] == "modules.list"
    assert frame.header["deadline_ms"] == 5000
    assert frame.payload == b'{"a": 1}'
    assert frame.header["idempotency_key"]


async def test_call_passes_query_as_prefixed_frame_headers() -> None:
    """查询串进帧头 `query.<name>`，不写进载荷。"""
    recorder = _Recorder(result_response())
    client = _client(recorder)
    await client.call(_request(path="/api/v1/modules/get", query=ConcurrentStableFrozenDict({"user_id": "7"})))
    frame = decode_frame(recorder.requests[0].body)
    assert frame.header["headers"] == {"query.user_id": "7"}
    assert frame.payload == b'{"a": 1}'


async def test_call_strips_inbound_authorization() -> None:
    """入站 `Authorization` 一律剥离（外部 token 不进东西向）。"""
    recorder = _Recorder(result_response())
    client = _client(recorder)
    await client.call(_request(headers=ConcurrentStableFrozenDict({"Authorization": "Bearer user", "x-extra": "1"})))
    frame = decode_frame(recorder.requests[0].body)
    assert frame.header["headers"] == {"x-extra": "1"}


async def test_call_attaches_service_token_when_enabled() -> None:
    """开启出站换券时按**调用方**服务标识签发并附 `Authorization`。"""
    recorder = _Recorder(result_response())
    issuer = _StubIssuer()
    client = _client(recorder, token_issuer=issuer, attach_service_token=True, tenant="1001")
    await client.call(_request())
    frame = decode_frame(recorder.requests[0].body)
    assert frame.header["headers"]["Authorization"] == "Bearer svc-jwt"
    assert issuer.specs[0].service == "platform"
    assert issuer.specs[0].tenant_id == "1001"


async def test_call_skips_authorization_when_issuer_returns_empty() -> None:
    """签发结果无 `access_token` 时不附空 `Authorization`（发出 `Bearer ` 会被对端判为非法凭证）。"""
    recorder = _Recorder(result_response())
    issuer = _StubIssuer(token="")
    client = _client(recorder, token_issuer=issuer, attach_service_token=True)
    await client.call(_request())
    frame = decode_frame(recorder.requests[0].body)
    assert "Authorization" not in (frame.header.get("headers") or {})


async def test_call_carries_tenant_header() -> None:
    """租户经 `X-Tenant-ID` 头传递（服务端仍以解析链为准）。"""
    recorder = _Recorder(result_response())
    client = _client(recorder, tenant="2002")
    await client.call(_request())
    assert dict(recorder.requests[0].headers)["X-Tenant-ID"] == "2002"


async def test_call_ignores_local_flag() -> None:
    """`local=True` 在 RPC 通道无直连语义 —— 忽略而不是报错（差异已登记）。"""
    recorder = _Recorder(result_response())
    client = _client(recorder)
    await client.call(_request(local=True))
    assert len(recorder.requests) == 1


async def test_call_applies_rate_limit_rule() -> None:
    """`policy.rate_limit` 超限即 `RateLimitError`，且不再发起调用。"""
    recorder = _Recorder(result_response())
    client = _client(recorder, rate_limiter=MemoryRateLimiter())
    policy = ServiceCallPolicy(rate_limit=RateLimitRule(limit=1), rate_limit_key="k1")
    await client.call(_request(policy=policy))
    with pytest.raises(RateLimitError):
        await client.call(_request(policy=policy))
    assert len(recorder.requests) == 1


async def test_call_maps_rate_limited_frame() -> None:
    """服务端 `350005` → `RateLimitError`（不重试：策略给 0 次）。"""
    recorder = _Recorder(error_response(350005, category="transient", retryable=True, retry_after_ms=100))
    client = _client(recorder)
    with pytest.raises(RateLimitError):
        await client.call(_request(policy=ServiceCallPolicy(max_retries=0)))


async def test_call_maps_business_reject_frame() -> None:
    """业务拒绝（方法未注册 350023）→ `BizError` 保留原始码。"""
    recorder = _Recorder(error_response(350023, category="business_reject", retryable=False))
    client = _client(recorder)
    with pytest.raises(BizError) as caught:
        await client.call(_request(policy=ServiceCallPolicy(max_retries=0)))
    assert caught.value.code == 350023


async def test_call_maps_unknown_frame_to_unavailable() -> None:
    """预算耗尽帧（350004）→ 不可用 + `outcome=unknown`。"""
    recorder = _Recorder(error_response(350004, category="unknown", retryable=False, layer="business"))
    client = _client(recorder)
    with pytest.raises(ServiceUnavailableError) as caught:
        await client.call(_request(policy=ServiceCallPolicy(max_retries=0)))
    detail = caught.value.data
    assert isinstance(detail, Mapping)
    assert detail["code"] == 350004
    assert detail["outcome"] == "unknown"


async def test_call_rejects_unregistered_service_without_calling() -> None:
    """目标未登记启用 → `ParamError`，且一次请求都不发。"""
    recorder = _Recorder(result_response())
    client = _client(recorder)
    with pytest.raises(ParamError):
        await client.call(_request(service="ghost"))
    assert not recorder.requests


async def test_call_rejects_conflicting_bodies_without_calling() -> None:
    """请求体二选一冲突在发请求前就拒。"""
    recorder = _Recorder(result_response())
    client = _client(recorder)
    with pytest.raises(ParamError):
        await client.call(_request(content=b"raw"))
    assert not recorder.requests


async def test_call_wraps_transport_error_as_unavailable() -> None:
    """传输层失败 → `ServiceUnavailableError`（协议异常不外泄到业务层）。"""
    recorder = _Recorder(error=RpcTransportError("connect refused"))
    client = _client(recorder)
    with pytest.raises(ServiceUnavailableError):
        await client.call(_request(policy=ServiceCallPolicy(max_retries=0)))


async def test_aclose_releases_transport() -> None:
    """`aclose()` 释放底层传输（生命周期由资源管理器回收）。"""
    recorder = _Recorder(result_response())
    client = _client(recorder)
    await client.aclose()
