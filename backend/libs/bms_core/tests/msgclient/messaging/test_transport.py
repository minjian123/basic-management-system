"""03-6 用例：JSON 传输层（Kiwi 2510）。

覆盖要点：请求头三段来源（租户 / 自定义 / 鉴权，后者覆盖前者）；三类传输异常的分工
（未发出 → 可重试、已发出无结果 → 结果未知、其余 → 结果未知兜底）；响应解析的三种不合法形态；
`Retry-After` 与 `data.retry_after_ms` 两个来源的优先级。
"""

from __future__ import annotations

import httpx
import pytest

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableFrozenDict
from bms_core.msgclient.errors import ErrorCategory
from bms_core.msgclient.messaging import ApiOutcome, ClientAction, MessagingTransport, MsgClientError

from ._support import ScriptedServer, build_config, build_transport, ok_body

pytestmark = pytest.mark.kiwi_id(2510)


def test_headers_tenant_only() -> None:
    """无自定义头、无鉴权：只带租户头。"""
    transport = build_transport(build_config(), ScriptedServer())
    headers = transport.headers()
    assert headers.get("X-Tenant-ID") == "t1"
    assert headers.get("Authorization") is None


def test_headers_merge_and_auth_wins() -> None:
    """自定义头与鉴权都注入；同名键以鉴权为准（避免自定义头把令牌覆盖成脏值）。"""
    config = build_config(
        headers_provider=lambda: ConcurrentStableDict({"X-Trace": "abc", "Authorization": "custom"}),
        auth_provider=lambda: "Bearer t",
    )
    headers = build_transport(config, ScriptedServer()).headers()
    assert headers.get("X-Trace") == "abc"
    assert headers.get("Authorization") == "Bearer t"


@pytest.mark.asyncio
async def test_post_parses_body_and_retry_after_header() -> None:
    """成功响应：解析 code / message / data，`Retry-After`（秒）转毫秒。"""
    server = ScriptedServer()
    server.push(
        "/msg/publish",
        body=ok_body(data={"leader": "msg-2"}),
        headers=ConcurrentStableFrozenDict({"Retry-After": "2"}),
    )
    transport = build_transport(build_config(), server)
    outcome = await transport.post("http://msg-1:8000", "/msg/publish", {"a": 1})
    assert outcome.code == 0
    assert outcome.data.get("leader") == "msg-2"
    assert outcome.retry_after_ms == 2_000
    assert server.requests[0].headers["X-Tenant-ID"] == "t1"


@pytest.mark.asyncio
async def test_post_reads_retry_after_from_data_when_header_absent() -> None:
    """没有 `Retry-After` 头：回落 `data.retry_after_ms`。"""
    server = ScriptedServer()
    server.push("/msg/publish", body=ok_body(350005, data={"retry_after_ms": 800}))
    outcome = await build_transport(build_config(), server).post("http://msg-1:8000", "/msg/publish", {})
    assert outcome.retry_after_ms == 800


@pytest.mark.asyncio
async def test_post_has_no_retry_hint() -> None:
    """两个来源都没有：`retry_after_ms` 为 None。"""
    server = ScriptedServer()
    server.push("/msg/publish", body=ok_body())
    outcome = await build_transport(build_config(), server).post("http://msg-1:8000", "/msg/publish", {})
    assert outcome.retry_after_ms is None


@pytest.mark.asyncio
async def test_connect_failure_is_retryable_and_not_sent() -> None:
    """建连失败：请求未发出 → `transient` / 可重试，且不标结果未知。"""
    server = ScriptedServer()
    server.push("/msg/publish", error=httpx.ConnectError("拒绝连接"))
    transport = build_transport(build_config(), server)
    with pytest.raises(MsgClientError) as captured:
        await transport.post("http://msg-1:8000", "/msg/publish", {})
    error = captured.value
    assert error.code == 0
    assert error.category is ErrorCategory.TRANSIENT
    assert error.action is ClientAction.RETRY
    assert error.outcome_unknown is False


@pytest.mark.asyncio
async def test_read_timeout_is_unknown() -> None:
    """读超时：已发出但没拿到结果 → 标结果未知（重试可能重复）。"""
    server = ScriptedServer()
    server.push("/msg/publish", error=httpx.ReadTimeout("超时"))
    transport = build_transport(build_config(), server)
    with pytest.raises(MsgClientError) as captured:
        await transport.post("http://msg-1:8000", "/msg/publish", {})
    assert captured.value.category is ErrorCategory.UNKNOWN
    assert captured.value.outcome_unknown is True


@pytest.mark.asyncio
async def test_other_transport_error_is_unknown_and_fatal() -> None:
    """其余传输异常：无法判定是否已发出 → 按结果未知兜底，且不自动重试。"""
    server = ScriptedServer()
    server.push("/msg/publish", error=httpx.DecodingError("坏响应"))
    transport = build_transport(build_config(), server)
    with pytest.raises(MsgClientError) as captured:
        await transport.post("http://msg-1:8000", "/msg/publish", {})
    assert captured.value.action is ClientAction.FATAL
    assert captured.value.outcome_unknown is True


@pytest.mark.asyncio
async def test_non_json_response_is_rejected() -> None:
    """响应不是 JSON（网关页面 / 反代错误页）：直接判失败，不重试。"""
    server = ScriptedServer()
    server.push("/msg/publish", status=200, body="<html>bad gateway</html>")
    transport = build_transport(build_config(), server)
    with pytest.raises(MsgClientError, match="不是合法 JSON"):
        await transport.post("http://msg-1:8000", "/msg/publish", {})


@pytest.mark.asyncio
async def test_non_object_response_is_rejected() -> None:
    """响应是 JSON 但不是对象：同样判失败。"""
    server = ScriptedServer()
    server.push("/msg/publish", body=[1, 2, 3])
    transport = build_transport(build_config(), server)
    with pytest.raises(MsgClientError, match="不是对象"):
        await transport.post("http://msg-1:8000", "/msg/publish", {})


@pytest.mark.asyncio
async def test_missing_code_is_rejected() -> None:
    """响应缺整型 code：判失败（对端不是本服务）。"""
    server = ScriptedServer()
    server.push("/msg/publish", body={"message": "x"})
    transport = build_transport(build_config(), server)
    with pytest.raises(MsgClientError, match="缺少整型 code"):
        await transport.post("http://msg-1:8000", "/msg/publish", {})


@pytest.mark.asyncio
async def test_data_not_object_becomes_empty_mapping() -> None:
    """`data` 不是对象：归一成空映射，不抛错（调用方按空 `data` 处理）。"""
    server = ScriptedServer()
    server.push("/msg/publish", body={"code": 0, "message": "", "data": "text"})
    outcome = await build_transport(build_config(), server).post("http://msg-1:8000", "/msg/publish", {})
    assert outcome.data == ConcurrentStableFrozenDict[str, object]()
    assert outcome.retry_after_ms is None


@pytest.mark.asyncio
async def test_close_is_idempotent() -> None:
    """关闭可重复调用（进程退出路径不该因为重复关而抛）。"""
    transport = MessagingTransport(
        build_config(),
        client=httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, json=ok_body()))),
    )
    await transport.close()
    await transport.close()


def test_api_outcome_defaults() -> None:
    """传输结果对象不传 `data` 时是空映射（调用方不必判 None）。"""
    outcome = ApiOutcome(code=0)
    assert outcome.data == ConcurrentStableFrozenDict[str, object]()
    assert outcome.message == ""
    assert outcome.retry_after_ms is None
