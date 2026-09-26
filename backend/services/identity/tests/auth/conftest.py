"""认证测试包公共夹具：会话表按用例清空（租户库为落盘 SQLite，防跨用例 / 跨次运行累积）。"""

from collections.abc import AsyncIterator

import pytest
from fastapi import FastAPI
from sqlalchemy import delete

from bms_core.db.session import session_scope
from bms_core.db.tenant import DEMO_TENANT
from bms_identity.models.session import SysSession


@pytest.fixture(autouse=True)
async def clean_sessions(service_app: FastAPI) -> AsyncIterator[None]:
    """用例前清空演示租户库 `sys_session`（会话断言确定性）。

    Args:
        service_app: 本服务应用实例。

    Yields:
        None: 用例运行期。
    """
    async with session_scope(
        service_app.state.engine_registry, db_key=DEMO_TENANT.db_key, factory=service_app.state.session_factory
    ) as session:
        await session.execute(delete(SysSession))
        await session.commit()
    yield
