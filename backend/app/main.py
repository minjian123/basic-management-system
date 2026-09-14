"""BMS 后端入口：应用工厂 create_app()，提供根路由、业务聚合路由与存活检查。"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import __version__
from app.api.errors import register_exception_handlers
from app.api.router import api_router, health_router
from app.captcha.base import NullCaptcha
from app.circuit.base import NullCircuitBreaker
from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.core.resources import ResourceManager
from app.db.engine import EngineFactory
from app.db.registry import EngineRegistry
from app.fallback.base import NullFallbackPolicy
from app.idempotency.base import NullIdempotencyStore
from app.lock.base import NullDistributedLock
from app.masking.base import NullMasker
from app.password.base import NullPasswordPolicy
from app.permission.base import NullPermissionChecker
from app.ratelimit.base import NullRateLimiter
from app.replay.base import NullReplayGuard
from app.repositories.demo_repository import DemoRepository
from app.schemas.common import ApiResponse
from app.services.demo_service import DemoService
from app.services.module_registry import ModuleRegistry


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """应用生命周期：启动校验模块注册，关闭时统一释放异步资源。

    Args:
        app: 应用实例。

    Yields:
        None: 应用运行期。

    Raises:
        RuntimeError: 模块注册校验失败（冲突 / 非法）。
    """
    errors = app.state.module_registry.validate()
    if errors:
        get_logger("bms").critical("模块注册校验失败", errors=errors)
        raise RuntimeError("模块注册校验失败：" + "；".join(errors))
    yield
    await app.state.resources.aclose()


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

    engine_factory = EngineFactory(get_settings())
    engine_registry = EngineRegistry(engine_factory)
    resources = ResourceManager()
    resources.register(engine_registry)

    app.state.engine_factory = engine_factory
    app.state.engine_registry = engine_registry
    app.state.resources = resources
    app.state.module_registry = ModuleRegistry()

    # 能力域基座（占位实现）：权限检查器先装配，掩码器依赖其判定 data:plain
    permission_checker = NullPermissionChecker()
    app.state.permission_checker = permission_checker
    app.state.masker = NullMasker(checker=permission_checker)
    app.state.distributed_lock = NullDistributedLock()
    app.state.captcha = NullCaptcha()
    app.state.password_policy = NullPasswordPolicy()
    app.state.fallback_policy = NullFallbackPolicy()
    app.state.circuit_breaker = NullCircuitBreaker()
    app.state.rate_limiter = NullRateLimiter()
    app.state.idempotency_store = NullIdempotencyStore()
    app.state.replay_guard = NullReplayGuard()

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
