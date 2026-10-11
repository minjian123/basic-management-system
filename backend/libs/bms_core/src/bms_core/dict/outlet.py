"""字典统一出口：按字典标识经登记路由到数据源（02_09）。

口径（2026-10-11 用户拍板）：字典的取数 / 缓存 / 翻译 / 高级查询**全部保留**，只是**数据源改调字典
数据源出口**——按 `dict_key` 查 `DictRegistry` 登记 → 取 `data_source` → 路由到对应数据源提供者
（平台内建 / 产品注入）。**未登记 / 停用 / 无提供者**一律返回空结果（版本 0、`items=()`），与空实现同
语义，调用方无需区分。

- `BaseDictDataProvider`：单数据源取数提供者契约（`data_source` 与登记项 `data_source` 对齐）。
- `DictOutlet`：登记 + 提供者的只读路由视图（应用装配期构造）。
- `RoutedDictSource` / `RoutedDictTranslator`：统一出口的取数 / 翻译契约实现（经 `DictOutlet` 路由）。
"""

from abc import ABC, abstractmethod

from bms_core.core.concurrent import ConcurrentStableDict
from bms_core.core.objects import BaseFrameworkObject
from bms_core.dict.base import (
    BaseDictSource,
    BaseDictTranslator,
    DictBatchQuery,
    DictBatchResult,
    DictQuery,
    DictTranslateQuery,
    DictTypeResult,
)
from bms_core.dict.registry import DictRegistry

__all__ = [
    "BaseDictDataProvider",
    "DictOutlet",
    "NullDictDataProvider",
    "RoutedDictSource",
    "RoutedDictTranslator",
]


def _empty_result() -> DictTypeResult:
    """构造空取数结果（未登记 / 停用 / 无提供者）。

    Returns:
        DictTypeResult: 版本 0、`items=()` 的空结果。
    """
    return DictTypeResult(version=0, items=())


class BaseDictDataProvider(BaseFrameworkObject, ABC):
    """字典数据源提供者契约：一个 `data_source` 对应一个实现。

    提供者由数据所有者域实现（平台内建 / 产品注入），在应用装配期登记到 `DictOutlet`。
    """

    @property
    @abstractmethod
    def data_source(self) -> str:
        """数据出口标识（与登记项 `DictRecord.data_source` 对齐）。"""

    @abstractmethod
    async def fetch(self, query: DictQuery) -> DictTypeResult:
        """按字典标识取数（版本比对 / 关键字 / 级联 / 按值子集 / 上限由提供者按需支持）。

        Args:
            query: 单类型取数参数对象。

        Returns:
            DictTypeResult: 取数结果。
        """

    async def translate(self, query: DictTranslateQuery) -> ConcurrentStableDict[str, str]:
        """按 value 批量翻译为 label（缺省经 `fetch` 取子集后本地映射）。

        Args:
            query: 翻译参数对象。

        Returns:
            ConcurrentStableDict[str, str]: value → label（未命中不占位）。
        """
        subset = DictQuery(dict_type=query.dict_type, values=query.values)
        result = await self.fetch(subset)
        mapping: ConcurrentStableDict[str, str] = ConcurrentStableDict()
        for item in result.items or ():
            if item.value in query.values:
                mapping.set(item.value, item.label)
        return mapping


class NullDictDataProvider(BaseDictDataProvider):
    """空数据源提供者（占位数据源的缺省实现；恒定空结果）。"""

    def __init__(self, data_source: str) -> None:
        """初始化。

        Args:
            data_source: 数据出口标识（占位数据源可用任意名）。
        """
        self._data_source = data_source

    @property
    def data_source(self) -> str:
        """数据出口标识。

        Returns:
            str: 数据出口标识。
        """
        return self._data_source

    async def fetch(self, query: DictQuery) -> DictTypeResult:
        """恒返回空结果。

        Args:
            query: 单类型取数参数对象。

        Returns:
            DictTypeResult: 空结果。
        """
        return _empty_result()


class DictOutlet(BaseFrameworkObject):
    """字典数据源出口：登记 + 提供者的只读路由视图。

    应用装配期由 `merge_dict_records()` 结果构造 `DictRegistry`，并注入各数据源提供者；
    运行期只读（无进程级注册表、不改常量）。
    """

    def __init__(
        self,
        registry: DictRegistry,
        providers: ConcurrentStableDict[str, BaseDictDataProvider],
    ) -> None:
        """初始化。

        Args:
            registry: 字典数据源登记（应用装配视图）。
            providers: 提供者映射（`data_source` → 提供者）。
        """
        self._registry = registry
        self._providers: ConcurrentStableDict[str, BaseDictDataProvider] = ConcurrentStableDict(
            (str(key), value) for key, value in providers.items()
        )

    @property
    def registry(self) -> DictRegistry:
        """登记注册表。

        Returns:
            DictRegistry: 登记注册表。
        """
        return self._registry

    def provider_for(self, dict_key: str) -> BaseDictDataProvider | None:
        """按字典标识解析提供者（经登记 → `data_source` → 提供者）。

        Args:
            dict_key: 字典标识。

        Returns:
            BaseDictDataProvider | None: 命中且启用返回提供者；未登记 / 停用 / 无提供者返回 None。
        """
        record = self._registry.get(dict_key)
        if record is None or record.status != "enabled":
            return None
        return self._providers.get(record.data_source)


class RoutedDictSource(BaseDictSource):
    """统一出口·取数：按字典标识经 `DictOutlet` 路由到数据源（未命中等价空结果）。"""

    def __init__(self, outlet: DictOutlet) -> None:
        """初始化。

        Args:
            outlet: 字典数据源出口。
        """
        self._outlet = outlet

    async def by_type(self, query: DictQuery) -> DictTypeResult:
        """按字典标识取数（路由到数据源）。

        Args:
            query: 单类型取数参数对象。

        Returns:
            DictTypeResult: 取数结果（未登记 / 停用 / 无提供者为空结果）。
        """
        provider = self._outlet.provider_for(query.dict_type)
        if provider is None:
            return _empty_result()
        return await provider.fetch(query)

    async def batch(self, query: DictBatchQuery) -> DictBatchResult:
        """批量合并取数（逐标识路由合并）。

        Args:
            query: 批量取数参数对象。

        Returns:
            DictBatchResult: 批量结果（版本一致的类型 items=None）。
        """
        items: ConcurrentStableDict[str, DictTypeResult | None] = ConcurrentStableDict()
        version = 0
        for dict_key in query.types:
            result = await self.by_type(DictQuery(dict_type=dict_key, version=query.version))
            version = max(version, result.version)
            items.set(dict_key, result)
        return DictBatchResult(version=version, items=items)


class RoutedDictTranslator(BaseDictTranslator):
    """统一出口·翻译：按字典标识经 `DictOutlet` 路由到数据源（未命中回退原值）。"""

    def __init__(self, outlet: DictOutlet) -> None:
        """初始化。

        Args:
            outlet: 字典数据源出口。
        """
        self._outlet = outlet

    async def translate(self, query: DictTranslateQuery) -> ConcurrentStableDict[str, str]:
        """按 value 批量翻译为 label（路由到数据源）。

        Args:
            query: 翻译参数对象。

        Returns:
            ConcurrentStableDict[str, str]: value → label（未命中不占位）。
        """
        provider = self._outlet.provider_for(query.dict_type)
        if provider is None:
            return ConcurrentStableDict()
        return await provider.translate(query)
