"""租户拓扑的启动装配（07C `02_01`）：自举默认拓扑 + 校验覆盖 + 装载快照 + 登记解析器。

- **何时执行**：platform 服务启动钩子——晚于「建表」、早于对外服务；
- **自举**：`tenant_id=0` 无记录时按「已登记域 → 该域承载服务键」写入版本 1（与 07B 过渡实现行为等价、
  库名零变化）；已有记录则跳过（幂等）；
- **拒启**：业务域登记为空、或默认拓扑未覆盖全部已登记域时 `CatalogError` / `ParamError` 上抛——
  拓扑是能力的第二段解析依据，缺它不该带病启动（需求 `02-2`「拓扑缺失即拒启」）；
- **登记**：装载全部租户快照后 `register_topology_resolver(TenantTopologyResolver())` 替换 07B 过渡实现
  （协议与消费方代码不变）。
"""

from typing import cast

from fastapi import FastAPI

from bms_core.audit.base import AuditCapturer
from bms_core.collaboration.topology import (
    TenantTopologyResolver,
    register_topology_resolver,
    register_topology_snapshot,
    reset_topology_resolver,
    reset_topology_snapshots,
)
from bms_core.core.capability import BaseAsyncResource
from bms_core.core.config import Settings
from bms_core.core.exceptions import CatalogError
from bms_core.core.logging import get_logger
from bms_core.core.plugin import resolve_plugin
from bms_core.db.keys import PLATFORM_DB_KEY
from bms_core.db.session import session_scope
from bms_core.db.unit_of_work import DbUnitOfWork
from bms_platform.domains.platform_registry.services.tenant_topology import TenantTopologyService

__all__ = ["TopologyResolverResource", "bootstrap_tenant_topologies"]

_LOGGER = get_logger("bms.platform.tenant_topology")


class TopologyResolverResource(BaseAsyncResource):
    """进程级拓扑状态的释放器：随应用关闭复位解析器与快照。

    拓扑快照与第二段解析实现是**进程级全局状态**，在启动钩子里登记；应用关闭（进程退出 /
    测试用应用拆卸）时复位，避免同一进程内下一次装配读到上一次的快照。
    """

    async def aclose(self) -> None:
        """复位第二段解析实现与全部快照（幂等）。"""
        reset_topology_resolver()
        reset_topology_snapshots()


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
    except CatalogError:
        raise
    except Exception as exc:
        raise CatalogError(f"租户部署拓扑装配失败：{type(exc).__name__}: {exc}") from exc
    for snapshot in snapshots:
        register_topology_snapshot(snapshot)
    register_topology_resolver(TenantTopologyResolver())
    app.state.resources.register(TopologyResolverResource())
    _LOGGER.info("tenant_topology_ready", default_version=version, tenants=len(snapshots))
