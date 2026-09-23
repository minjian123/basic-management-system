"""服务目录快照取数编排（06_01）：本地权威直读 / 跨服务经契约（06_03 遗留 2）。

- **platform 服务**（目录单一权威、`sys_module` 所有者）：直接经 `ModuleRepository` 读**本服务平台库**
  ——自己是权威数据源，非跨服务读（不做自 HTTP 调用，开发单进程亦可运行）；读失败即抛
  `CatalogError`（配置 / 迁移问题，拒启）。
- **其余服务**：经 `service_client` 调 `platform` 的 `GET /api/v1/modules/snapshot` 取全量清单；
  不可达 / 响应非法抛 `ServiceUnavailableError`，由调用方按降级口径处置（启动告警放行 +
  `/readyz` 的 `catalog` 非必需项）。
- 消费方：启动接库校验（`application.py::_validate_service_catalog`）与 `CatalogHealthCheck`。
"""

from typing import cast

from fastapi import FastAPI

from bms_core.catalog.base import CATALOG_SERVICE_KEY, fetch_catalog_snapshot
from bms_core.core.config import Settings
from bms_core.core.exceptions import CatalogError
from bms_core.core.plugin import resolve_plugin
from bms_core.db.engine import PLATFORM_DB_KEY
from bms_core.db.registry import EngineRegistry
from bms_core.db.session import SessionFactory, session_scope
from bms_core.repositories.module_repository import ModuleRepository
from bms_core.servicecall.base import BaseServiceClient
from bms_core.services.module_registry import ModuleRecord

__all__ = ["is_catalog_authority", "load_catalog_snapshot"]


def is_catalog_authority(service: str) -> bool:
    """运行服务是否为服务目录权威（提供方）。

    Args:
        service: 运行服务标识（`ServiceIdentity.name`）。

    Returns:
        bool: 目录提供方 True（取本地权威路径）。
    """
    return service == CATALOG_SERVICE_KEY


async def load_catalog_snapshot(app: FastAPI) -> list[ModuleRecord]:
    """取服务目录快照（platform 本地权威直读；其余服务经契约）。

    Args:
        app: 应用实例（取服务身份 / 配置 / 引擎注册表 / 会话工厂）。

    Returns:
        list[ModuleRecord]: 服务目录清单。

    Raises:
        CatalogError: 权威服务本地读失败（平台库不可读 / 表缺失）。
        ServiceUnavailableError: 契约不可达、非 2xx 或响应体非法。
    """
    if is_catalog_authority(cast("str", app.state.service_identity.name)):
        try:
            async with session_scope(
                cast("EngineRegistry", app.state.engine_registry),
                db_key=PLATFORM_DB_KEY,
                factory=cast("SessionFactory", app.state.session_factory),
            ) as session:
                rows = await ModuleRepository(session).list_catalog()
        except Exception as exc:
            raise CatalogError(f"服务目录不可读（请先执行平台库迁移）：{exc}") from exc
        return [ModuleRecord.from_row(row) for row in rows]
    settings = cast("Settings", app.state.settings)
    client = cast(
        "BaseServiceClient",
        resolve_plugin(
            "service_client",
            settings.service_client.provider,
            expected_version=BaseServiceClient.contract_version,
        ),
    )
    return await fetch_catalog_snapshot(client)
