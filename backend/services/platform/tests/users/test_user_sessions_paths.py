"""用户会话失效通道补齐用例（`bms_platform/services/user_sessions.py`）。

覆盖：下游非 200 → 记日志并不阻断；内部出口响应体解析的回落分支。
"""

from __future__ import annotations

from typing import Any, cast

from bms_core.servicecall.base import ServiceRequest, ServiceResponse
from bms_platform.domains.user.services.user_sessions import (
    REASON_USER_DISABLED,
    UserSessionClient,
    _read_revoked,  # pyright: ignore[reportPrivateUsage]
)


class _Client:
    """服务间客户端替身：恒定返回预置响应。"""

    def __init__(self, response: ServiceResponse) -> None:
        """初始化。

        Args:
            response: 预置响应。
        """
        self.response = response

    async def call(self, request: ServiceRequest) -> ServiceResponse:
        """返回预置响应。

        Args:
            request: 服务间请求（忽略）。

        Returns:
            ServiceResponse: 预置响应。
        """
        del request
        return self.response


async def test_revoke_returns_false_on_non_200() -> None:
    """下游非 200：记日志并回 False（不阻断主流程）。"""
    client = UserSessionClient(cast("Any", _Client(ServiceResponse(status_code=503))))
    assert await client.revoke_user_sessions(1, reason=REASON_USER_DISABLED) is False


def test_read_revoked_fallback_paths() -> None:
    """响应体解析回落：非对象 / `data` 非对象 / `revoked` 非整数 → 0；整数原样。"""
    assert _read_revoked("text") == 0
    assert _read_revoked({"data": "x"}) == 0
    assert _read_revoked({"data": {"revoked": "5"}}) == 0
    assert _read_revoked({"data": {"revoked": 5}}) == 5
