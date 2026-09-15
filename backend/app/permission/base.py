"""权限校验能力域：权限码校验基座契约（真实 RBAC + 主体链随 RBAC 阶段回补）。

- `BasePermissionChecker`：能力域中间层契约（`key = "permission"`）——`check` 判定权限码、
  `require` 强制校验（失败抛 `PermissionError`，30001 / 403）；与数据侧 `DataScope` 分工
  （权限码校验 vs 数据范围过滤）。
- `get_permission_checker` / `require_permission`：依赖注入提供者与 FastAPI 依赖工厂；
  公共依赖经 `app/api/deps.py` 统一导出。

本契约按需求 02-24 完整交付（契约代码由 02-3-5 提前落地，02-3-9 实施时复用，不重复建设）。
"""

from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import cast

from fastapi import Request

from app.core.config import Settings
from app.core.exceptions import PermissionError
from app.core.plugin import DEFAULT_CONTRACT_VERSION, NULL_PLUGIN_NAME, BasePluggable, resolve_plugin


class BasePermissionChecker(BasePluggable, ABC):
    """权限校验契约：权限码判定 + 强制校验。"""

    key: str = "permission"
    plugin_key: str = "permission"
    plugin_name: str = NULL_PLUGIN_NAME
    contract_version: str = DEFAULT_CONTRACT_VERSION

    @abstractmethod
    def check(self, code: str) -> bool:
        """是否持指定权限码。

        Args:
            code: 权限码（`业务:动作`，如 `data:plain`）。

        Returns:
            bool: 持有为 True。
        """

    def require(self, code: str) -> None:
        """强制校验权限码。

        Args:
            code: 权限码。

        Raises:
            PermissionError: 不持该权限码（30001 / 403，全局处理器统一转响应）。
        """
        if not self.check(code):
            raise PermissionError(f"缺少权限：{code}")


def get_permission_checker(request: Request) -> BasePermissionChecker:
    """取应用级权限检查器（依赖注入提供者）。

    Args:
        request: 请求对象。

    Returns:
        BasePermissionChecker: 应用装配的检查器实例。
    """
    settings = cast("Settings", request.app.state.settings)
    return cast(
        "BasePermissionChecker",
        resolve_plugin(
            "permission",
            settings.permission.provider,
            expected_version=BasePermissionChecker.contract_version,
        ),
    )


def require_permission(code: str) -> Callable[..., None]:
    """构造权限校验依赖（FastAPI 依赖工厂）。

    Args:
        code: 权限码（`业务:动作`）。

    Returns:
        Callable[[Request], None]: 可直接用于 `Depends(...)` 的依赖函数。
    """

    def _dependency(request: Request) -> None:
        """校验当前请求是否持权限码。

        Args:
            request: 请求对象。

        Raises:
            PermissionError: 不持该权限码（30001 / 403）。
        """
        get_permission_checker(request).require(code)

    return _dependency
