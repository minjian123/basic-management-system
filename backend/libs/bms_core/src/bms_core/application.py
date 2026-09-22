"""服务应用装配基座：把每服务都需要的应用构造与生命周期收敛到共享库。

- `service_lifespan`：共享应用生命周期——启动校验模块注册 + 工厂 / 插件装配（完成后标记就绪），
  关闭时先取消就绪再统一释放异步资源；与 02_02 平台服务语义一致。
- `BaseServiceApplicationFactory`：服务应用工厂基座（继承 `BaseApplicationFactory`）——承载通用装配
  编排（服务身份 / 中间件 / 异常处理 / 状态与前缀工厂 / 引擎注册表 / 租户源 / 插件装配 / 探针），
  各服务只声明身份、业务路由与可选钩子，装配行为不改。

服务侧用法：声明 `service_name` / `service_title` / `version`，覆写 `service_routers()` 返回业务路由；
需要服务专属 state（如 demo 服务）覆写 `configure_service()`，需要创建前调整配置覆写 `prepare_settings()`。
"""

from collections.abc import AsyncGenerator, Sequence
from contextlib import asynccontextmanager
from typing import cast

from fastapi import APIRouter, FastAPI

from bms_core.api import health
from bms_core.api.errors import register_exception_handlers
from bms_core.api.middleware import ReadOnlyMiddleware, RequestLoggingMiddleware, TenantMiddleware, TraceIdMiddleware
from bms_core.cache.base import CacheRegion
from bms_core.core.assembly import assemble_plugins, register_platform_plugins
from bms_core.core.config import Settings, get_settings, validate_startup
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

__all__ = ["BaseServiceApplicationFactory", "service_lifespan"]

_LOGGER = "bms_core.application"


@asynccontextmanager
async def service_lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """服务生命周期：启动校验模块注册 + 工厂 / 插件装配（完成后标记就绪），关闭时统一释放异步资源。

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
    errors = cast("ModuleRegistry", app.state.module_registry).validate()
    if errors:
        get_logger("bms").critical("模块注册校验失败", errors=errors)
        raise RuntimeError("模块注册校验失败：" + "；".join(errors))
    await assemble_plugins(app, settings, cast("ResourceManager", app.state.resources))
    created = await ensure_development_schema(
        cast("EngineRegistry", app.state.engine_registry),
        settings,
        factory=cast("EngineFactory", app.state.engine_factory),
    )
    if created:
        get_logger(_LOGGER).info("sqlite_auto_create_done", targets=",".join(created))
    app.state.startup_complete = True
    try:
        yield
    finally:
        app.state.startup_complete = False
        await cast("ResourceManager", app.state.resources).aclose()


class BaseServiceApplicationFactory(BaseApplicationFactory):
    """服务应用工厂基座：承载通用装配，各服务只声明身份与路由。"""

    key: str = "application_factory"
    service_name: str = ""
    """服务名（`[app].service` 为空时取本声明；用于日志 `service`、探针响应与按服务配置）。"""
    service_title: str = ""
    """服务中文名（用于应用 title 与根路由）。"""
    version: str = "0.1.0"
    """服务版本（取服务包 `__version__`）。"""

    def service_routers(self) -> Sequence[APIRouter]:
        """业务路由清单（子类覆写；探针路由由基座统一挂载，无需返回）。

        Returns:
            Sequence[APIRouter]: 业务路由（挂 `/api/v1` 前缀）。
        """
        return ()

    def prepare_settings(self, settings: Settings) -> None:
        """创建前配置调整钩子（默认空实现；如最小服务置空健康 provider）。

        Args:
            settings: 应用配置（可变）。
        """

    def configure_service(self, app: FastAPI, settings: Settings) -> None:
        """服务专属 state 注入钩子（默认空实现；如平台服务注入 demo 服务）。

        Args:
            app: 应用实例。
            settings: 应用配置。
        """

    def create(self, options: None = None) -> FastAPI:
        """创建服务 FastAPI 应用（通用装配编排）。

        Args:
            options: 未使用（零参口径）。

        Returns:
            FastAPI: 已注册基线配置与端点的应用实例。
        """
        settings = get_settings()
        self.prepare_settings(settings)
        configure_logging(settings)

        app = FastAPI(title=self.service_title, version=self.version, lifespan=service_lifespan)

        # 服务运行时：解析服务身份（包声明 + 配置覆盖）→ 绑定日志上下文 → 落 app.state（含停机摘流）
        attach_service(
            app,
            declared_name=self.service_name,
            version=self.version,
            title=self.service_title,
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

        self.configure_service(app, settings)

        @app.get("/")
        def root() -> ApiResponse:  # pyright: ignore[reportUnusedFunction]
            """应用信息。

            Returns:
                ApiResponse: {code, message, data:{name, version}}。
            """
            return ApiResponse.ok({"name": self.service_title, "version": self.version})

        app.include_router(health.router)
        for router in self.service_routers():
            app.include_router(router)

        return app
