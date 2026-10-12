"""请求上下文变量测试（Kiwi 25 租户 / Kiwi 44 链路）：设置 / 读取 / 复位。"""

import pytest

from bms_core.core.context import (
    get_current_span_id,
    get_current_tenant,
    get_current_tenant_id,
    get_current_trace_id,
    reset_current_span_id,
    reset_current_tenant,
    reset_current_tenant_id,
    reset_current_trace_id,
    set_current_span_id,
    set_current_tenant,
    set_current_tenant_id,
    set_current_trace_id,
)


@pytest.mark.kiwi_id(36)
def test_current_tenant_context() -> None:
    """租户上下文：设置 / 读取 / 复位。"""
    assert get_current_tenant() is None
    token = set_current_tenant("demo")
    assert get_current_tenant() == "demo"
    reset_current_tenant(token)
    assert get_current_tenant() is None


@pytest.mark.kiwi_id(36)
def test_current_tenant_id_context() -> None:
    """租户主键上下文（雪花 id 字符串）：设置 / 读取 / 复位。"""
    assert get_current_tenant_id() is None
    token = set_current_tenant_id("1002")
    assert get_current_tenant_id() == "1002"
    reset_current_tenant_id(token)
    assert get_current_tenant_id() is None


@pytest.mark.kiwi_id(44)
def test_trace_context() -> None:
    """链路上下文（链路 id / span id）：设置 / 读取 / 复位。"""
    assert get_current_trace_id() is None
    assert get_current_span_id() is None

    trace_token = set_current_trace_id("a" * 32)
    span_token = set_current_span_id("b" * 16)
    assert get_current_trace_id() == "a" * 32
    assert get_current_span_id() == "b" * 16

    reset_current_span_id(span_token)
    reset_current_trace_id(trace_token)
    assert get_current_trace_id() is None
    assert get_current_span_id() is None
