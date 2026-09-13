"""BMS 后端入口：应用工厂 create_app()，提供根路由、业务聚合路由与存活检查。"""

from fastapi import FastAPI

from app import __version__
from app.api.errors import register_exception_handlers
from app.api.router import api_router, health_router
from app.repositories.demo_repository import DemoRepository
from app.schemas.common import ApiResponse
from app.services.demo_service import DemoService


def create_app() -> FastAPI:
    """创建 FastAPI 应用。

    注册位按序预留：中间件 → 异常处理器 → 路由。

    Returns:
        FastAPI: 已注册基线配置与端点的应用实例。
    """
    app = FastAPI(title="BMS 基础管理系统", version=__version__)

    # TODO(02-01/02-02): lifespan 内加载配置与日志
    # TODO(02-05): demo 服务改由依赖注入提供（get_db 等）

    register_exception_handlers(app)

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
