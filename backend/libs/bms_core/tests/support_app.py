"""基座测试支撑：最小测试服务应用工厂（无业务路由），供共享能力域测试构造应用与探针。

共享能力域实现留 `bms_core`，其测试不依赖具体服务；本模块提供等价于服务应用工厂的测试应用，
使原经 `bms_platform.main` 构造应用的契约测试可迁入基座测试并保持断言不变。
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from bms_core.application import BaseServiceApplicationFactory, service_lifespan


class ApplicationFactory(BaseServiceApplicationFactory):
    """基座测试用应用工厂（无业务路由，装配全部内建插件）。"""

    key: str = "application_factory"
    service_name: str = "core_test"
    service_title: str = "BMS 基座测试服务"
    version: str = "0.1.0"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """测试用 lifespan（转调共享 `service_lifespan`，兼容 `async with lifespan(app)` 用法）。

    Args:
        app: 应用实例。

    Yields:
        None: 应用运行期。
    """
    async with service_lifespan(app):
        yield
