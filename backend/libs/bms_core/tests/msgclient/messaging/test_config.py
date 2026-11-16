"""03-6 用例：客户端配置校验（Kiwi 2510）。

覆盖要点：地址 / 租户 / 数值三类构造期校验；空地址池两条来路（显式传空、走默认工厂）。
配置错在构造期就报，比第一次发布时才在拼 URL 或查询参数处炸更好定位。
"""

from __future__ import annotations

from dataclasses import replace

import pytest
from msgclient_support.rpc_retry import FakeClock, FixedJitter

from bms_core.core.concurrent import ConcurrentStableFrozenList
from bms_core.core.exceptions import ParamError
from bms_core.msgclient.messaging import MessagingConfig
from bms_core.msgclient.retry import JitterMode, RetryPolicy

pytestmark = pytest.mark.kiwi_id(2510)


def _config(**overrides: object) -> MessagingConfig:
    """构造配置（直接展开字段，便于逐字段断言校验失败）。

    Args:
        overrides: 覆盖字段。

    Returns:
        MessagingConfig: 配置。
    """
    base = MessagingConfig(
        endpoints=ConcurrentStableFrozenList(["http://msg-1:8000"]),
        tenant="t1",
        retry=RetryPolicy(jitter=JitterMode.NONE),
        clock=FakeClock(),
        jitter=FixedJitter([1]),
    )
    return replace(base, **overrides)


def test_config_accepts_valid_values() -> None:
    """合法配置可直接构造，字段按入参落位。"""
    config = _config()
    assert config.endpoints[0] == "http://msg-1:8000"
    assert config.tenant == "t1"
    assert config.retry.max_retries == RetryPolicy().max_retries


def test_config_rejects_empty_endpoints() -> None:
    """地址池显式传空：构造期即失败。"""
    with pytest.raises(ParamError, match="endpoints 不能为空"):
        _config(endpoints=ConcurrentStableFrozenList[str]())


def test_config_default_endpoints_factory_is_empty_then_rejected() -> None:
    """不传地址池：默认工厂给出空列表，随即被校验拒绝（默认值不会静默放行）。"""
    with pytest.raises(ParamError, match="endpoints 不能为空"):
        MessagingConfig(tenant="t1")


@pytest.mark.parametrize(
    ("endpoint", "message"),
    [
        ("ftp://msg-1:8000", "协议必须是 http 或 https"),
        ("http:///msg", "缺少主机"),
        ("http://msg-1:8000/api", "不得带路径"),
        ("http://msg-1:8000?a=1", "不得带路径"),
        ("http://msg-1:8000#x", "不得带路径"),
    ],
)
def test_config_rejects_bad_endpoint(endpoint: str, message: str) -> None:
    """地址形态非法：协议 / 主机 / 路径 / 查询 / 片段五类各拒一次。

    Args:
        endpoint: 非法地址。
        message: 期望提示片段。
    """
    with pytest.raises(ParamError, match=message):
        _config(endpoints=ConcurrentStableFrozenList([endpoint]))


def test_config_rejects_empty_tenant() -> None:
    """租户为空：拒绝（数据面解析链会按未知租户 350012 拒，早点说清更好）。"""
    with pytest.raises(ParamError, match="tenant 不能为空"):
        _config(tenant="  ")


@pytest.mark.parametrize(
    "field",
    [
        "connect_timeout_ms",
        "request_timeout_ms",
        "refresh_min_interval_ms",
        "max_redirects",
        "idempotency_ttl_ms",
        "idempotency_capacity",
        "publish_concurrency",
    ],
)
def test_config_rejects_non_positive_values(field: str) -> None:
    """数值字段非正数：逐个拒绝（0 和非正数都得拦）。

    Args:
        field: 字段名。
    """
    with pytest.raises(ParamError, match="必须为正整数"):
        _config(**{field: 0})
