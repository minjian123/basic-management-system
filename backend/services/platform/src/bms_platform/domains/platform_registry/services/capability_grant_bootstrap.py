"""能力分配授权的启动装配（07B `02_04`）：声明同步落库 + 登记授权视图来源 + 预热快照。

- **何时执行**：platform 服务启动钩子（`startup_hooks`）——晚于「产品清单装载」与「建表」、
  早于对外服务；失败**拒绝启动**（`CatalogError`，断链不留到运行期）；
- **声明同步**：把产品清单的 `default_consumers` 按「声明是基线、人工是覆盖」的纯函数差异落库；
- **授权视图来源**：登记「本库直读」实现（平台库是授权唯一权威），供入站判定与出站 scope 读取；
- **预热**：本服务承载的业务域 `provider` 视图 + 自身 `consumer` 视图各拉一次，使首访不依赖惰性加载
  （实现收归基座 `bms_core.collaboration.bootstrap`，产品进程共用同一份预热口径）。

产品服务（跨进程提供方）的来源登记与预热调 `bootstrap_remote_capability_grants()`（`03_01`）。
"""

from typing import cast

from fastapi import FastAPI
from sqlalchemy.exc import SQLAlchemyError

from bms_core.audit.base import AuditCapturer
from bms_core.collaboration.bootstrap import warm_capability_grant_views
from bms_core.collaboration.grant import (
    CapabilityGrant,
    register_capability_grant_source,
)
from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.config import Settings
from bms_core.core.exceptions import CatalogError
from bms_core.core.logging import get_logger
from bms_core.core.objects import BaseFrameworkObject
from bms_core.core.plugin import resolve_plugin
from bms_core.db.keys import PLATFORM_DB_KEY
from bms_core.db.session import session_scope
from bms_core.db.unit_of_work import DbUnitOfWork
from bms_platform.domains.platform_registry.services.capability_grant import CapabilityGrantService

__all__ = ["PlatformCapabilityGrantSource", "bootstrap_capability_grants", "warm_capability_grant_views"]

_LOGGER = get_logger("bms.platform.capability_grant")


class PlatformCapabilityGrantSource(BaseFrameworkObject):
    """授权视图来源：platform 直读平台库 `sys_capability_grant`（授权唯一权威在平台库）。

    实现 `CapabilityGrantSource` 协议（结构化契约，不继承——同 `DomainLayoutTopologyResolver`）。
    """

    def __init__(self, app: FastAPI) -> None:
        """初始化。

        Args:
            app: 应用实例（取引擎注册表与会话工厂）。
        """
        self._app = app

    async def load(
        self, *, provider: str | None = None, consumer: str | None = None
    ) -> ConcurrentStableList[CapabilityGrant]:
        """按维度读取启用中的授权记录。

        Args:
            provider: 提供方业务域（入站维度）。
            consumer: 消费方服务键（出站维度）。

        Returns:
            ConcurrentStableList[CapabilityGrant]: 授权记录（含已过期行，有效性由调用方判定）。
        """
        async with session_scope(
            self._app.state.engine_registry,
            db_key=PLATFORM_DB_KEY,
            factory=self._app.state.session_factory,
        ) as session:
            return await CapabilityGrantService(session).view(provider=provider, consumer=consumer)


async def bootstrap_capability_grants(app: FastAPI) -> None:
    """启动钩子：同步声明默认授权、登记视图来源并预热快照。

    Args:
        app: 应用实例（取配置 / 审计插件 / 引擎注册表 / 会话工厂 / 指标器）。

    Raises:
        CatalogError: 声明同步或视图预热失败（拒启；不静默跳过）。
    """
    settings: Settings = app.state.settings
    audit = cast(
        "AuditCapturer",
        resolve_plugin("audit", settings.audit.provider, expected_version=AuditCapturer.contract_version),
    )
    metrics = getattr(app.state, "metrics", None)
    try:
        async with session_scope(
            app.state.engine_registry,
            db_key=PLATFORM_DB_KEY,
            factory=app.state.session_factory,
        ) as session:
            service = CapabilityGrantService(
                session,
                audit=audit,
                metrics=metrics,
                uow=DbUnitOfWork(session),
            )
            report = await service.sync_declared()
    except SQLAlchemyError as exc:
        # 库不可读 / 未建表：与「表归属接库校验」同口径降级放行（记 WARNING + 打降级标记），
        # 不因「还没初始化库」把整个服务拒之门外；入站判定仍 fail-closed（未装配来源即未授权）。
        _LOGGER.warning("capability_grant_sync_unavailable", error=type(exc).__name__, detail=str(exc))
        app.state.grant_sync_degraded = True
        return
    except CatalogError:
        raise
    except Exception as exc:
        raise CatalogError(f"能力分配声明同步失败：{type(exc).__name__}: {exc}") from exc
    if report.changed:
        _LOGGER.info(
            "capability_grant_synced",
            created=report.created,
            restored=report.restored,
            revoked=report.revoked,
        )
    for message in report.warnings:
        _LOGGER.warning("capability_grant_declaration_conflict", detail=message)
    register_capability_grant_source(PlatformCapabilityGrantSource(app))
    try:
        await warm_capability_grant_views(settings.app.service)
    except Exception as exc:
        raise CatalogError(f"授权视图预热失败：{type(exc).__name__}: {exc}") from exc
