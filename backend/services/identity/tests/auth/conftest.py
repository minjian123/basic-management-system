"""认证测试包公共夹具入口（04-6-2 单库叠加口径）。

**不再逐例清空 `sys_session`**：会话表落共享租户库、全 worker 共用，整表 `delete` 会删掉并行
worker 正在断言的会话（历史现象：踢出 404、登出后存储标记仍在、列表 total 偏小）。
改由用例自己划命名空间——用户主键 / 会话主键按 `session_helpers.uid()` / `sid()` 派生，
断言按 `user_id` 精确筛选（见 `session_helpers` 模块 docstring）。
"""

import pytest


@pytest.fixture(autouse=True)
def shared_tenant(tenant_db: None) -> None:  # pyright: ignore[reportUnusedFunction]
    """本目录用例切到**共享租户库**（目录级接线，逐目录推进；实现见套件 `conftest.tenant_db`）。

    Args:
        tenant_db: 共享租户库接线（把 `BMS_DATABASE__TENANTS__URL` 指向 `.cache/test/tenant.db`）。
    """
