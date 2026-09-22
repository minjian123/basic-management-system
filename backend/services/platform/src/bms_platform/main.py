"""BMS 后端入口：应用工厂 `ApplicationFactory`，提供根路由、业务聚合路由与存活检查。

- 应用工厂：`ApplicationFactory.create(None)` 构造 FastAPI 实例（注册中间件 / 路由 / 异常处理器 /
  健康检查）；启动入口见 `app/asgi.py` 的模块级 `app`（`uvicorn bms_platform.asgi:app`）。
- lifespan：启动校验模块注册 → 工厂装配（登记 → 注册表构建 → 关键工厂解析 → 能力装配），
  关闭时先摘流再统一释放异步资源。
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import cast

from fastapi import FastAPI

from bms_core.api.errors import register_exception_handlers
from bms_core.api.middleware import ReadOnlyMiddleware, RequestLoggingMiddleware, TenantMiddleware, TraceIdMiddleware
from bms_core.cache.base import CacheRegion
from bms_core.core.assembly import assemble_plugins, register_platform_plugins
from bms_core.core.config import get_settings, validate_startup
from bms_core.core.factory import BaseApplicationFactory, register_factory, resolve_factory
from bms_core.core.id import IdGeneratorFactory
from bms_core.core.logging import configure_logging, get_logger
from bms_core.core.plugin import build_plugin_registry, resolve_plugin
from bms_core.core.resources import ResourceManager
from bms_core.core.service import attach_service
from bms_core.db.bootstrap import ensure_development_schema
from bms_core.db.engine import EngineFactory
from bms_core.db.health import PrimaryHealth
from bms_core.db.registry import EngineRegistry, pool_budget_warnings, tenant_pool_budget_warnings
from bms_core.db.session import SessionFactory
from bms_core.db.tenant_source import TenantSource
from bms_core.lock.base import BaseDistributedLock
from bms_core.schemas.common import ApiResponse
from bms_core.services.module_registry import ModuleRegistry
from bms_platform import SERVICE_NAME, SERVICE_TITLE, __version__
from bms_platform.api.router import api_router, health_router
from bms_platform.repositories.demo_repository import DemoRepository
from bms_platform.services.demo_service import DemoService


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """应用生命周期：启动校验模块注册 + 工厂 / 插件装配（完成后标记就绪），关闭时先摘流再统一释放异步资源。

    Args:
        app: 应用实例。

    Yields:
        None: 应用运行期。

    Raises:
        RuntimeError: 模块注册校验失败（冲突 / 非法）。
        PluginError: 工厂 / 插件装配失败（非法 provider / 重名 / 契约版本不符 / 依赖不可用）。
    """
    settings = get_settings()
    validate_startup(settings)
    for message in pool_budget_warnings(settings):
        get_logger("bms_core.db").warning("pool_budget_exceeded", detail=message)
    for message in tenant_pool_budget_warnings(settings, settings.tenant.engine_max_active):
        get_logger("bms_core.db").warning("tenant_pool_budget_exceeded", detail=message)
    errors = app.state.module_registry.validate()
    if errors:
        get_logger("bms").critical("模块注册校验失败", errors=errors)
        raise RuntimeError("模块注册校验失败：" + "；".join(errors))
    await assemble_plugins(app, settings, app.state.resources)
    # SQLite 开发库自动建表（按迁移链表集、幂等；非 SQLite 环境自然跳过）
    created = await ensure_development_schema(
        cast("EngineRegistry", app.state.engine_registry),
        settings,
        factory=cast("EngineFactory", app.state.engine_factory),
    )
    if created:
        get_logger("bms_platform.main").info("sqlite_auto_create_done", targets=",".join(created))
    app.state.startup_complete = True
    try:
        yield
    finally:
        app.state.startup_complete = False
        await app.state.resources.aclose()


class ApplicationFactory(BaseApplicationFactory):
    """应用工厂：构造 FastAPI 应用（引导工厂，不注册为可替换实现）。"""

    key: str = "application_factory"

    def create(self, options: None = None) -> FastAPI:
        """创建 FastAPI 应用。

        注册位按序预留：中间件 → 异常处理器 → 路由；能力实例由 lifespan 装配（`assemble_plugins`）。

        Args:
            options: 未使用（零参口径）。

        Returns:
            FastAPI: 已注册基线配置与端点的应用实例。
        """
        app = FastAPI(title=SERVICE_TITLE, version=__version__, lifespan=lifespan)

        # TODO(02-05): demo 服务改由依赖注入提供（get_db 等）

        settings = get_settings()
        configure_logging(settings)

        # 服务运行时：解析服务身份（包声明 + 配置覆盖）→ 绑定日志上下文 → 落 app.state（含停机摘流）
        attach_service(
            app,
            declared_name=SERVICE_NAME,
            version=__version__,
            title=SERVICE_TITLE,
            settings=settings,
        )

        # 中间件先于路由注册（后注册者在外层）：只读标记 → 请求日志 → 链路 id → 租户解析（全局，最内层）；
        # 租户解析位于链路 id 之内，未知 / 停用租户的拒绝响应仍带请求 id 与链路 id。
        app.add_middleware(TenantMiddleware)
        app.add_middleware(TraceIdMiddleware)
        app.add_middleware(RequestLoggingMiddleware, slow_request_ms=settings.log.slow_request_ms)
        app.add_middleware(ReadOnlyMiddleware)

        register_exception_handlers(app)

        app.state.resources = ResourceManager()
        app.state.module_registry = ModuleRegistry()
        app.state.settings = settings
        app.state.startup_complete = False

        # 工厂 / 插件装配前置：平台实现登记 → 注册表构建 → 关键工厂解析（可替换，配置选择）
        register_platform_plugins(settings, app, app.state.resources)
        build_plugin_registry()
        register_factory("engine_factory", "default", EngineFactory)
        register_factory("session_factory", "default", SessionFactory)
        register_factory("id_generator", "default", IdGeneratorFactory)
        engine_factory = cast(
            "EngineFactory",
            resolve_factory("engine_factory", settings.engine_factory.provider),
        )
        cross_instance_lock = cast(
            "BaseDistributedLock",
            resolve_plugin(
                "distributed_lock",
                settings.distributed_lock.provider,
                expected_version=BaseDistributedLock.contract_version,
            ),
        )
        engine_registry = EngineRegistry(
            engine_factory,
            max_active=settings.tenant.engine_max_active,
            idle_timeout=settings.tenant.engine_idle_timeout,
            lock=cross_instance_lock,
        )
        session_factory = cast(
            "SessionFactory",
            resolve_factory("session_factory", settings.session_factory.provider),
        )
        primary_health = PrimaryHealth(engine_factory)
        tenant_source = TenantSource(
            engine_registry,
            cache=cast(
                "CacheRegion",
                resolve_plugin("cache", settings.cache.provider, expected_version=CacheRegion.contract_version),
            ),
            session_factory=session_factory,
            cache_ttl=settings.tenant.resolve_cache_ttl,
        )
        app.state.engine_factory = engine_factory
        app.state.engine_registry = engine_registry
        app.state.session_factory = session_factory
        app.state.primary_health = primary_health
        app.state.tenant_source = tenant_source
        app.state.resources.register(engine_registry)
        app.state.resources.register(primary_health)

        app.state.demo_service = DemoService(DemoRepository())

        @app.get("/")
        def root() -> ApiResponse:  # pyright: ignore[reportUnusedFunction]
            """应用信息。

            Returns:
                ApiResponse: {code, message, data:{name, version}}。
            """
            return ApiResponse.ok({"name": SERVICE_TITLE, "version": __version__})

        app.include_router(api_router)
        app.include_router(health_router)

        return app
