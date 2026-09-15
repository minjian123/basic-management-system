"""契约套件夹具：会话级保证默认注册表已完成平台实现登记与构建（幂等）。"""

import pytest

from tests.contracts.support import build_snapshot


@pytest.fixture(scope="session", autouse=True)
def plugin_snapshot() -> None:
    """会话级快照前置：单文件运行（如仅域用例）时同样可用默认注册表。"""
    build_snapshot()
