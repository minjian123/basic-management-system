"""请求上下文变量测试（Kiwi 25）：租户上下文。"""

import pytest

from app.core.context import get_current_tenant, reset_current_tenant, set_current_tenant


@pytest.mark.kiwi_id(36)
def test_current_tenant_context() -> None:
    """租户上下文：设置 / 读取 / 复位。"""
    assert get_current_tenant() is None
    token = set_current_tenant("demo")
    assert get_current_tenant() == "demo"
    reset_current_tenant(token)
    assert get_current_tenant() is None
