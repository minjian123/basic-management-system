"""角色域用例的收尾：释放 `helpers.session()` 顺带建的平台库引擎。

角色域跨两库（角色 / 授权在租户库，元数据在平台库），`helpers.session()` 会一并建平台库会话；
用例只 `dispose` 自己的租户库引擎，平台库那份在这里统一收，避免每个用例都写一遍。
"""

from collections.abc import AsyncIterator

import pytest

from tests.role import helpers


@pytest.fixture(autouse=True)
async def _close_role_helpers() -> AsyncIterator[None]:
    """用例结束后释放平台库引擎。"""
    yield
    await helpers.close_all()
