"""服务应用装配基座：把每服务都需要的应用构造与生命周期收敛到共享库。

- `service_lifespan`：共享应用生命周期——启动校验（离线清单校验 + 开发库自动建表 + 接库服务目录校验）
  + 工厂 / 插件装配（完成后标记就绪），关闭时先取消就绪再统一释放异步资源；与 02_02 平台服务语义一致。
- `BaseServiceApplicationFactory`：服务应用工厂基座（继承 `BaseApplicationFactory`）——承载通用装配
  编排（服务身份 / 中间件 / 异常处理 / 状态与前缀工厂 / 引擎注册表 / 租户源 / 插件装配 / 探针），
  各服务只声明身份、业务路由与可选钩子，装配行为不改。

服务侧用法：声明 `service_name` / `service_title` / `version` / `contract_version`，覆写 `service_routers()`
返回业务路由；服务专属 state 覆写 `configure_service()`，创建前调整配置覆写 `prepare_settings()`。
"""

from collections.abc import AsyncGenerator, Sequence
from contextlib import asynccontextmanager
from typing import cast

from fastapi import APIRouter, FastAPI
from sqlalchemy import select

from bms_core.api import health
from bms_core.api.errors import register_exception_handlers
from bms_core.api.metrics import router as metrics_router
from bms_core.api.middleware import (
    EdgeGuardMiddleware,
    ReadOnlyMiddleware,
    RequestLoggingMiddleware,
    TenantMiddleware,
    TraceIdMiddleware,
)
from bms_core.cache.base import CacheRegion
from bms_core.catalog.loader import load_catalog_snapshot
from bms_core.core.assembly import assemble_plugins, register_platform_plugins
from bms_core.core.config import Settings, get_settings, validate_startup
from bms_core.core.exceptions import CatalogError, EventContractError
from bms_core.core.factory import BaseApplicationFactory, register_factory, resolve_factory
from bms_core.core.id import IdGeneratorFactory
from bms_core.core.logging import configure_logging, get_logger
from bms_core.core.plugin import build_plugin_registry, resolve_plugin
from bms_core.core.resources import ResourceManager
from bms_core.core.service import ServiceIdentity, attach_service
from bms_core.db.bootstrap import ensure_development_schema
from bms_core.db.engine import EngineFactory
from bms_core.db.health import PrimaryHealth
from bms_core.db.keys import PLATFORM_DB_KEY, PLATFORM_SERVICE_KEY
from bms_core.db.registry import EngineRegistry, pool_budget_warnings, tenant_pool_budget_warnings
from bms_core.db.session import SessionFactory, session_scope
from bms_core.db.tenant_remote import register_remote_tenant_source
from bms_core.db.tenant_source import build_tenant_lookup
from bms_core.events.contracts import default_event_contract_registry, validate_event_registry
from bms_core.lock.base import BaseDistributedLock
from bms_core.metrics.base import BaseMetrics
from bms_core.models.ownership import SysTableOwnership
from bms_core.schemas.common import ApiResponse
from bms_core.services.module_registry import (
    SERVICE_CATALOG,
    ModuleRegistry,
    enabled_service_keys,
    known_event_domains,
    validate_catalog,
)
from bms_core.services.table_registry import (
    TABLE_OWNERSHIP,
    TableOwnershipRegistry,
    TableRecord,
    validate_table_ownership,
)
from bms_core.tracing.setup import setup_observability

__all__ = ["BaseServiceApplicationFactory", "service_lifespan"]

_LOGGER = "bms_core.application"


async def _validate_service_catalog(app: FastAPI) -> None:
    """接库服务目录校验：取目录快照校验并拒启（空目录仅告警放行；06_01 起改经契约）。

    取数路径（见 `bms_core/catalog/loader.py`）：

    - `platform`（目录单一权威）：本地读**本服务平台库** `sys_module`，读失败即拒启（`CatalogError`）；
    - 其余服务：经 `service_client` 调 `GET /api/v1/modules/snapshot`；**不可达 / 响应非法时告警放行**
      并置 `app.state.catalog_degraded = True`（`/readyz` 的 `catalog` 非必需项可见降级，不产生 503）。

    Args:
        app: 应用实例（取引擎注册表 / 会话工厂 / 服务身份）。

    Raises:
        CatalogError: 权威服务目录不可读（表缺失 / 连接失败）或校验冲突（唯一 / 对账 / 契约版本）。
    """
    logger = get_logger("bms")
    identity = cast("ServiceIdentity", app.state.service_identity)
    try:
        records = await load_catalog_snapshot(app)
    except CatalogError:
        raise
    except Exception as exc:  # 契约不可达 / 未装配 / 响应非法：降级放行（CI 离线校验为硬门禁）
        logger.warning("service_catalog_snapshot_unavailable", detail=f"{type(exc).__name__}: {exc}")
        app.state.catalog_degraded = True
        return
    if not records:
        logger.warning("service_catalog_empty", hint="服务目录无登记行，跳过接库校验")
        return
    errors = validate_catalog(
        SERVICE_CATALOG,
        records,
        service_key=identity.name,
        contract_version=identity.contract_version,
    )
    if errors:
        logger.critical("service_catalog_invalid", scope="database", errors=errors)
        raise CatalogError("服务目录校验失败：" + "；".join(errors))


async def _validate_table_ownership(app: FastAPI) -> None:
    """表归属登记校验（离线清单 + `platform` 服务接库对账；06_02 承接 06_03 遗留 1）。

    - **离线清单自校验**（零依赖，所有服务执行）：`TABLE_OWNERSHIP` 唯一性 / 格式 / 归属合法，
    违规即拒启（配置级错误，不应放行）；
    - **接库对账**（仅 `platform` 服务——`sys_table_ownership` 归其平台服务库，非其归属库不跨服务直读）：
    读本服务平台服务库与清单双向对账，不一致即拒启（`CatalogError`，登记类冲突复用既有错误码）；
    库不可读（未迁移）→ WARNING 放行 + `app.state.ownership_degraded = True`（与 `catalog` 降级同口径）。

    Args:
        app: 应用实例（取服务身份 / 引擎注册表 / 会话工厂）。

    Raises:
        CatalogError: 离线清单非法或接库对账不一致。
    """
    logger = get_logger("bms")
    errors = TableOwnershipRegistry().validate()
    if errors:
        logger.critical("table_ownership_invalid", scope="offline", errors=errors)
        raise CatalogError("表归属登记校验失败（清单）：" + "；".join(errors))
    identity = cast("ServiceIdentity", app.state.service_identity)
    if identity.name != PLATFORM_SERVICE_KEY:
        return
    try:
        async with session_scope(
            cast("EngineRegistry", app.state.engine_registry),
            db_key=PLATFORM_DB_KEY,
            factory=cast("SessionFactory", app.state.session_factory),
        ) as session:
            statement = select(SysTableOwnership).where(SysTableOwnership.deleted_at.is_(None))
            records = [TableRecord.from_row(row) for row in (await session.execute(statement)).scalars().all()]
    except Exception as exc:  # 库不可读（未迁移）：降级放行（CI 接库对账为硬门禁）
        logger.warning("table_ownership_unavailable", detail=f"{type(exc).__name__}: {exc}")
        app.state.ownership_degraded = True
        return
    if not records:
        logger.warning("table_ownership_empty", hint="表归属登记无登记行，跳过接库对账（先执行 ops.seed_tables）")
        return
    errors = validate_table_ownership(TABLE_OWNERSHIP, records)
    if errors:
        logger.critical("table_ownership_invalid", scope="database", errors=errors)
        raise CatalogError("表归属登记校验失败（接库）：" + "；".join(errors))


async def _record_db_inventory(app: FastAPI, settings: Settings) -> None:
    """记录库数量指标（`bms_db_count`）：启动期记预期平台服务库数与归档库数，并刷新活跃库数。

    口径见 `bms_core/db/inventory.py`：`kind = platform`（预期平台服务库数 = 启用服务数）、
    `kind = archive`（恒 1）、`kind = tenant`（**活跃**租户库数，由引擎注册表随新建 / 回收刷新）；
    Prometheus 暴露端点与看板归阶段八（08_01）。

    Args:
        app: 应用实例（取指标器 / 引擎注册表）。
        settings: 应用配置。
    """
    metrics = cast("BaseMetrics | None", getattr(app.state, "metrics", None))
    if metrics is None:
        return
    service = settings.app.service
    await metrics.gauge(
        "bms_db_count", value=float(len(enabled_service_keys())), labels={"kind": "platform", "service": service}
    )
    await metrics.gauge("bms_db_count", value=1.0, labels={"kind": "archive", "service": service})
    await cast("EngineRegistry", app.state.engine_registry).record_db_counts()


def _validate_event_contracts() -> None:
    """离线事件契约校验：登记契约与订阅（命名 / 事件域 / 版本 / 字段）违规即拒启。

    Raises:
        EventContractError: 契约或订阅校验失败（含事件域未登记、订阅未覆盖当前主版本）。
    """
    errors = validate_event_registry(default_event_contract_registry(), domains=known_event_domains())
    if errors:
        get_logger("bms").critical("event_contract_invalid", errors=errors)
        raise EventContractError("事件契约校验失败：" + "；".join(errors))


@asynccontextmanager
async def service_lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """服务生命周期：启动校验（离线 + 接库）+ 工厂 / 插件装配（完成后标记就绪），关闭时统一释放异步资源。

    Args:
        app: 应用实例。

    Yields:
        None: 应用运行期。

    Raises:
        CatalogError: 服务目录校验失败（离线清单冲突 / 接库冲突 / 库不可读）。
        EventContractError: 事件契约或订阅校验失败。
        PluginError: 工厂 / 插件装配失败（非法 provider / 重名 / 契约版本不符 / 依赖不可用）。
    """
    settings = get_settings()
    validate_startup(settings)
    for message in pool_budget_warnings(settings):
        get_logger("bms_core.db").warning("pool_budget_exceeded", detail=message)
    for message in tenant_pool_budget_warnings(settings, settings.tenant.engine_max_active):
        get_logger("bms_core.db").warning("tenant_pool_budget_exceeded", detail=message)
    try:
        errors = cast("ModuleRegistry", app.state.module_registry).validate()
        if errors:
            get_logger("bms").critical("service_catalog_invalid", scope="offline", errors=errors)
            raise CatalogError("服务目录校验失败（清单）：" + "；".join(errors))
        _validate_event_contracts()
        created = await ensure_development_schema(
            cast("EngineRegistry", app.state.engine_registry),
            settings,
            factory=cast("EngineFactory", app.state.engine_factory),
        )
        if created:
            get_logger(_LOGGER).info("sqlite_auto_create_done", targets=",".join(created))
        await _validate_service_catalog(app)
        await _validate_table_ownership(app)
        await assemble_plugins(app, settings, cast("ResourceManager", app.state.resources))
        await _record_db_inventory(app, settings)
    except Exception:
        # 启动失败前释放已装配资源（含引擎连接池），避免失败路径残留资源
        await cast("ResourceManager", app.state.resources).aclose()
        raise
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
    contract_version: str = "0.1.0"
    """公开契约（OpenAPI）版本（取服务包 `CONTRACT_VERSION`；启动接库校验主版本兼容）。"""

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

        app = FastAPI(title=self.service_title, version=self.contract_version, lifespan=service_lifespan)

        # 服务运行时：解析服务身份（包声明 + 配置覆盖）→ 绑定日志上下文 → 落 app.state（含停机摘流）
        attach_service(
            app,
            declared_name=self.service_name,
            version=self.version,
            title=self.service_title,
            contract_version=self.contract_version,
            settings=settings,
        )

        # 中间件先于路由注册（后注册者在外层）：只读标记 → 请求日志 → 链路 id → 边缘净化 → 租户解析（全局，最内层）；
        # 租户解析位于链路 id 之内，未知 / 停用租户的拒绝响应仍带请求 id 与链路 id；
        # 边缘净化先于租户解析，使信任模式下租户身份只采信网关注入值（见 bms_core/edge/）。
        app.add_middleware(TenantMiddleware)
        app.add_middleware(EdgeGuardMiddleware)
        app.add_middleware(TraceIdMiddleware)
        app.add_middleware(RequestLoggingMiddleware, slow_request_ms=settings.log.slow_request_ms)
        app.add_middleware(ReadOnlyMiddleware)

        register_exception_handlers(app)

        app.state.resources = ResourceManager()
        app.state.module_registry = ModuleRegistry()
        app.state.settings = settings
        app.state.startup_complete = False
        app.state.catalog_degraded = False
        app.state.ownership_degraded = False

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
        metrics = cast(
            "BaseMetrics",
            resolve_plugin("metrics", settings.metrics.provider, expected_version=BaseMetrics.contract_version),
        )
        engine_registry = EngineRegistry(
            engine_factory,
            max_active=settings.tenant.engine_max_active,
            idle_timeout=settings.tenant.engine_idle_timeout,
            lock=cross_instance_lock,
            metrics=metrics,
            metrics_service=settings.app.service,
        )
        session_factory = cast(
            "SessionFactory",
            resolve_factory("session_factory", settings.session_factory.provider),
        )
        primary_health = PrimaryHealth(engine_factory)
        register_remote_tenant_source()  # 登记 `remote` 租户源实现（配置可切 `local`）
        tenant_source = build_tenant_lookup(
            settings.tenant.source,
            settings=settings,
            registry=engine_registry,
            cache=cast(
                "CacheRegion",
                resolve_plugin("cache", settings.cache.provider, expected_version=CacheRegion.contract_version),
            ),
            session_factory=session_factory,
        )
        app.state.engine_factory = engine_factory
        app.state.engine_registry = engine_registry
        app.state.session_factory = session_factory
        app.state.primary_health = primary_health
        app.state.tenant_source = tenant_source
        app.state.metrics = metrics
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
        app.include_router(metrics_router)
        for router in self.service_routers():
            app.include_router(router)

        # 可观测接入（指标 / 链路真实实现）：最后装配——OTel ASGI 中间件位于最外层，
        # 使我方中间件进入时服务端 span 已激活（`resolve_trace_id` 取到真实 trace id）。
        setup_observability(app, settings)

        return app
