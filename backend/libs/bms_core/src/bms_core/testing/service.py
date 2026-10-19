"""服务测试基类（13_04）：按子类声明的应用工厂装配应用。

用法::

    class TestMyService(ServiceTestCase):
        app_factory = ApplicationFactory          # 子类声明工厂类

        async def test_health(self, service_app):
            ...
"""

from collections.abc import AsyncIterator
from typing import Any, ClassVar

import pytest
from fastapi import FastAPI

from bms_core.testing.base import BaseTestCase


class ServiceTestCase(BaseTestCase):
    """服务用例基类：提供 `service_app`（经 lifespan 装配）。"""

    app_factory: ClassVar[Any] = None
    """应用工厂类（子类必须设置；需提供无参 `create(None)`）。"""

    @pytest.fixture
    async def service_app(self) -> AsyncIterator[FastAPI]:
        """服务应用实例（经 lifespan 装配）。

        Yields:
            FastAPI: 应用实例。

        Raises:
            RuntimeError: 子类未设置 `app_factory`。
        """
        if self.app_factory is None:
            raise RuntimeError("ServiceTestCase 子类须设置 app_factory（应用工厂类）")
        app: FastAPI = self.app_factory().create(None)
        async with app.router.lifespan_context(app):
            yield app
