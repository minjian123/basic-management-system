"""数据查询提供者能力域：统一查询提供者与注册表契约（真实数据集 / 字典高级查询随报表 / 表单定制阶段回补）。

- `QueryResult`：查询结果数据契约（frozen）。
- `BaseQueryProvider`：提供者契约（抽象属性 `key` + 异步 `query`，**只读数据源约束**）。
- `BaseQueryProviderRegistry`：能力域中间层契约（`key = "query_provider_registry"`）——抽象 `register` / `get` / `keys`
  + **具体聚合模板** `query`（解析提供者 → 委托；未命中抛 `NotFoundError`）。
- `get_query_provider_registry`：依赖注入提供者（应用级单例；公共依赖经 `app/api/deps.py` 统一导出）。

口径：报表数据集与字典高级查询各自注册提供者，前端只做发现与调用（架构 29）；数据集白名单 + 只读从库 +
租户隔离由实现保证，禁止经本域写库。真实实现随报表 BI / 表单定制阶段回补。
"""

from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass
from typing import cast

from fastapi import Request

from app.core.base import BaseObject
from app.core.config import Settings
from app.core.exceptions import NotFoundError
from app.core.plugin import DEFAULT_CONTRACT_VERSION, NULL_PLUGIN_NAME, BasePluggable, resolve_plugin
from app.core.provider import BaseProvider

__all__ = [
    "BaseQueryProvider",
    "BaseQueryProviderRegistry",
    "QueryResult",
    "get_query_provider_registry",
]


@dataclass(frozen=True)
class QueryResult(BaseObject):
    """查询结果。"""

    rows: tuple[Mapping[str, object], ...]
    """结果行（每行字段映射）。"""

    total: int = 0
    """结果总数。"""


class BaseQueryProvider(BaseProvider, ABC):
    """查询提供者契约：`key` + 只读查询。"""

    @abstractmethod
    async def query(self, params: Mapping[str, object]) -> QueryResult:
        """执行只读查询（**只读数据源约束**：数据集白名单 / 只读从库由实现保证）。

        Args:
            params: 查询参数。

        Returns:
            QueryResult: 查询结果。
        """


class BaseQueryProviderRegistry(BasePluggable, ABC):
    """查询提供者注册表契约：注册 / 解析 / 清单 + 聚合查询。"""

    key: str = "query_provider_registry"
    plugin_key: str = "query_provider_registry"
    plugin_name: str = NULL_PLUGIN_NAME
    contract_version: str = DEFAULT_CONTRACT_VERSION

    @abstractmethod
    def register(self, provider: BaseQueryProvider) -> None:
        """注册查询提供者（启动期注册）。

        Args:
            provider: 查询提供者。
        """

    @abstractmethod
    def get(self, key: str) -> BaseQueryProvider | None:
        """按 key 解析提供者。

        Args:
            key: 提供者标识。

        Returns:
            BaseQueryProvider | None: 提供者；未命中返回 None。
        """

    @abstractmethod
    def keys(self) -> tuple[str, ...]:
        """已注册提供者 key 清单（注册顺序）。

        Returns:
            tuple[str, ...]: 提供者 key 元组。
        """

    async def query(self, key: str, params: Mapping[str, object]) -> QueryResult:
        """聚合查询（模板方法：解析提供者 → 委托）。

        Args:
            key: 提供者标识。
            params: 查询参数。

        Returns:
            QueryResult: 查询结果。

        Raises:
            NotFoundError: 提供者不存在（10002 / 404，全局处理器统一转响应）。
        """
        provider = self.get(key)
        if provider is None:
            raise NotFoundError(f"查询提供者不存在：{key}")
        return await provider.query(params)


def get_query_provider_registry(request: Request) -> BaseQueryProviderRegistry:
    """取应用级查询提供者注册表（依赖注入提供者）。

    Args:
        request: 请求对象。

    Returns:
        BaseQueryProviderRegistry: 应用装配的注册表实例。
    """
    settings = cast("Settings", request.app.state.settings)
    return cast(
        "BaseQueryProviderRegistry",
        resolve_plugin(
            "query_provider_registry",
            settings.query_provider_registry.provider,
            expected_version=BaseQueryProviderRegistry.contract_version,
        ),
    )
