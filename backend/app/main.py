"""BMS 后端入口：应用工厂 create_app()，提供根路由、业务聚合路由与存活检查。"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import __version__
from app.api.errors import register_exception_handlers
from app.api.middleware import RequestLoggingMiddleware, TraceIdMiddleware
from app.api.router import api_router, health_router
from app.core.assembly import assemble_plugins, register_platform_plugins
from app.core.config import get_settings, validate_startup
from app.core.logging import configure_logging, get_logger
from app.core.plugin import build_plugin_registry
from app.core.resources import ResourceManager
from app.db.engine import EngineFactory
from app.db.registry import EngineRegistry
from app.health.checks import DatabaseHealthCheck, RedisHealthCheck
from app.health.registry import HealthCheckRegistry
from app.repositories.demo_repository import DemoRepository
from app.schemas.common import ApiResponse
from app.services.demo_service import DemoService
from app.services.module_registry import ModuleRegistry


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """应用生命周期：启动校验模块注册 + 插件装配（完成后标记就绪），关闭时先摘流再统一释放异步资源。

    Args:
        app: 应用实例。

    Yields:
        None: 应用运行期。

    Raises:
        RuntimeError: 模块注册校验失败（冲突 / 非法）。
        PluginError: 插件装配失败（非法 provider / 重名 / 契约版本不符 / 依赖不可用）。
    """
    settings = get_settings()
    validate_startup(settings)
    errors = app.state.module_registry.validate()
    if errors:
        get_logger("bms").critical("模块注册校验失败", errors=errors)
        raise RuntimeError("模块注册校验失败：" + "；".join(errors))
    register_platform_plugins(settings)
    build_plugin_registry()
    await assemble_plugins(app, settings, app.state.resources)
    app.state.startup_complete = True
    try:
        yield
    finally:
        app.state.startup_complete = False
        await app.state.resources.aclose()


def create_app() -> FastAPI:
    """创建 FastAPI 应用。

    注册位按序预留：中间件 → 异常处理器 → 路由；能力实例由 lifespan 装配（`assemble_plugins`）。

    Returns:
        FastAPI: 已注册基线配置与端点的应用实例。
    """
    app = FastAPI(title="BMS 基础管理系统", version=__version__, lifespan=lifespan)

    # TODO(02-05): demo 服务改由依赖注入提供（get_db 等）

    settings = get_settings()
    configure_logging(settings)

    # 中间件先于路由注册：请求日志外层（request_id 先生效）→ 入站链路 id 贯穿（缺失回退 request_id）
    app.add_middleware(TraceIdMiddleware)
    app.add_middleware(RequestLoggingMiddleware, slow_request_ms=settings.log.slow_request_ms)

    register_exception_handlers(app)

    engine_factory = EngineFactory(get_settings())
    engine_registry = EngineRegistry(engine_factory)
    resources = ResourceManager()
    resources.register(engine_registry)

    app.state.engine_factory = engine_factory
    app.state.engine_registry = engine_registry
    app.state.resources = resources
    app.state.module_registry = ModuleRegistry()
    app.state.startup_complete = False

    # 健康检查（03-3 真实探针）：注册表 + redis / database 检查项；redis 客户端随应用生命周期释放
    health_registry = HealthCheckRegistry(
        check_timeout_ms=settings.health.check_timeout_ms,
        total_timeout_ms=settings.health.total_timeout_ms,
    )
    redis_check = RedisHealthCheck(settings.redis.url)
    health_registry.register(redis_check)
    health_registry.register(DatabaseHealthCheck(engine_registry))
    resources.register(redis_check)
    app.state.health_check_registry = health_registry

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
