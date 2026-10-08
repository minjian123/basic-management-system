"""权限校验能力域：权限码校验基座契约（真实 RBAC + 主体链随 RBAC 阶段回补）。

- `BasePermissionChecker`：能力域中间层契约（`key = "permission"`）——`check` 判定权限码、
  `require` 强制校验（失败抛 `PermissionError`，30001 / 403）；与数据侧 `DataScope` 分工
  （权限码校验 vs 数据范围过滤）。
- `get_permission_checker` / `require_permission`：依赖注入提供者与 FastAPI 依赖工厂；
  公共依赖经 `app/api/deps.py` 统一导出。

本契约按需求 02-24 完整交付（契约代码由 02-3-5 提前落地，02-3-9 实施时复用，不重复建设）。
"""

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from typing import cast

from fastapi import Request

from bms_core.core.config import Settings
from bms_core.core.exceptions import PermissionError
from bms_core.core.plugin import DEFAULT_CONTRACT_VERSION, NULL_PLUGIN_NAME, BasePluggable, resolve_plugin


class BasePermissionChecker(BasePluggable, ABC):
    """权限校验契约：权限码判定 + 强制校验 + 请求级预加载。

    实现为**应用级单例**（`resolve_plugin` 复用唯一实例），故请求态（用户 / 租户 / 快照）一律经
    `core/context.py` 的 contextvar 承载；`aprepare` 为**请求级预加载钩子**：真实实现（如 RBAC）
    在此按请求计算并缓存「用户权限快照」，随后同步 `check` 只读快照。
    """

    key: str = "permission"
    plugin_key: str = "permission"
    plugin_name: str = NULL_PLUGIN_NAME
    contract_version: str = DEFAULT_CONTRACT_VERSION

    async def aprepare(self, *, request: Request) -> None:
        """请求级预加载钩子（缺省空实现）。

        真实实现（`rbac`）在此加载「当前用户权限快照」并落 contextvar，供同一请求内同步 `check`
        逐码判定复用（避免 N 次取快照）；占位实现无需任何准备。

        实现所需的会话 / 缓存等依赖由实现自行从 `request.app.state` 与会话作用域获取——
        基座不向本钩子注入依赖，避免给未接库的调用方增加装配负担。

        Args:
            request: 当前请求（可读 `request.state` 与应用装配状态）。
        """
        return None

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


def require_permission(code: str) -> Callable[..., Awaitable[None]]:
    """构造权限校验依赖（FastAPI 依赖工厂；含请求级预加载）。

    依赖先 `await checker.aprepare(...)`（真实实现加载权限快照、占位实现空操作），再同步 `require`；
    同一请求内 FastAPI 复用 `uow` / `cache` 依赖，且检查器把快照落入 contextvar 供逐码判定复用。

    Args:
        code: 权限码（`业务:动作`）。

    Returns:
        Callable[..., Awaitable[None]]: 可直接用于 `Depends(...)` 的异步依赖函数。
    """

    async def _dependency(request: Request) -> None:
        """预加载请求态并校验权限码。

        Args:
            request: 请求对象。

        Raises:
            PermissionError: 不持该权限码（30001 / 403）。
        """
        checker = get_permission_checker(request)
        prepare = getattr(checker, "aprepare", None)
        if callable(prepare):
            await cast("Callable[..., Awaitable[None]]", prepare)(request=request)
        checker.require(code)

    return _dependency


def prepare_permission_dependency() -> Callable[..., Awaitable[None]]:
    """构造「仅预加载、不校验」的依赖（供逐码自行判定的端点复用，如 `/api/v1/menus/my`）。

    Returns:
        Callable[..., Awaitable[None]]: 可直接用于 `Depends(...)` 的异步依赖函数。
    """

    async def _dependency(request: Request) -> None:
        """预加载当前请求的权限快照。

        Args:
            request: 请求对象。
        """
        await get_permission_checker(request).aprepare(request=request)

    return _dependency
