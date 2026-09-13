"""BMS 后端入口：应用工厂 create_app()，提供根路由、业务聚合路由与存活检查。"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import __version__
from app.api.errors import register_exception_handlers
from app.api.router import api_router, health_router
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.engine import EngineFactory
from app.repositories.demo_repository import DemoRepository
from app.schemas.common import ApiResponse
from app.services.demo_service import DemoService


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """应用生命周期：关闭时统一释放异步资源。

    Args:
        app: 应用实例。

    Yields:
        None: 应用运行期。
    """
    yield
    await app.state.engine_factory.aclose()


def create_app() -> FastAPI:
    """创建 FastAPI 应用。

    注册位按序预留：中间件 → 异常处理器 → 路由。

    Returns:
        FastAPI: 已注册基线配置与端点的应用实例。
    """
    app = FastAPI(title="BMS 基础管理系统", version=__version__, lifespan=lifespan)

    # TODO(02-05): demo 服务改由依赖注入提供（get_db 等）

    configure_logging(get_settings())

    register_exception_handlers(app)

    app.state.engine_factory = EngineFactory(get_settings())
    app.state.demo_service = DemoService(DemoRepository())

    @app.get("/")
    def root() -> ApiResponse:  # pyright: ignore[reportUnusedFunction]
        """应用信息。

        Returns:
            ApiResponse: {code, message, data:{name, version}}。
        """
        return ApiResponse.ok({"name": "BMS 基础管理系统", "version": __version__})

    app.include_router(api_router, prefix="/api/v1")
    app.include_router(health_router)

    return app
