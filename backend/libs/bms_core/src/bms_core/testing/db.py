"""数据库测试基类（13_04）：`db_session` 回滚夹具。

- 会话来自 `rollback_session`（外层事务 + savepoint），用例结束整体回滚；
- 依赖仓库级 `platform_db_url` 夹具（会话级种子库）；
- 表结构按已导入模型的 `Base.metadata` 建表（导入服务模型即纳入）。
"""

from collections.abc import AsyncIterator

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from bms_core.models.base import Base
from bms_core.testing.base import BaseTestCase
from bms_core.testing.transaction import rollback_session


class DbTestCase(BaseTestCase):
    """数据库用例基类：提供回滚会话。"""

    @pytest.fixture
    async def db_session(self, platform_db_url: str) -> AsyncIterator[AsyncSession]:
        """回滚会话夹具（非 autouse：子类按需声明参数）。

        Args:
            platform_db_url: 会话级测试库连接串（仓库级夹具提供）。

        Yields:
            AsyncSession: 外层事务上的会话（用例内 commit 只提交 savepoint）。
        """
        engine = create_async_engine(platform_db_url)
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        try:
            async with rollback_session(engine) as session:
                yield session
        finally:
            await engine.dispose()
