"""公告应读人数读取（Kiwi 2518）：成功 / 非 2xx / 响应非法 / 下游不可用。"""

# pyright: reportPrivateUsage=false, reportUnknownLambdaType=false, reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false, reportUnknownParameterType=false, reportDeprecated=false, reportUntypedFunctionDecorator=false, reportCallIssue=false
from __future__ import annotations

from typing import cast

import pytest

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.exceptions import NoticeAudienceUnavailableError, ServiceUnavailableError
from bms_notification.domains.notification.services.notice_audience import NoticeAudienceReader
from notice._support import reset_user, use_user

pytestmark = pytest.mark.kiwi_id(2518)


class _Response:
    """服务调用响应替身。"""

    def __init__(self, status_code: int, body: object) -> None:
        self.status_code = status_code
        self._body = body

    def payload(self) -> object:
        """返回响应体。

        Returns:
            object: 响应体。
        """
        return self._body


class _Client:
    """服务调用客户端替身。"""

    def __init__(self, response: _Response | None = None, *, error: Exception | None = None) -> None:
        self.response = response
        self.error = error
        self.requests: ConcurrentStableList[object] = ConcurrentStableList()

    async def call(self, request: object) -> _Response:
        """记录请求并返回预设响应。

        Args:
            request: 服务请求。

        Returns:
            _Response: 响应。

        Raises:
            Exception: 预设异常。
        """
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        if self.response is None:  # pragma: no cover - 测试始终给响应或异常
            raise AssertionError("缺少响应")
        return self.response


def _reader(client: _Client) -> NoticeAudienceReader:
    """构造读取器（客户端替身）。

    Args:
        client: 客户端替身。

    Returns:
        NoticeAudienceReader: 读取器。
    """
    return NoticeAudienceReader(cast("object", client))  # pyright: ignore[reportArgumentType]


async def test_count_enabled_success() -> None:
    """成功读取 total，并携带租户与筛选参数。"""
    tokens = use_user(1)
    try:
        client = _Client(_Response(200, {"code": 0, "data": {"total": 7}}))
        assert await _reader(client).count_enabled() == 7
        request = client.requests[0]
        assert getattr(request, "tenant_id", None) is not None
    finally:
        reset_user(tokens)


async def test_count_enabled_failures() -> None:
    """非 2xx / 非 JSON / 业务码非 0 / 缺 data / total 非法 / 下游不可用均 70206。"""
    tokens = use_user(1)
    try:
        cases = (
            _Client(_Response(503, {})),
            _Client(_Response(200, "not-json")),
            _Client(_Response(200, {"code": 30001, "message": "denied"})),
            _Client(_Response(200, {"code": 0, "data": "bad"})),
            _Client(_Response(200, {"code": 0, "data": {}})),
            _Client(_Response(200, {"code": 0, "data": {"total": -1}})),
            _Client(error=ServiceUnavailableError("down")),
        )
        for client in cases:
            with pytest.raises(NoticeAudienceUnavailableError):
                await _reader(client).count_enabled()
    finally:
        reset_user(tokens)


async def test_count_enabled_missing_message() -> None:
    """业务码非 0 且无 message 时仍抛 70206（覆盖消息回退分支）。"""
    tokens = use_user(1)
    try:
        client = _Client(_Response(200, {"code": 30001}))
        with pytest.raises(NoticeAudienceUnavailableError):
            await _reader(client).count_enabled()
        assert client.requests
    finally:
        reset_user(tokens)
