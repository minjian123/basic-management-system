"""BMS 后端占位入口：最小 FastAPI 应用工厂，提供 /healthz 存活检查。"""

from fastapi import FastAPI

from app import __version__


def create_app() -> FastAPI:
    """创建 FastAPI 应用（02 起在工厂内注册中间件 / 路由 / 异常处理器）。"""
    app = FastAPI(title="BMS 后端", version=__version__)

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        """存活检查端点。

        Returns:
            dict: 服务状态，固定返回 {"status": "ok"}。
        """
        return {"status": "ok"}

    return app
