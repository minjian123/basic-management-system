"""03-6 用例：错误对象（Kiwi 2510）。

覆盖要点：可读串含「码 / 类别 / 动作」三段（排障时不必再翻码表）；未给 `data` 时为空映射；
给出的 `data`（`leader` / `epoch`）与建议重试间隔原样保留。
"""

from __future__ import annotations

from typing import cast

import pytest

from bms_core.core.concurrent import ConcurrentStableFrozenDict
from bms_core.msgclient.errors import ErrorCategory
from bms_core.msgclient.messaging import ClientAction, MsgClientError

pytestmark = pytest.mark.kiwi_id(2510)


def test_error_str_and_default_data() -> None:
    """未给 `data` 时为空映射，可读串含码 / 类别 / 动作。"""
    error = MsgClientError(
        code=350033,
        category=ErrorCategory.TRANSIENT,
        action=ClientAction.REFRESH,
        message="非 leader",
    )
    assert str(error) == "350033 transient refresh: 非 leader"
    assert error.data == ConcurrentStableFrozenDict[str, object]()


def test_error_keeps_given_data() -> None:
    """给出的 `data`（含 leader / epoch）与建议间隔原样保留，供改投使用。"""
    error = MsgClientError(
        code=350033,
        category=ErrorCategory.TRANSIENT,
        action=ClientAction.REFRESH,
        message="非 leader",
        data=ConcurrentStableFrozenDict({"leader": "msg-2", "epoch": 3}),
        retry_after_ms=100,
    )
    data = cast("ConcurrentStableFrozenDict[str, object]", error.data)
    assert data.get("leader") == "msg-2"
    assert error.retry_after_ms == 100
