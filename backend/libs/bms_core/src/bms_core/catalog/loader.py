"""服务目录快照取数编排（06_01；06_02 改为权威读取器**注册点**模式）。

- **platform 服务**（目录单一权威、`sys_module` 所有者）：经**注册的本地读取器**读**本服务平台服务库**
  ——自己是权威数据源，非跨服务读（不做自 HTTP 调用，开发单进程亦可运行）；读失败即抛
  `CatalogError`（配置 / 迁移问题，拒启）。
  模型与仓储迁至平台服务工程（06_02）后，共享基座库不再静态依赖服务包：读取器由平台服务在装配期
  经 `register_catalog_reader` 登记（与租户源装配点同模式）。
- **其余服务**：经 `service_client` 调 `platform` 的 `GET /api/v1/modules/snapshot` 取全量清单；
  不可达 / 响应非法抛 `ServiceUnavailableError`，由调用方按降级口径处置（启动告警放行 +
  `/readyz` 的 `catalog` 非必需项）。
- 消费方：启动接库校验（`application.py::_validate_service_catalog`）与 `CatalogHealthCheck`。
"""

from collections.abc import Awaitable, Callable
from typing import cast

from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession

from bms_core.catalog.base import CATALOG_SERVICE_KEY, fetch_catalog_snapshot
from bms_core.core.config import Settings
from bms_core.core.exceptions import CatalogError
from bms_core.core.plugin import resolve_plugin
from bms_core.db.engine import PLATFORM_DB_KEY
from bms_core.db.registry import EngineRegistry
from bms_core.db.session import SessionFactory, session_scope
from bms_core.servicecall.base import BaseServiceClient
from bms_core.services.module_registry import ModuleRecord

__all__ = [
    "CatalogReader",
    "is_catalog_authority",
    "load_catalog_snapshot",
    "register_catalog_reader",
    "resolve_catalog_reader",
]

CatalogReader = Callable[[AsyncSession], Awaitable[list[ModuleRecord]]]
"""目录权威本地读取器（入参为**本服务平台服务库**的会话，返回服务目录清单）。"""

_CATALOG_READERS: dict[str, CatalogReader] = {}
"""目录权威本地读取器注册表（`{服务标识: 读取器}`；由服务包在装配期登记）。"""


def register_catalog_reader(service: str, reader: CatalogReader) -> None:
    """登记目录权威本地读取器（幂等：同名后登记者为准）。

    Args:
        service: 服务标识（目录权威，如 `platform`）。
        reader: 读取器（读本服务平台服务库 `sys_module`）。
    """
    _CATALOG_READERS[service] = reader


def resolve_catalog_reader(service: str) -> CatalogReader | None:
    """取目录权威本地读取器（未登记返回 None）。

    Args:
        service: 服务标识。

    Returns:
        CatalogReader | None: 读取器；未登记返回 None。
    """
    return _CATALOG_READERS.get(service)


def is_catalog_authority(service: str) -> bool:
    """运行服务是否为服务目录权威（提供方）。

    Args:
        service: 运行服务标识（`ServiceIdentity.name`）。

    Returns:
        bool: 目录提供方 True（取本地权威路径）。
    """
    return service == CATALOG_SERVICE_KEY


async def load_catalog_snapshot(app: FastAPI) -> list[ModuleRecord]:
    """取服务目录快照（platform 本地权威读；其余服务经契约）。

    Args:
        app: 应用实例（取服务身份 / 配置 / 引擎注册表 / 会话工厂）。

    Returns:
        list[ModuleRecord]: 服务目录清单。

    Raises:
        CatalogError: 权威服务读取器未登记或本地读失败（平台库不可读 / 表缺失）。
        ServiceUnavailableError: 契约不可达、非 2xx 或响应体非法。
    """
    service = cast("str", app.state.service_identity.name)
    if is_catalog_authority(service):
        reader = resolve_catalog_reader(service)
        if reader is None:
            raise CatalogError(
                f"服务目录权威（{service}）的本地读取器未登记：请由该服务包在装配期调用 "
                "bms_core.catalog.loader.register_catalog_reader 登记"
            )
        try:
            async with session_scope(
                cast("EngineRegistry", app.state.engine_registry),
                db_key=PLATFORM_DB_KEY,
                factory=cast("SessionFactory", app.state.session_factory),
            ) as session:
                return await reader(cast("AsyncSession", session))
        except CatalogError:
            raise
        except Exception as exc:
            raise CatalogError(f"服务目录不可读（请先执行本服务平台服务库迁移）：{exc}") from exc
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
