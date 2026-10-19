"""HTTP 接口测试基类（13_04）：`client` 类内夹具。

`service_app` 由各服务 conftest 提供（应用工厂不同），本基类只统一客户端构造方式。
"""

from collections.abc import AsyncIterator

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from bms_core.testing.base import BaseTestCase


class ApiTestCase(BaseTestCase):
    """接口用例基类：提供 ASGI 内存客户端。"""

    @pytest.fixture
    async def client(self, service_app: FastAPI) -> AsyncIterator[AsyncClient]:
        """ASGI 内存客户端（复用 `service_app`；认证头由子类 / conftest 追加）。

        Args:
            service_app: 服务应用实例（仓库 / 服务 conftest 提供）。

        Yields:
            AsyncClient: 测试客户端。
        """
        async with AsyncClient(transport=ASGITransport(app=service_app), base_url="http://test") as client:
            yield client
