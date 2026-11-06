"""07B `06_01` 步 2 用例（Kiwi 2441）：端口字段 ↔ RPC 帧的翻译与错误分派。

只断言纯函数：方法名归一化、查询串透传、请求体编码、五类错误到 bms 异常的分派。
网络与帧编解码由 `test_service_client.py` 覆盖。
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import cast

import pytest
from structlog.testing import capture_logs

from bms_core.core.concurrent import ConcurrentStableFrozenDict
from bms_core.core.error_codes import ErrorCode
from bms_core.core.exceptions import BizError, ParamError, RateLimitError, ServiceUnavailableError
from bms_core.msgclient.adapter.mapping import (
    OUTCOME_UNKNOWN,
    QUERY_HEADER_PREFIX,
    method_of,
    query_headers,
    request_payload,
    to_bms_error,
)
from bms_core.msgclient.errors import ErrorCategory
from bms_core.msgclient.rpc import RpcCallError, RpcCallTimeoutError
from bms_core.servicecall.base import ServiceRequest

pytestmark = pytest.mark.kiwi_id(2441)


def test_method_of_strips_public_prefix_and_joins_segments() -> None:
    """公开契约路径归一为 `foo.bar` 形态（msg 04-5 §2.3 同一口径）。"""
    assert method_of("/api/v1/foo/bar") == "foo.bar"
    assert method_of("/api/v1/foo/bar/") == "foo.bar"
    assert method_of("/api/v1/single") == "single"
    assert method_of("/other/path") == "other.path"


def test_method_of_rejects_bare_prefix() -> None:
    """`/api/v1` 没有可归一的末段 —— 拒，不猜方法名。"""
    with pytest.raises(ParamError):
        method_of("/api/v1")
    with pytest.raises(ParamError):
        method_of("/api/v1/")


def test_query_headers_is_prefixed_and_empty_by_default() -> None:
    """查询串逐项进帧头 `query.<name>`；无查询时为空表。"""
    headers = query_headers(ConcurrentStableFrozenDict({"user_id": "7", "db_key": "main"}))
    assert dict(headers.items()) == {f"{QUERY_HEADER_PREFIX}user_id": "7", f"{QUERY_HEADER_PREFIX}db_key": "main"}
    assert not query_headers(None)
    assert not query_headers(ConcurrentStableFrozenDict())


def test_request_payload_prefers_json_body_with_deterministic_bytes() -> None:
    """`json_body` 归一后按键排序输出 —— 同输入同字节，便于对账。"""
    request = ServiceRequest(
        service="platform",
        method="POST",
        path="/api/v1/a/b",
        json_body=ConcurrentStableFrozenDict({"b": 1, "a": "中"}),
    )
    assert request_payload(request) == '{"a": "中", "b": 1}'.encode()


def test_request_payload_passes_raw_content_and_empty_body() -> None:
    """`content` 原样透传；两者皆空给空字节。"""
    raw = ServiceRequest(service="platform", method="POST", path="/api/v1/a/b", content=b"raw")
    assert request_payload(raw) == b"raw"
    empty = ServiceRequest(service="platform", method="POST", path="/api/v1/a/b")
    assert request_payload(empty) == b""


def test_request_payload_rejects_both_bodies() -> None:
    """`json_body` 与 `content` 同时给 —— 拒，不猜优先级。"""
    request = ServiceRequest(
        service="platform",
        method="POST",
        path="/api/v1/a/b",
        json_body=ConcurrentStableFrozenDict({"a": 1}),
        content=b"raw",
    )
    with pytest.raises(ParamError):
        request_payload(request)


def test_to_bms_error_maps_param_error() -> None:
    """参数错误 → `ParamError`（10001），原始码只进 `data`。"""
    error = to_bms_error(RpcCallError(350018, "帧非法", category=ErrorCategory.PARAM_ERROR, layer="protocol"))
    assert isinstance(error, ParamError)
    assert error.code == int(ErrorCode.PARAM)
    detail = cast("Mapping[str, object]", error.data)
    assert detail["code"] == 350018
    assert detail["category"] == ErrorCategory.PARAM_ERROR.value


def test_to_bms_error_keeps_business_code() -> None:
    """业务拒绝 → `BizError` 保留原始码（方法未注册不能被翻译成「下游不可用」）。"""
    error = to_bms_error(RpcCallError(350023, "方法未注册", category=ErrorCategory.BUSINESS_REJECT, layer="business"))
    assert isinstance(error, BizError)
    assert error.code == 350023


def test_to_bms_error_business_code_zero_falls_back_to_unavailable() -> None:
    """业务拒绝但码缺失（0）→ 回落平台不可用码，不抛一个 `error.0` 给前端。"""
    error = to_bms_error(RpcCallError(0, "无码", category=ErrorCategory.BUSINESS_REJECT))
    assert error.code == int(ErrorCode.SERVICE_UNAVAILABLE)


def test_to_bms_error_maps_rate_limited_with_retry_after() -> None:
    """`350005` 是瞬时故障里唯一单列的码 → `RateLimitError`（10005）并保留建议等待。"""
    error = to_bms_error(
        RpcCallError(
            350005,
            "限流",
            retryable=True,
            category=ErrorCategory.TRANSIENT,
            retry_after_ms=1500,
            attempts=2,
            backoff_ms=(100,),
        )
    )
    assert isinstance(error, RateLimitError)
    assert error.code == int(ErrorCode.RATE_LIMIT)
    detail = cast("Mapping[str, object]", error.data)
    assert isinstance(detail, Mapping)
    assert detail["retry_after_ms"] == 1500
    assert detail["attempts"] == 2
    assert detail["backoff_ms"] == [100]


def test_to_bms_error_maps_rate_limited_without_retry_after() -> None:
    """`350005` 没给建议等待时不多塞字段（`data` 只放真实存在的值）。"""
    error = to_bms_error(RpcCallError(350005, "限流", retryable=True, category=ErrorCategory.TRANSIENT))
    detail = cast("Mapping[str, object]", error.data)
    assert "retry_after_ms" not in detail


def test_to_bms_error_maps_other_transient_to_unavailable() -> None:
    """其余瞬时故障 → `ServiceUnavailableError`（10007），不重写判定。"""
    error = to_bms_error(RpcCallError(350022, "存储水位", retryable=True, category=ErrorCategory.TRANSIENT, attempts=1))
    assert isinstance(error, ServiceUnavailableError)
    assert error.code == int(ErrorCode.SERVICE_UNAVAILABLE)
    detail = cast("Mapping[str, object]", error.data)
    assert isinstance(detail, Mapping)
    assert detail["code"] == 350022


def test_to_bms_error_maps_timeout_to_unknown_outcome() -> None:
    """预算耗尽（350004）→ 不可用 + `outcome=unknown`：结果未知，不是失败。"""
    error = to_bms_error(RpcCallTimeoutError("预算耗尽", budget_ms=1000))
    assert isinstance(error, ServiceUnavailableError)
    detail = cast("Mapping[str, object]", error.data)
    assert isinstance(detail, Mapping)
    assert detail["code"] == 350004
    assert detail["outcome"] == OUTCOME_UNKNOWN


def test_to_bms_error_logs_server_bug() -> None:
    """服务端 bug → 不可用 + 告警事件（排障面靠这条日志）。"""
    with capture_logs() as logs:
        error = to_bms_error(RpcCallError(350099, "崩了", category=ErrorCategory.SERVER_BUG))
    assert isinstance(error, ServiceUnavailableError)
    assert any(entry.get("event") == "msg_rpc_server_bug" for entry in logs)
