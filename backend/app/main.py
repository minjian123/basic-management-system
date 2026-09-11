"""BMS 后端入口：应用工厂 create_app()，提供根路由、业务聚合路由与存活检查。"""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app import __version__
from app.api.router import api_router, health_router
from app.core.exceptions import NotFoundError
from app.repositories.demo_repository import DemoRepository
from app.services.demo_service import DemoService


def create_app() -> FastAPI:
    """创建 FastAPI 应用。

    注册位按序预留：中间件 → 异常处理器 → 路由（统一异常体系等 02 域实现）。

    Returns:
        FastAPI: 已注册基线配置与端点的应用实例。
    """
    app = FastAPI(title="BMS 基础管理系统", version=__version__)

    # TODO(02-01/02-02): lifespan 内加载配置与日志
    # TODO(02-03): 注册统一异常处理器（BizError / RequestValidationError / 未捕获异常）
    # TODO(02-05): demo 服务改由依赖注入提供（get_db 等）

    async def not_found_handler(_request: Request, exc: Exception) -> JSONResponse:
        """NotFoundError → 404（临时实现，02-3 统一异常体系接管后替换）。"""
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    app.add_exception_handler(NotFoundError, not_found_handler)

    app.state.demo_service = DemoService(DemoRepository())

    @app.get("/")
    def root() -> dict[str, object]:  # pyright: ignore[reportUnusedFunction]
        """应用信息（统一响应结构占位，02-3 起换用 ApiResponse）。

        Returns:
            dict: {code, message, data:{name, version}}。
        """
        return {
            "code": 0,
            "message": "ok",
            "data": {"name": "BMS 基础管理系统", "version": __version__},
        }

    app.include_router(api_router, prefix="/api/v1")
    app.include_router(health_router)

    return app
