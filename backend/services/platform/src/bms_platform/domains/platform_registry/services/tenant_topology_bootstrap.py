"""租户拓扑的启动装配（07C `02_01`）：自举默认拓扑 + 校验覆盖 + 装载快照 + 登记解析器。

- **何时执行**：platform 服务启动钩子——晚于「建表」、早于对外服务；
- **自举**：`tenant_id=0` 无记录时按「已登记域 → 该域承载服务键」写入版本 1（与 07B 过渡实现行为等价、
  库名零变化）；已有记录则跳过（幂等）；
- **拒启**：业务域登记为空、或默认拓扑未覆盖全部已登记域时 `CatalogError` / `ParamError` 上抛——
  拓扑是能力的第二段解析依据，缺它不该带病启动（需求 `02-2`「拓扑缺失即拒启」）；
- **登记**：装载全部租户快照后 `register_topology_resolver(TenantTopologyResolver())` 替换 07B 过渡实现
  （协议与消费方代码不变）；
- **库不可读 / 未建表的降级**（与 07B 能力分配同口径）：拓扑表还没就绪（如开发库未初始化）时记 `WARNING`
  并打降级标记、**保留过渡实现**——区分「环境未就绪」与「拓扑未配置」：后者（表可读但缺域）仍拒启。
"""

from typing import cast

from fastapi import FastAPI
from sqlalchemy.exc import SQLAlchemyError

from bms_core.audit.base import AuditCapturer
from bms_core.collaboration.topology import (
    TenantTopologyResolver,
    TopologyResolverResource,
    register_instance_context,
    register_topology_resolver,
    register_topology_snapshot,
)
from bms_core.core.config import Settings
from bms_core.core.exceptions import CatalogError
from bms_core.core.logging import get_logger
from bms_core.core.plugin import resolve_plugin
from bms_core.db.keys import PLATFORM_DB_KEY
from bms_core.db.session import session_scope
from bms_core.db.unit_of_work import DbUnitOfWork
from bms_platform.domains.platform_registry.services.tenant_topology import TenantTopologyService

__all__ = ["bootstrap_tenant_topologies"]

_LOGGER = get_logger("bms.platform.tenant_topology")


async def bootstrap_tenant_topologies(app: FastAPI) -> None:
    """启动钩子：自举默认拓扑、装载快照并登记第二段解析实现。

    Args:
        app: 应用实例（取配置 / 审计插件 / 引擎注册表 / 会话工厂）。

    Raises:
        CatalogError: 业务域登记为空或快照装载失败（拒启；不静默跳过）。
        ParamError: 默认拓扑未覆盖全部已登记业务域（拒启）。
    """
    settings: Settings = app.state.settings
    audit = cast(
        "AuditCapturer",
        resolve_plugin("audit", settings.audit.provider, expected_version=AuditCapturer.contract_version),
    )
    try:
        async with session_scope(
            app.state.engine_registry,
            db_key=PLATFORM_DB_KEY,
            factory=app.state.session_factory,
        ) as session:
            service = TenantTopologyService(session, audit=audit)
            version = await service.ensure_default()
            await DbUnitOfWork(session).commit()
            snapshots = await service.snapshot()
    except SQLAlchemyError as exc:
        # 库不可读 / 未建表：与能力分配同步同口径降级放行（记 WARNING + 打降级标记），保留 07B 过渡实现；
        # 「表可读但缺域」不在此列——那种属装配错误，仍按下方 CatalogError 拒启。
        _LOGGER.warning("tenant_topology_unavailable", error=type(exc).__name__, detail=str(exc))
        app.state.topology_degraded = True
        return
    except CatalogError:
        raise
    except Exception as exc:
        raise CatalogError(f"租户部署拓扑装配失败：{type(exc).__name__}: {exc}") from exc
    for snapshot in snapshots:
        register_topology_snapshot(snapshot)
    register_topology_resolver(TenantTopologyResolver())
    register_instance_context(settings.app.service, settings.topology.units)
    app.state.resources.register(TopologyResolverResource())
    _LOGGER.info("tenant_topology_ready", default_version=version, tenants=len(snapshots))
