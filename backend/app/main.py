"""BMS 后端入口：应用工厂 create_app()，提供根路由与 /healthz 存活检查。"""

from fastapi import FastAPI

from app import __version__


def create_app() -> FastAPI:
    """创建 FastAPI 应用。

    注册位按序预留：中间件 → 异常处理器 → 路由（02 域实现，01-03 起迁移到 app/api/）。

    Returns:
        FastAPI: 已注册基线配置与端点的应用实例。
    """
    app = FastAPI(title="BMS 基础管理系统", version=__version__)

    # TODO(01-03): 路由迁移至 app/api/router.py 统一 include
    # TODO(02-01/02-02): lifespan 内加载配置与日志
    # TODO(02-03): 注册统一异常处理器（BizError / RequestValidationError / 未捕获异常）

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

    @app.get("/healthz")
    def healthz() -> dict[str, str]:  # pyright: ignore[reportUnusedFunction]
        """存活检查端点。

        Returns:
            dict: 服务状态，固定返回 {"status": "ok"}。
        """
        return {"status": "ok"}

    return app
