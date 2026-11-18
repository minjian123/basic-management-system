"""帮助包管理面端点（`/api/v1/help/packages*`，12_01）。

- **鉴权**：`require_auth` + `help:package`（与内容维护 `help:manage` 分离授权）；
- **只装当前租户**：请求租户上下文决定目标租户库；`--all-tenants` 仍归命令行；
- **路径受限**：`package_path` 只接受 `[help_package].root` 内的相对路径（`40021`）。
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Query

from bms_core.api.base import BaseRouter, page_query, require_auth
from bms_core.permission.base import require_permission
from bms_core.schemas.common import ApiResponse
from bms_core.schemas.pagination import BasePageQuery
from bms_platform.domains.help.api.deps import PackageAdminServiceDep
from bms_platform.domains.help.schemas.package import (
    HelpPackageLoadRequest,
    HelpPackageLoadResult,
    HelpPackagePage,
    HelpPackageUnloadRequest,
    HelpPackageUnloadResult,
)

__all__ = ["router"]

router = BaseRouter(
    key="help_packages",
    prefix="/help",
    tags=["help"],
    dependencies=[Depends(require_auth)],
)

_REQUIRE_PACKAGE = Depends(require_permission("help:package"))
"""帮助包装载 / 卸载独立权限码（概要 17 §6）。"""

PageDep = Annotated[BasePageQuery, Depends(page_query)]


@router.get("/packages", dependencies=[_REQUIRE_PACKAGE])
async def list_packages(
    service: PackageAdminServiceDep,
    page: PageDep,
    product_key: Annotated[str | None, Query(max_length=64, description="产品键过滤")] = None,
    status: Annotated[str | None, Query(pattern="^(loaded|outdated|unloaded)$", description="包状态过滤")] = None,
) -> ApiResponse[HelpPackagePage]:
    """已装载帮助包列表（装载时间倒序）。

    Args:
        service: 包管理服务。
        page: 统一分页参数。
        product_key: 产品键过滤。
        status: 包状态过滤。

    Returns:
        ApiResponse[HelpPackagePage]: 统一响应，data 为分页包登记。
    """
    return ApiResponse.ok(
        await service.list_packages(
            product_key=product_key,
            status=status,
            page=page.page,
            size=page.size,
        )
    )


@router.post("/packages/load", dependencies=[_REQUIRE_PACKAGE])
async def load_package(
    payload: HelpPackageLoadRequest,
    service: PackageAdminServiceDep,
) -> ApiResponse[HelpPackageLoadResult]:
    """装载或升级帮助包（`dry_run` 缺省 true）。

    路径越界 / 绝对路径 / 不存在 `40021`；版本冲突 `40011`；校验和不符 `40010`；锚点不可解析 `40008`。

    Args:
        payload: 装载请求。
        service: 包管理服务。

    Returns:
        ApiResponse[HelpPackageLoadResult]: 统一响应，data 为装载结果。
    """
    return ApiResponse.ok(
        await service.load(
            package_path=payload.package_path,
            dry_run=payload.dry_run,
            lenient=payload.lenient,
        )
    )


@router.post("/packages/{product_key}/unload", dependencies=[_REQUIRE_PACKAGE])
async def unload_package(
    product_key: str,
    payload: HelpPackageUnloadRequest,
    service: PackageAdminServiceDep,
) -> ApiResponse[HelpPackageUnloadResult]:
    """卸载某产品的帮助包（`dry_run` 缺省 true）。

    该产品未装载 `40012`。

    Args:
        product_key: 产品键。
        payload: 卸载请求。
        service: 包管理服务。

    Returns:
        ApiResponse[HelpPackageUnloadResult]: 统一响应，data 为卸载结果。
    """
    return ApiResponse.ok(await service.unload(product_key=product_key, dry_run=payload.dry_run))
