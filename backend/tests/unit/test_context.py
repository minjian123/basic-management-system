"""单元测试：请求级上下文（contextvars）。"""

from __future__ import annotations

from app.core.context import get_request_id, get_tenant_code, set_request_id, set_tenant


def test_request_id_roundtrip() -> None:
    """request_id 写入后可读回。"""
    set_request_id("test-123")
    assert get_request_id() == "test-123"
    set_request_id(None)
    assert get_request_id() is None


def test_tenant_context_roundtrip() -> None:
    """租户上下文写入后可读回，平台级请求为 None。"""
    set_tenant("demo")
    assert get_tenant_code() == "demo"
    set_tenant(None)
    assert get_tenant_code() is None


def test_tenant_id_default_none() -> None:
    """tenant_id 默认 None（阶段三 sys_tenant 表就绪后启用）。"""
    set_tenant("demo")
    from app.core.context import get_tenant_id

    assert get_tenant_id() is None
