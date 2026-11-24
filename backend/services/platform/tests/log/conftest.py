"""审计日志域用例夹具：共享平台库会话（分片台账表 / 分片表）。"""

from collections.abc import AsyncIterator

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from tests_support.shared_access import shared_write


@pytest_asyncio.fixture
async def log_session(shared_platform_engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    """共享平台库写会话（分片台账表由数据初始化建好；分片表由仓储运行期创建）。

    Args:
        shared_platform_engine: 共享平台库门代理引擎。

    Yields:
        AsyncSession: 共享平台库写会话。
    """
    async with shared_write(shared_platform_engine) as session:
        yield session
