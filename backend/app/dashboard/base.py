"""首页工作台卡片能力域：卡片提供者与注册表契约（真实卡片注册与模板解析随首页工作台阶段回补）。

- `CARD_TYPES`：卡片类型（双轨制：`builtin` 内置功能卡 / `dataset` 数据集图表卡）。
- `BaseDashboardCardProvider`：卡片提供者契约（抽象 `key` + 同步 `metadata` / 异步 `fetch`）。
- `BaseDashboardCardRegistry`：能力域中间层契约（`key = "dashboard_card_registry"`）——抽象 `register` / `get` / `keys`
  + **具体聚合模板** `metadata` / `fetch`（解析卡片 → 委托；未命中抛 `NotFoundError`）。
- `get_dashboard_card_registry`：依赖注入提供者（应用级单例；公共依赖经 `app/api/deps.py` 统一导出）。

口径：卡片元数据随布局接口下发（前端不硬编码卡片清单）；`fetch` 转发来源模块既有接口、**不绕行其权限校验**；
数据集卡取 02-4-9 `BaseQueryProvider`；三级模板回退与布局缓存归上层（首页工作台阶段）。
"""

from abc import ABC, abstractmethod
from collections.abc import Mapping
from typing import cast

from fastapi import Request

from app.core.config import Settings
from app.core.exceptions import NotFoundError
from app.core.plugin import DEFAULT_CONTRACT_VERSION, NULL_PLUGIN_NAME, BasePluggable, resolve_plugin
from app.core.provider import BaseProvider

__all__ = [
    "CARD_TYPES",
    "BaseDashboardCardProvider",
    "BaseDashboardCardRegistry",
    "get_dashboard_card_registry",
]

CARD_TYPES: tuple[str, ...] = ("builtin", "dataset")
"""卡片类型（双轨制：内置功能卡 / 数据集图表卡）；占位期仅登记不校验。"""


class BaseDashboardCardProvider(BaseProvider, ABC):
    """卡片提供者契约：元数据 + 取数。"""

    @abstractmethod
    def metadata(self) -> Mapping[str, object]:
        """卡片元数据（名称 / 尺寸 / `render_key` / 数据接口地址 / `card_type` 等）。

        Returns:
            Mapping[str, object]: 元数据。
        """

    @abstractmethod
    async def fetch(self, params: Mapping[str, object]) -> Mapping[str, object]:
        """取卡片数据（真实实现转发来源模块既有接口，不绕行其权限校验）。

        Args:
            params: 取数参数。

        Returns:
            Mapping[str, object]: 卡片数据。
        """


class BaseDashboardCardRegistry(BasePluggable, ABC):
    """卡片注册表契约：注册 / 解析 / 卡片集 + 元数据与取数聚合。"""

    key: str = "dashboard_card_registry"
    plugin_key: str = "dashboard_card_registry"
    plugin_name: str = NULL_PLUGIN_NAME
    contract_version: str = DEFAULT_CONTRACT_VERSION

    @abstractmethod
    def register(self, provider: BaseDashboardCardProvider) -> None:
        """注册卡片（启动期注册）。

        Args:
            provider: 卡片提供者。
        """

    @abstractmethod
    def get(self, key: str) -> BaseDashboardCardProvider | None:
        """按 key 解析卡片。

        Args:
            key: 卡片标识。

        Returns:
            BaseDashboardCardProvider | None: 提供者；未命中返回 None。
        """

    @abstractmethod
    def keys(self) -> tuple[str, ...]:
        """已注册卡片 key 清单（注册顺序）。

        Returns:
            tuple[str, ...]: 卡片 key 元组。
        """

    def metadata(self, card_key: str) -> Mapping[str, object]:
        """聚合元数据（模板方法：解析卡片 → 委托）。

        Args:
            card_key: 卡片标识。

        Returns:
            Mapping[str, object]: 卡片元数据。

        Raises:
            NotFoundError: 卡片不存在（10002 / 404，全局处理器统一转响应）。
        """
        provider = self.get(card_key)
        if provider is None:
            raise NotFoundError(f"工作台卡片不存在：{card_key}")
        return provider.metadata()

    async def fetch(self, card_key: str, params: Mapping[str, object]) -> Mapping[str, object]:
        """聚合取数（模板方法：解析卡片 → 委托）。

        Args:
            card_key: 卡片标识。
            params: 取数参数。

        Returns:
            Mapping[str, object]: 卡片数据。

        Raises:
            NotFoundError: 卡片不存在（10002 / 404）。
        """
        provider = self.get(card_key)
        if provider is None:
            raise NotFoundError(f"工作台卡片不存在：{card_key}")
        return await provider.fetch(params)


def get_dashboard_card_registry(request: Request) -> BaseDashboardCardRegistry:
    """取应用级工作台卡片注册表（依赖注入提供者）。

    Args:
        request: 请求对象。

    Returns:
        BaseDashboardCardRegistry: 应用装配的注册表实例。
    """
    settings = cast("Settings", request.app.state.settings)
    return cast(
        "BaseDashboardCardRegistry",
        resolve_plugin(
            "dashboard_card_registry",
            settings.dashboard_card_registry.provider,
            expected_version=BaseDashboardCardRegistry.contract_version,
        ),
    )
