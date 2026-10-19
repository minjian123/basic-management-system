"""测试公共基座：三层基类（Db / Api / Service）可用性（Kiwi 2317）。"""

from collections.abc import AsyncIterator
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from bms_core.testing import ApiTestCase, DbTestCase, ServiceTestCase


class TestDbLayer(DbTestCase):
    """数据库层基类：`db_session` 回滚夹具可用。"""

    @pytest.mark.kiwi_id(2317)
    async def test_session_usable(self, db_session: AsyncSession) -> None:
        """会话可执行查询（表结构由基类按模型元数据建好）。"""
        result = await db_session.execute(text("SELECT 1"))
        assert result.scalar_one() == 1


class TestApiLayer(ApiTestCase):
    """接口层基类：`client` 内存客户端可用。"""

    @pytest.fixture
    async def service_app(self) -> AsyncIterator[FastAPI]:
        """最小应用（单条路由）。

        Yields:
            FastAPI: 应用实例。
        """
        app = FastAPI()

        @app.get("/ping")
        async def ping() -> str:  # pyright: ignore[reportUnusedFunction]
            """探针路由。

            Returns:
                str: 固定响应。
            """
            return "ok"

        yield app

    @pytest.mark.kiwi_id(2317)
    async def test_client_roundtrip(self, client: AsyncClient) -> None:
        """经 ASGITransport 调用应用。"""
        response = await client.get("/ping")

        assert response.status_code == 200
        assert response.json() == "ok"


class _Factory:
    """应用工厂替身。"""

    def create(self, options: Any = None) -> FastAPI:
        """返回最小应用。

        Args:
            options: 忽略。

        Returns:
            FastAPI: 应用实例。
        """
        return FastAPI()


class TestServiceLayer(ServiceTestCase):
    """服务层基类：按子类工厂装配应用。"""

    app_factory = _Factory

    @pytest.mark.kiwi_id(2317)
    async def test_app_assembled(self, service_app: FastAPI) -> None:
        """应用实例经 lifespan 装配后可用。"""
        assert isinstance(service_app, FastAPI)


class TestServiceLayerRequiresFactory(ServiceTestCase):
    """服务层基类：未声明工厂即显式失败。"""

    @pytest.mark.kiwi_id(2317)
    def test_missing_factory_raises(self, request: pytest.FixtureRequest) -> None:
        """未设置 `app_factory` ⇒ RuntimeError（不静默）。"""
        with pytest.raises(RuntimeError):
            request.getfixturevalue("service_app")
