"""07B `06_01` 步 3 用例（Kiwi 2442）：回滚三态与真实调用点两通道等价。

**为什么这几条放在一起**：都在验「切换 `provider` 对业务是透明的」——在途请求（重试全程
同一幂等键）、通道互斥（一次调用只发一条通道）、真实调用点（`fetch_catalog_snapshot` 在
`http` 与 `msg` 两通道产出同构结果、失败同构）。分开写会各自造一套替身，切换口径的差异
反而藏起来。三态里的「未确认事件」走发件箱投递器，用例落
`tests/outbox/test_provider_switch.py`（那里有真发件箱表与投递器夹具）。
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable

import httpx
import pytest
from msgclient_support.rpc_retry import FakeClock, error_response, result_response
from msgclient_support.rpc_transport import ScriptedRpcTransport

from bms_core.catalog.base import CATALOG_SNAPSHOT_PATH, fetch_catalog_snapshot
from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.exceptions import ServiceUnavailableError
from bms_core.fallback.null import NullFallbackPolicy
from bms_core.msgclient.adapter.policy import default_circuit
from bms_core.msgclient.adapter.service_client import MsgServiceClient
from bms_core.msgclient.frame import decode_frame
from bms_core.msgclient.rpc import RpcClient, StaticInstanceSelector
from bms_core.msgclient.transport import RpcHttpRequest, RpcHttpResponse, RpcTransportError
from bms_core.ratelimit.null import NullRateLimiter
from bms_core.servicecall.http import HttpServiceClient

pytestmark = pytest.mark.kiwi_id(2442)

BASE_URL = "http://msg:8000"
"""msg 实例地址（脚本传输只取路径与方法，主机名仅占位）。"""

_ModuleHandler = Callable[[RpcHttpRequest], Awaitable[RpcHttpResponse]]
"""一元处理器类型（脚本帧传输）。"""

_MODULE_FIELDS: ConcurrentStableDict[str, object] = ConcurrentStableDict(
    {
        "module_key": "platform",
        "name": "平台",
        "table_prefix": "sys_",
        "event_domain": "platform",
        "errcode_segment": "10",
        "service_key": "platform",
        "business_code": "platform",
        "service_group": "foundation",
        "build_batch": 1,
        "service_version": "0.1.0",
        "contract_version": "0.1.0",
        "product_key": "bms",
        "status": "enabled",
    }
)
"""一行的必填字段（`_to_record` 只读这些；`tenant_base` 缺省按 False）。"""


def _snapshot_body() -> bytes:
    """统一响应包裹的快照体（两通道同一份字节，避免「差在响应体」被当成通道差异）。"""
    body: ConcurrentStableDict[str, object] = ConcurrentStableDict(
        {"code": 0, "message": "ok", "data": [dict(_MODULE_FIELDS.items())]}
    )
    return json.dumps(dict(body.items())).encode()


def _msg_client(transport: ScriptedRpcTransport) -> MsgServiceClient:
    """构造走脚本帧传输的 `MsgServiceClient`（零退避时钟，避免用例真的睡）。"""
    return MsgServiceClient(
        rpc_client=RpcClient(
            StaticInstanceSelector([BASE_URL]),
            transport=transport,
            circuit=default_circuit(),
            clock=FakeClock(),
        ),
        rate_limiter=NullRateLimiter(),
        caller="platform",
    )


def _http_client(handler: Callable[[httpx.Request], httpx.Response]) -> HttpServiceClient:
    """构造走 `httpx.MockTransport` 的 `HttpServiceClient`（真实 http 通道实现）。"""
    return HttpServiceClient(
        circuit_breaker=default_circuit(),
        fallback_policy=NullFallbackPolicy(),
        rate_limiter=NullRateLimiter(),
        base_url_template="http://{service}:8000",
        caller="platform",
        transport=httpx.MockTransport(handler),
    )


def _fixed(response: RpcHttpResponse) -> _ModuleHandler:
    """构造「恒定返回给定响应」的一元处理器。

    Args:
        response: 要返回的响应。

    Returns:
        _ModuleHandler: 一元处理器。
    """

    async def handler(request: RpcHttpRequest) -> RpcHttpResponse:
        """忽略请求，返回固定响应。"""
        del request
        return response

    return handler


async def test_inflight_request_retries_with_same_idempotency_key() -> None:
    """在途请求：首次传输失败 → 重试，**全程同一幂等键**，业务结果一次生效。

    服务端按 `(service, method, idempotency_key)` 去重，所以「键稳定」是「不重复执行」的前提；
    键每跳一变，重试就变成第二次真实执行——这正是回滚窗口里最贵的错。
    """
    attempts: ConcurrentStableList[ConcurrentStableDict[str, object]] = ConcurrentStableList()

    async def handler(request: RpcHttpRequest) -> RpcHttpResponse:
        """首跳失败、次跳成功，并记录每跳帧头。"""
        attempts.add(ConcurrentStableDict(dict(decode_frame(request.body).header.items())))
        if len(attempts) == 1:
            raise RpcTransportError("首跳超时（注入）")
        return result_response(_snapshot_body())

    records = await fetch_catalog_snapshot(_msg_client(ScriptedRpcTransport(handler=handler)))

    assert [record.module_key for record in records] == ["platform"]
    assert len(attempts) == 2
    keys = [header.get("idempotency_key") for header in attempts]
    assert keys[0] is not None
    assert keys[0] == keys[1]
    # 调用链预算逐跳递减：每次重试消耗一次，后续跳不能再按原额度重来。
    assert int(attempts[1]["retry_budget"]) < int(attempts[0]["retry_budget"])  # pyright: ignore[reportArgumentType]


async def test_real_call_point_equivalent_on_both_channels() -> None:
    """真实调用点 `fetch_catalog_snapshot`：`msg` 与 `http` 两通道产出同构结果（切回即恢复）。"""
    msg_transport = ScriptedRpcTransport(handler=_fixed(result_response(_snapshot_body())))
    http_seen: ConcurrentStableList[str] = ConcurrentStableList()

    def http_handler(request: httpx.Request) -> httpx.Response:
        """记录路径后返回同一份响应体。"""
        http_seen.add(request.url.path)
        return httpx.Response(200, content=_snapshot_body())

    msg_client = _msg_client(msg_transport)
    http_client = _http_client(http_handler)

    over_msg = await fetch_catalog_snapshot(msg_client)
    over_http = await fetch_catalog_snapshot(http_client)
    back_to_msg = await fetch_catalog_snapshot(msg_client)

    assert [record.module_key for record in over_msg] == ["platform"]
    assert over_msg == over_http == back_to_msg
    assert list(http_seen) == [CATALOG_SNAPSHOT_PATH]
    # 方法名归一化：`/api/v1/modules/snapshot` → `modules.snapshot`，服务端按二元组分发。
    header = decode_frame(msg_transport.requests[0].body).header
    assert header["service"] == "platform"
    assert header["method"] == "modules.snapshot"


async def test_single_channel_per_call_no_dual_path() -> None:
    """通道互斥：一次调用只发一条通道（不存在「两条都发」的双写路径）。

    `MsgServiceClient` 只持有一个 `RpcClient`（一个传输），所以「每次调用恰好一条帧」就是
    「没有第二通道」的可测判据；两次调用 = 两条帧，多一条就说明有并发路径。
    """
    msg_transport = ScriptedRpcTransport(handler=_fixed(result_response(_snapshot_body())))
    client = _msg_client(msg_transport)

    first = await fetch_catalog_snapshot(client)
    second = await fetch_catalog_snapshot(client)

    assert [record.module_key for record in first] == ["platform"]
    assert first == second
    assert len(msg_transport.requests) == 2


async def test_failure_branches_converge_to_same_exception() -> None:
    """失败口径一致：`msg` 的**不可用类**错误帧与 `http` 非 2xx 都收敛为 `ServiceUnavailableError`。

    业务拒绝（`business_reject`）另有口径（原码 `BizError`，见步 2 用例），这里只对齐「下游不可用」
    这一支——它是切换期最常见、也是调用方降级判据唯一依赖的那一支。
    """
    msg_error = error_response(350016, category="transient", retryable=False)
    with pytest.raises(ServiceUnavailableError):
        await fetch_catalog_snapshot(_msg_client(ScriptedRpcTransport(handler=_fixed(msg_error))))

    with pytest.raises(ServiceUnavailableError):
        await fetch_catalog_snapshot(_http_client(lambda request: httpx.Response(503, content=b"{}")))


async def test_invalid_payload_converges_to_same_exception() -> None:
    """响应体非法（缺 `data` 数组）在两通道都是 `ServiceUnavailableError`，不是 `KeyError` 外泄。"""
    bad_body = json.dumps({"code": 0, "message": "ok"}).encode()
    with pytest.raises(ServiceUnavailableError):
        await fetch_catalog_snapshot(_msg_client(ScriptedRpcTransport(handler=_fixed(result_response(bad_body)))))
    with pytest.raises(ServiceUnavailableError):
        await fetch_catalog_snapshot(_http_client(lambda request: httpx.Response(200, content=bad_body)))
