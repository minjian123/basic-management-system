"""帮助内容路由公共依赖：四个服务构造（读者 / 维护 / 统计 / 包管理）。

**为什么在装配面构造**：帮助域只依赖基座与本域实现；服务间协作（平台库锚点清单、缓存、发件箱）
一律由装配面注入，域内不 import 其他域实现。
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from bms_core.api.deps import get_cache_region, get_outbox_store, get_platform_uow, get_uow
from bms_core.cache.base import CacheRegion
from bms_core.core.config import Settings, get_settings
from bms_core.db.unit_of_work import UnitOfWork
from bms_core.i18n.base import get_default_locale
from bms_core.outbox.base import BaseOutboxStore
from bms_platform.api.locale import accept_locale
from bms_platform.domains.help.services.maintenance import HelpMaintenanceService
from bms_platform.domains.help.services.package_admin import HelpPackageAdminService
from bms_platform.domains.help.services.reader import HelpReaderService
from bms_platform.domains.help.services.statistics import HelpStatisticsService
from bms_platform.wiring import (
    build_help_maintenance_service,
    build_help_package_admin_service,
    build_help_reader_service,
    build_help_statistics_service,
)

__all__ = [
    "MaintenanceServiceDep",
    "PackageAdminServiceDep",
    "ReaderServiceDep",
    "SettingsDep",
    "StatisticsServiceDep",
    "maintenance_service",
    "package_admin_service",
    "reader_service",
    "statistics_service",
]


def reader_service(
    request: Request,
    tenant_uow: Annotated[UnitOfWork, Depends(get_uow)],
    cache: Annotated[CacheRegion, Depends(get_cache_region)],
) -> HelpReaderService:
    """构造请求级读者面服务。

    Args:
        request: 请求对象（解析请求语言）。
        tenant_uow: 租户库工作单元。
        cache: 缓存 Region（阅读计数去重窗口）。

    Returns:
        HelpReaderService: 读者面服务实例。
    """
    return build_help_reader_service(
        tenant_uow=tenant_uow,
        cache=cache,
        locale=accept_locale(request),
        default_locale=get_default_locale(),
    )


ReaderServiceDep = Annotated[HelpReaderService, Depends(reader_service)]


def maintenance_service(
    tenant_uow: Annotated[UnitOfWork, Depends(get_uow)],
    platform_uow: Annotated[UnitOfWork, Depends(get_platform_uow)],
    outbox: Annotated[BaseOutboxStore, Depends(get_outbox_store)],
    cache: Annotated[CacheRegion, Depends(get_cache_region)],
) -> HelpMaintenanceService:
    """构造请求级维护服务。

    Args:
        tenant_uow: 租户库工作单元（内容表）。
        platform_uow: 平台库工作单元（锚点清单）。
        outbox: 发件箱存储（事件发布）。
        cache: 缓存 Region（内容版本键）。

    Returns:
        HelpMaintenanceService: 维护服务实例。
    """
    return build_help_maintenance_service(
        tenant_uow=tenant_uow,
        platform_uow=platform_uow,
        outbox=outbox,
        cache=cache,
    )


MaintenanceServiceDep = Annotated[HelpMaintenanceService, Depends(maintenance_service)]


def statistics_service(
    tenant_uow: Annotated[UnitOfWork, Depends(get_uow)],
) -> HelpStatisticsService:
    """构造请求级统计服务。

    Args:
        tenant_uow: 租户库工作单元。

    Returns:
        HelpStatisticsService: 统计服务实例。
    """
    return build_help_statistics_service(tenant_uow=tenant_uow)


StatisticsServiceDep = Annotated[HelpStatisticsService, Depends(statistics_service)]


def package_admin_service(
    tenant_uow: Annotated[UnitOfWork, Depends(get_uow)],
    platform_uow: Annotated[UnitOfWork, Depends(get_platform_uow)],
    cache: Annotated[CacheRegion, Depends(get_cache_region)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> HelpPackageAdminService:
    """构造请求级帮助包管理服务。

    Args:
        tenant_uow: 租户库工作单元（内容表）。
        platform_uow: 平台库工作单元（锚点清单）。
        cache: 缓存 Region（内容版本键）。
        settings: 应用配置（装载根目录）。

    Returns:
        HelpPackageAdminService: 包管理服务实例。
    """
    return build_help_package_admin_service(
        tenant_uow=tenant_uow,
        platform_uow=platform_uow,
        cache=cache,
        root=settings.help_package.root,
    )


PackageAdminServiceDep = Annotated[HelpPackageAdminService, Depends(package_admin_service)]

SettingsDep = Annotated[Settings, Depends(get_settings)]
