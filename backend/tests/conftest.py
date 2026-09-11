"""pytest 公共夹具：ASGI 内存客户端（免启服务器）。"""

from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import create_app


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    """ASGITransport 异步客户端夹具（每个用例独立应用实例）。"""
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
