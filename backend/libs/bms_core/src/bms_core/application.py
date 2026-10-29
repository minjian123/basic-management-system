"""服务应用装配基座：把每服务都需要的应用构造与生命周期收敛到共享库。

- `service_lifespan`：共享应用生命周期——启动校验（离线清单校验 + 开发库自动建表 + 接库服务目录校验）
  + 工厂 / 插件装配（完成后标记就绪），关闭时先取消就绪再统一释放异步资源；与 02_02 平台服务语义一致。
- `BaseServiceApplicationFactory`：服务应用工厂基座（继承 `BaseApplicationFactory`）——承载通用装配
  编排（服务身份 / 中间件 / 异常处理 / 状态与前缀工厂 / 引擎注册表 / 租户源 / 插件装配 / 探针），
  各服务只声明身份、业务路由与可选钩子，装配行为不改。
- **产品服务装配（12_03）**：服务目录为**应用级视图**——工厂经 `service_records()` 注入本服务补充记录
  （产品服务清单）与 `SERVICE_CATALOG` 拼接，落 `app.state.module_registry`；启动校验（离线清单 /
  接库对账 / 事件契约域）一律以该视图为准，产品服务不再隐式依赖平台固定服务集；声明 `product_key`
  的产品服务另做产品维度 fail-closed 校验（`validate_product_service_records()`）。平台服务不覆写钩子
  / 不声明 `product_key`，视图与校验口径与既有完全一致。

服务侧用法：声明 `service_name` / `service_title` / `version` / `contract_version`，覆写 `service_routers()`
返回业务路由；服务专属 state 覆写 `configure_service()`，创建前调整配置覆写 `prepare_settings()`；
产品服务另声明 `product_key` 并覆写 `service_records()` 返回本产品服务清单。

- **产品 `form_key` 清单注入**：表单标识清单同为**应用级视图**——工厂经 `form_records()` 注入本产品登记项
  （`FormRecord`），基座经 `merge_form_records()` 与 `FORM_CATALOG` 拼接后落 `app.state.form_registry`
  （无进程级注册表、不改常量）；`GET /api/v1/form-keys` 一律取该视图。平台服务不覆写钩子，视图严格等于
  `FORM_CATALOG`，行为不变。
"""

from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import cast

from fastapi import APIRouter, Depends, FastAPI
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
from bms_core.catalog.loader import is_catalog_authority, load_catalog_snapshot
from bms_core.collaboration.bootstrap import bootstrap_remote_topologies
from bms_core.collaboration.usage import (
    CapabilityUsage,
    register_capability_usages,
    validate_capability_usages,
)
from bms_core.collaboration.usage import (
    capability_usages as registered_capability_usages,
)
from bms_core.core.assembly import assemble_base_plugins, assemble_plugins, register_platform_plugins
from bms_core.core.concurrent import ConcurrentStableList, ConcurrentStableSet
from bms_core.core.config import Settings, get_settings, validate_startup
from bms_core.core.exceptions import CatalogError, EventContractError
from bms_core.core.factory import BaseApplicationFactory, register_factory, resolve_factory
from bms_core.core.id import IdGeneratorFactory
from bms_core.core.logging import configure_logging, get_logger
from bms_core.core.plugin import build_plugin_registry, resolve_plugin
from bms_core.core.resources import ResourceManager
from bms_core.core.service import ServiceIdentity, attach_service
from bms_core.core.service_endpoints import register_service_endpoints, reset_service_endpoints
from bms_core.db.bootstrap import ensure_unit_schema
from bms_core.db.engine import EngineFactory
from bms_core.db.health import PrimaryHealth
from bms_core.db.keys import PLATFORM_DB_KEY, PLATFORM_SERVICE_KEY
from bms_core.db.registry import EngineRegistry, pool_budget_warnings, tenant_pool_budget_warnings
from bms_core.db.session import SessionFactory, session_scope
from bms_core.db.tenant_remote import register_remote_tenant_source
from bms_core.db.tenant_source import build_tenant_lookup
from bms_core.events.contracts import default_event_contract_registry, validate_event_registry
from bms_core.lock.base import BaseDistributedLock
from bms_core.masking.base import get_masker
from bms_core.metrics.base import BaseMetrics
from bms_core.models.ownership import SysTableOwnership
from bms_core.registry.boot import bootstrap_declarations
from bms_core.registry.forms import FormRecord, FormRegistry, merge_form_records
from bms_core.registry.products import load_product_manifests
from bms_core.schemas.common import ApiResponse
from bms_core.servicecall.base import BaseServiceClient
from bms_core.services.module_registry import (
    ModuleRecord,
    ModuleRegistry,
    enabled_service_keys,
    injected_service_records,
    register_service_records,
    service_catalog_view,
    validate_catalog,
    validate_product_service_records,
)
from bms_core.services.table_registry import (
    TableOwnershipRegistry,
    TableRecord,
    register_table_records,
    table_ownership_view,
    validate_table_ownership,
)
from bms_core.tenant.db import register_db_tenant_self_service
from bms_core.tenant.membership import build_tenant_membership_store
from bms_core.tenant.membership_remote import register_remote_tenant_membership_store
from bms_core.tracing.setup import setup_observability

__all__ = ["BaseServiceApplicationFactory", "service_lifespan"]

_LOGGER = "bms_core.application"


async def _validate_service_catalog(app: FastAPI) -> None:
    """接库服务目录校验：取目录快照校验并拒启（空目录仅告警放行；06_01 起改经契约）。

    取数路径（见 `bms_core/catalog/loader.py`）：

    - `platform`（目录单一权威）：本地读**本服务平台库** `sys_module`，读失败即拒启（`CatalogError`）；
    - 其余服务：经 `service_client` 调 `GET /api/v1/modules/snapshot`；**不可达 / 响应非法时告警放行**
      并置 `app.state.catalog_degraded = True`（`/readyz` 的 `catalog` 非必需项可见降级，不产生 503）。

    对账清单取**应用级视图**（`app.state.module_registry.catalog_records()`；平台服务等于
    `SERVICE_CATALOG`，产品服务为「平台清单 + `service_records()` 注入记录」）——产品行随注入进入
    对账，产品服务不因平台固定清单产生隐式依赖（12_03）。

    Args:
        app: 应用实例（取引擎注册表 / 会话工厂 / 服务身份 / 服务目录视图）。

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
    # 常量维度对账的取数面：**平台行 + 本产品行**（其余产品行归各自进程 / 注册通道）
    product_key = cast("str | None", app.state.service_product_key)
    catalog = _scope_catalog(cast("ModuleRegistry", app.state.module_registry).catalog_records(), product_key)
    records = _scope_catalog(records, product_key)
    own_keys: ConcurrentStableSet[str] | None = None
    if not is_catalog_authority(identity.name):
        # 产品进程：对账基准只含「平台自身行 + 本产品行」。常量里其他产品的行归各自进程注册，
        # 计入会让每个产品进程启动即报「库中缺登记行」（07B `04_02` 重开补正）。
        own_keys = ConcurrentStableSet(record.module_key for record in injected_service_records())
    errors = validate_catalog(
        catalog,
        records,
        service_key=identity.name,
        contract_version=identity.contract_version,
        own_keys=own_keys,
    )
    if errors:
        logger.critical("service_catalog_invalid", scope="database", errors=errors)
        raise CatalogError("服务目录校验失败：" + "；".join(errors))


def _scope_catalog(
    records: ConcurrentStableList[ModuleRecord], product_key: str | None
) -> ConcurrentStableList[ModuleRecord]:
    """取常量维度对账的取数面：平台自身行 + 本产品行（其余产品行不在本进程责任内）。

    口径（07B `04_02` 重开补正）：平台常量只承载**平台自身行**，产品行经注册通道按**声明方作用域**
    对账（`02_06`）。不划这一刀的话，任一产品注册后**平台重启**即报「库中登记行不在清单：<产品>」，
    产品进程也会因别的产品的行不在本进程视图里而误报——两者都属「拿别人的责任范围判自己」。

    Args:
        records: 目录行（库快照或应用级视图）。
        product_key: 本进程产品标识（平台进程为 None，只保留平台行）。

    Returns:
        ConcurrentStableList[ModuleRecord]: 取数面内的行（插入序）。
    """
    return ConcurrentStableList(
        record for record in records if not record.product_key or record.product_key == product_key
    )


async def _validate_capability_usages(app: FastAPI) -> None:
    """能力使用登记校验（07B `02_02`）：消费方声明的能力必须已登记，降级声明须合规，否则拒启。

    三档失败语义中的**第一档**（装载 / 启动）：`02_01` 六类校验管「提供方声明是否自洽」，
    本步管「消费方声明是否可兑现」——声明了未登记能力（拼错 / 未装载）、无理由降级、`stale`
    无投影来源、写 / 强一致能力声明降级，一律 `CatalogError` 拒启并定位到能力名。

    Args:
        app: 应用实例（取配置中的服务标识与装配期登记的声明视图）。

    Raises:
        CatalogError: 使用声明不满足（信息含消费方与能力名）。
    """
    settings = cast("Settings", app.state.settings)
    service = settings.app.service
    usages = registered_capability_usages(service)
    if not usages:
        return
    try:
        validate_capability_usages(service, usages)
    except CatalogError as exc:
        get_logger("bms").critical("capability_usage_invalid", scope="startup", consumer=service, detail=str(exc))
        raise


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
    errors = validate_table_ownership(table_ownership_view(), ConcurrentStableList(records))
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


def _injected_service_records(app: FastAPI) -> ConcurrentStableList[ModuleRecord]:
    """取本服务注入的服务目录记录（应用工厂 `service_records()` 产物；未注入返回空清单）。

    Args:
        app: 应用实例。

    Returns:
        ConcurrentStableList[ModuleRecord]: 注入记录（插入序）。
    """
    return cast("ConcurrentStableList[ModuleRecord]", app.state.service_injected_records)


def _validate_event_contracts(app: FastAPI) -> None:
    """离线事件契约校验：登记契约与订阅（命名 / 事件域 / 版本 / 字段）违规即拒启。

    事件域取**应用级视图**（`app.state.module_registry.event_domains()`）——产品服务注入记录的
    自有事件域随之生效，不再受平台固定清单限制（12_03）。

    Args:
        app: 应用实例（取服务目录视图）。

    Raises:
        EventContractError: 契约或订阅校验失败（含事件域未登记、订阅未覆盖当前主版本）。
    """
    errors = validate_event_registry(
        default_event_contract_registry(),
        domains=cast("ModuleRegistry", app.state.module_registry).event_domains(),
    )
    if errors:
        get_logger("bms").critical("event_contract_invalid", errors=errors)
        raise EventContractError("事件契约校验失败：" + "；".join(errors))


@asynccontextmanager
async def service_lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """服务生命周期：启动校验（离线 + 接库）+ 工厂 / 插件装配（完成后标记就绪），关闭时统一释放异步资源。

    启动顺序：离线清单校验 → **基础能力先行装配**（Redis 统一客户端先登记——开库引导与接库校验
    都要取数据库引擎，而引擎注册表的跨实例创建锁经分布式锁基座取共享客户端）→ 开发库自动建表 →
    接库服务目录校验 → 表归属对账 → 其余能力装配 → 库数量上报 → 就绪标记。

    离线阶段另执行**产品维度校验**（应用工厂声明 `product_key` 时）：注入的服务目录记录须非空、
    均为产品分组、产品归属与声明一致、且含运行服务登记行（不通过即拒启；12_03）。

    Args:
        app: 应用实例。

    Yields:
        None: 应用运行期。

    Raises:
        CatalogError: 服务目录校验失败（离线清单冲突 / 产品维度不合规 / 接库冲突 / 库不可读）。
        EventContractError: 事件契约或订阅校验失败。
        PluginError: 工厂 / 插件装配失败（非法 provider / 重名 / 契约版本不符 / 依赖不可用）。
    """
    settings = get_settings()
    validate_startup(settings)
    # 服务端点覆盖（本机裸跑寻址补充）：装配前登记，服务间调用与能力寻址同口径取用
    # （容器部署 endpoints 为空表，行为与未引入覆盖时一致）；收尾复位，避免同进程多次装配互相污染。
    register_service_endpoints(settings.service_client.endpoints)
    for message in pool_budget_warnings(settings):
        get_logger("bms_core.db").warning("pool_budget_exceeded", detail=message)
    for message in tenant_pool_budget_warnings(settings, settings.tenant.engine_max_active):
        get_logger("bms_core.db").warning("tenant_pool_budget_exceeded", detail=message)
    try:
        registry = cast("ModuleRegistry", app.state.module_registry)
        identity = cast("ServiceIdentity", app.state.service_identity)
        errors = registry.validate()
        product_key = cast("str | None", app.state.service_product_key)
        if product_key is not None:
            errors.update(
                validate_product_service_records(
                    _injected_service_records(app), service_key=identity.name, product_key=product_key
                )
            )
        if errors:
            get_logger("bms").critical("service_catalog_invalid", scope="offline", errors=errors)
            raise CatalogError("服务目录校验失败（清单）：" + "；".join(errors))
        _validate_event_contracts(app)
        # 基础能力先行（03_04）：开库引导与接库校验都会取数据库引擎，而引擎注册表的跨实例创建锁
        # 经分布式锁基座取共享 Redis 客户端；该客户端由插件装配期登记，故此处先装配基础能力。
        await assemble_base_plugins(app, settings, cast("ResourceManager", app.state.resources))
        created = await ensure_unit_schema(
            settings,
            factory=cast("EngineFactory", app.state.engine_factory),
        )
        if created:
            get_logger(_LOGGER).info("schema_auto_create_done", targets=",".join(created))
        # 注册表启动装配（07B `02_06`）：产品进程上报自身声明并拉取权威快照投影；
        # 平台进程跳过（本库即权威，由平台自身启动钩子注册）。
        # **顺序**：必须先于接库服务目录校验——平台自注册写入 `sys_module` 是目录校验的基准，
        # 放到 `startup_hooks`（更晚）会让重启后的校验对着空库跑，误报「库中缺登记行」全表。
        await bootstrap_declarations(app)
        # 部署拓扑分发（07C `02_02`）：非平台进程经内部出口拉取全量快照并登记第二段解析与
        # 本实例承载集合；平台进程内部跳过（本库即权威，由启动钩子装载）。
        # **顺序**：必须在声明装载之后——承载集合校验与单元判定依赖域登记视图与承载服务映射。
        await bootstrap_remote_topologies(app)
        await _validate_service_catalog(app)
        await _validate_capability_usages(app)
        await _validate_table_ownership(app)
        await assemble_plugins(app, settings, cast("ResourceManager", app.state.resources))
        await _record_db_inventory(app, settings)
        for hook in cast("tuple[StartupHook, ...]", getattr(app.state, "startup_hooks", ())):
            await hook(app)
    except Exception:
        # 启动失败前释放已装配资源（含引擎连接池），避免失败路径残留资源
        await cast("ResourceManager", app.state.resources).aclose()
        reset_service_endpoints()
        raise
    app.state.startup_complete = True
    try:
        yield
    finally:
        app.state.startup_complete = False
        await cast("ResourceManager", app.state.resources).aclose()
        reset_service_endpoints()


StartupHook = Callable[[FastAPI], Awaitable[None]]
"""启动钩子（生命周期内、装配完成后执行；用于幂等引导类任务）。"""


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
    product_key: str | None = None
    """产品标识（**产品服务**声明；平台服务保持 `None`）。

    声明后进入产品维度 fail-closed 校验（`service_records()` 注入记录非空 / 均为产品分组 / 产品归属
    与本值一致 / 含本服务登记行），应用级清单视图为「平台清单 + 注入记录」（12_03）。
    """

    def service_records(self) -> ConcurrentStableList[ModuleRecord]:
        """本服务补充的服务目录记录（子类覆写；缺省空元组）。

        **产品服务**在此返回本产品服务清单（与 `bms_core` 同口径 `ModuleRecord`；跨仓库直接
        `import` 自身清单返回）：基座把它与 `SERVICE_CATALOG` 拼接为应用级视图
        （`app.state.module_registry`），启动离线校验 / 接库对账 / 事件契约域一律以该视图为准。
        平台服务不覆写——视图严格等于 `SERVICE_CATALOG`，装配与校验行为不变。

        Returns:
            tuple[ModuleRecord, ...]: 补充的服务目录记录（插入序）。
        """
        return ConcurrentStableList(())

    def table_records(self) -> ConcurrentStableList[TableRecord]:
        """本服务补充的表归属记录（子类覆写；缺省空元组）。

        **产品服务**在此返回本产品表归属清单（`bms_core.services.table_registry.TableRecord`；跨仓库
        直接 `import` 自身清单返回）：基座在装配期**登记**这些记录并把「平台清单 + 注入记录」的
        **合并视图**置为 `app.state.table_ownership`，派生（`chain_tables` / 自动建表）与归属校验
        一律以该视图为准；合并按「同 `table_name` 同值去重、异值即拒」（12_04）。
        平台服务不覆写——合并视图严格等于 `TABLE_OWNERSHIP`，装配与校验行为不变。

        Returns:
            tuple[TableRecord, ...]: 补充的表归属记录（插入序）。
        """
        return ConcurrentStableList(())

    def form_records(self) -> ConcurrentStableList[FormRecord]:
        """本服务补充的 `form_key` 登记记录（子类覆写；缺省空清单）。

        **产品服务**在此返回本产品表单标识清单（`bms_core.registry.forms.FormRecord`；跨仓库直接
        `import` 自身清单返回）：基座在装配期把它与 `FORM_CATALOG` 经 `merge_form_records()` 拼接为
        **应用级视图**并置为 `app.state.form_registry`（`GET /api/v1/form-keys` 取该视图）。
        产品侧清单为**唯一出处**（如某产品的 `services/form_registry.py`），基座不改常量、无进程级注册表。
        平台服务不覆写——视图严格等于 `FORM_CATALOG`，装配与校验行为不变。

        Returns:
            ConcurrentStableList[FormRecord]: 补充的表单标识登记记录（插入序）。
        """
        return ConcurrentStableList(())

    def capability_usages(self) -> ConcurrentStableList[CapabilityUsage]:
        """本服务（作为消费方）的跨产品能力使用声明（子类覆写；缺省空清单）。

        声明含**降级策略**（`CapabilityUsage.degrade` / `reason`）：降级是消费方策略，提供方无权替
        消费者决定能否接受空集。基座在装配期登记该清单，并在启动校验步骤 fail-closed——声明了未登记
        能力（拼错 / 未装载）、无理由降级、`stale`（无投影来源）、写 / 强一致能力声明降级，一律拒启。

        未覆写 = 该服务不声明任何能力使用，行为与改造前一致（无进程级注册表、无空登记）。

        Returns:
            ConcurrentStableList[CapabilityUsage]: 能力使用声明（插入序）。
        """
        return ConcurrentStableList(())

    def service_routers(self) -> ConcurrentStableList[APIRouter]:
        """业务路由清单（子类覆写；探针路由由基座统一挂载，无需返回）。

        Returns:
            ConcurrentStableList[APIRouter]: 业务路由（挂 `/api/v1` 前缀）。
        """
        return ConcurrentStableList()

    def startup_hooks(self) -> ConcurrentStableList[StartupHook]:
        """启动钩子清单（子类覆写；缺省空元组）。

        钩子在生命周期装配完成后、`startup_complete` 标记前逐个执行；失败按启动失败处理（释放资源并拒启）。
        用于幂等引导类任务（如租户服务引导默认平台租户）。

        Returns:
            tuple[StartupHook, ...]: 启动钩子（执行序）。
        """
        return ConcurrentStableList(())

    def prepare_settings(self, settings: Settings) -> None:
        """创建前配置调整钩子（默认空实现；如最小服务置空健康 provider）。

        Args:
            settings: 应用配置（可变）。
        """

    def configure_plugins(self, app: FastAPI, settings: Settings) -> None:
        """服务侧**插件登记**钩子（默认空实现；须在建注册表之前）。

        调用点＝`register_platform_plugins` 之后、`build_plugin_registry()` 之前：服务的**依赖应用
        状态**的插件实现（如 `txn` 恢复器：取 `engine_registry` / `branch_driver` / 分布式锁 / 指标）
        只可在此登记——`prepare_settings()` 早于应用构造、`configure_service()` 晚于注册表冻结
        （`PluginError: 运行期只读`）。缺省实现下行为与改前一致。

        Args:
            app: 应用实例（取应用级状态）。
            settings: 应用配置（可变；可在此置能力分区缺省 provider）。
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

        # 全局标注依赖 `get_masker`：请求期把掩码器写入 `current_masker`（`BaseSchema` 序列化期取用），
        # 请求结束复位；一处生效即覆盖全部服务全部路由，无需逐路由挂载（org 路由重复挂载由依赖缓存去重）。
        # 文档端点按 `[app].docs_enabled`（基线开、生产关）注册：关闭时三端点 404，契约走 CI 快照。
        docs_enabled = settings.app.docs_enabled
        app = FastAPI(
            title=self.service_title,
            version=self.contract_version,
            lifespan=service_lifespan,
            dependencies=[Depends(get_masker)],
            docs_url="/docs" if docs_enabled else None,
            redoc_url="/redoc" if docs_enabled else None,
            openapi_url="/openapi.json" if docs_enabled else None,
        )

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
        # 服务目录为**应用级视图**：平台清单 + 本服务注入记录（产品服务经 `service_records()` 提供）；
        # 合并按「同 module_key 同值去重、异值即拒」（平台侧已登记 + 产品侧自报同值时并存不冲突；12_03 扩展）
        # 产品登记清单（产品仓自持）：服务行 / 产品路由 / 数据源条目在装配期装载进合并视图；
        # 07B `04_02`：只装载**本仓** `deploy/registry/*.toml`（`product_manifests` 配置键已退役）——
        # 跨仓声明由注册通道（`02_06`）在下游启动钩子里上报 / 拉取，装配期不再挂别家清单路径。
        loads = load_product_manifests(ConcurrentStableList())
        if loads:
            get_logger("bms").info("product_manifests_loaded", count=len(loads))
        # 能力使用登记（07B `02_02`）：消费方声明须在装配期登记，生命周期内由校验步骤 fail-closed；
        # 空声明不登记（未声明降级的服务与既有一致，不产生进程级状态）
        declared_usages = ConcurrentStableList(self.capability_usages())
        if declared_usages:
            register_capability_usages(settings.app.service, declared_usages)
        app.state.capability_usages = declared_usages
        injected = ConcurrentStableList(self.service_records())
        register_service_records(injected)
        app.state.module_registry = ModuleRegistry(service_catalog_view())
        app.state.service_product_key = self.product_key
        app.state.service_injected_records = injected
        # 表归属为**合并视图**：平台清单 + 本服务注入记录（产品服务经 `table_records()` 提供）；
        # 装配期登记（`register_table_records`）后，开发库自动建表与迁移等**装载期派生**即可见产品表；
        # 合并按「同 table_name 同值去重、异值即拒」（12_04）
        injected_tables = ConcurrentStableList(self.table_records())
        register_table_records(injected_tables)
        app.state.table_ownership = TableOwnershipRegistry(table_ownership_view())
        app.state.table_injected_records = injected_tables
        # `form_key` 清单为**应用级视图**：平台构建期清单 + 本服务注入记录（产品服务经 `form_records()` 提供）；
        # 无进程级注册表、不改 `FORM_CATALOG` 常量，`GET /api/v1/form-keys` 一律取该视图
        injected_forms = ConcurrentStableList(self.form_records())
        app.state.form_registry = FormRegistry(merge_form_records(injected=injected_forms))
        app.state.form_injected_records = injected_forms
        app.state.settings = settings
        app.state.startup_complete = False
        app.state.catalog_degraded = False
        app.state.ownership_degraded = False

        # 工厂 / 插件装配前置：平台实现登记 → 服务侧插件登记 → 注册表构建 → 关键工厂解析（可替换，配置选择）
        register_platform_plugins(settings, app, app.state.resources)
        self.configure_plugins(app, settings)
        register_db_tenant_self_service(app)  # 登记 / 按应用刷新租户自助真实实现工厂（11_01）
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
        register_remote_tenant_membership_store()  # 登记 `remote` 关系数据源实现（配置可切 `local`）
        # 服务间调用客户端在装配期解析**一次**并登记到 `app.state`：启动期引导（声明上报 / 授权视图
        # 预热）取不到 FastAPI 请求作用域，只能从这里取（与 `get_service_client` 同源同实例）。
        service_client = cast(
            "BaseServiceClient",
            resolve_plugin(
                "service_client",
                settings.service_client.provider,
                expected_version=BaseServiceClient.contract_version,
            ),
        )
        tenant_membership = build_tenant_membership_store(
            settings.tenant_membership.source,
            settings=settings,
            registry=engine_registry,
            session_factory=session_factory,
            service_client=service_client,
        )
        app.state.engine_factory = engine_factory
        app.state.engine_registry = engine_registry
        app.state.session_factory = session_factory
        app.state.primary_health = primary_health
        app.state.tenant_source = tenant_source
        app.state.tenant_membership = tenant_membership
        app.state.service_client = service_client
        app.state.metrics = metrics
        app.state.resources.register(engine_registry)
        app.state.resources.register(primary_health)

        self.configure_service(app, settings)
        app.state.startup_hooks = self.startup_hooks()

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
