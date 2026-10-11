"""字典统一出口：按字典标识经登记路由到数据源（02_09）。

口径（2026-10-11 用户拍板）：字典的取数 / 缓存 / 翻译 / 高级查询**全部保留**，只是**数据源改调字典
数据源出口**——按 `dict_key` 查 `DictRegistry` 登记 → 取 `data_source` → 路由到对应数据源提供者
（平台内建）。**未登记 / 停用 / 无提供者**一律返回空结果（版本 0、`items=()`），与空实现同语义。

- `BaseDictDataProvider`：单数据源取数提供者契约（`data_source` 与登记项 `data_source` 对齐）——只负责
  **加载某字典全部启用条目**；版本比对 / 缓存（L1 双分区 + Redis）/ 关键字 / 级联 / 按值子集 / 探针截断
  **由出口统一承载**（功能一个不能少）。
- `DictOutlet`：登记 + 提供者的只读路由视图（应用装配期构造）。
- `RoutedDictSource` / `RoutedDictTranslator`：统一出口的取数 / 翻译契约实现（经 `DictOutlet` 路由 + 缓存）。
- 产品来源字典（`origin=product`）**不经平台出口**：由前端经网关直取产品命名空间（`/api/{product_key}/v1/...`）。
"""

import asyncio
from abc import ABC, abstractmethod
from collections.abc import Mapping
from typing import cast
from uuid import uuid4

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.objects import BaseFrameworkObject
from bms_core.db.tenant import current_tenant_id_str
from bms_core.dict.base import (
    DICT_PROBE_LIMIT,
    BaseDictSource,
    BaseDictTranslator,
    DictBatchQuery,
    DictBatchResult,
    DictCacheRegion,
    DictItem,
    DictQuery,
    DictTranslateQuery,
    DictTypeResult,
    current_dict_locale,
)
from bms_core.dict.cache import MemoryDictCacheRegion
from bms_core.dict.registry import DictRegistry, merge_dict_records
from bms_core.i18n.base import DEFAULT_LOCALE

__all__ = [
    "LOCK_TTL_SECONDS",
    "LOCK_WAIT_SECONDS",
    "BaseDictDataProvider",
    "DictOutlet",
    "EmptyDictDataProvider",
    "RoutedDictSource",
    "RoutedDictTranslator",
    "build_dict_outlet",
    "register_dict_provider",
    "registered_dict_providers",
]

LOCK_TTL_SECONDS = 5
"""取数互斥锁有效期（秒）。"""

LOCK_WAIT_SECONDS = 0.05
"""未获锁短暂等待（秒）后重读缓存，仍无则回源（防击穿）。"""


def _empty_result() -> DictTypeResult:
    """构造空取数结果（未登记 / 停用 / 无提供者）。

    Returns:
        DictTypeResult: 版本 0、`items=()` 的空结果。
    """
    return DictTypeResult(version=0, items=())


class BaseDictDataProvider(BaseFrameworkObject, ABC):
    """字典数据源提供者契约：一个 `data_source` 对应一个实现。

    提供者只负责**加载某字典的全部启用条目**（locale 感知）；版本比对 / 缓存 / 关键字 / 级联 /
    按值子集 / 探针截断由统一出口承载。提供者由数据所有者域实现（平台内建）。
    """

    @property
    @abstractmethod
    def data_source(self) -> str:
        """数据出口标识（与登记项 `DictRecord.data_source` 对齐）。"""

    @abstractmethod
    async def load(self, dict_key: str, locale: str) -> tuple[DictItem, ...]:
        """加载某字典全部启用条目（供出口做过滤 / 截断 / 缓存）。

        Args:
            dict_key: 字典标识。
            locale: 语言。

        Returns:
            tuple[DictItem, ...]: 启用条目（未登记字典返回空元组）。
        """


class EmptyDictDataProvider(BaseDictDataProvider):
    """空数据源提供者（占位数据源的缺省实现；恒定空条目）。"""

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

    async def load(self, dict_key: str, locale: str) -> tuple[DictItem, ...]:
        """恒返回空条目。

        Args:
            dict_key: 字典标识。
            locale: 语言。

        Returns:
            tuple[DictItem, ...]: 空元组。
        """
        return ()


class DictOutlet(BaseFrameworkObject):
    """字典数据源出口：登记 + 提供者的只读路由视图（运行期只读）。"""

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


def _apply_filters(items: tuple[DictItem, ...], query: DictQuery) -> tuple[DictItem, ...]:
    """按查询条件过滤条目（按值子集 / 关键字 / 上级条目 ID）。

    Args:
        items: 全量启用条目。
        query: 单类型取数参数。

    Returns:
        tuple[DictItem, ...]: 过滤后的条目。
    """
    result = items
    if query.values is not None:
        wanted = set(query.values)
        result = tuple(item for item in result if item.value in wanted)
    if query.keyword:
        keyword = query.keyword
        result = tuple(
            item for item in result if keyword in item.label or keyword in item.value or keyword in item.code
        )
    if query.parent_id is not None:
        parent = None if query.parent_id == 0 else query.parent_id
        result = tuple(item for item in result if item.parent_id == parent)
    return result


def _snapshot_payload(result: DictTypeResult) -> ConcurrentStableDict[str, object]:
    """结果 → 缓存载荷（版本 / 条目 / 截断 / 总数）。

    Args:
        result: 取数结果。

    Returns:
        ConcurrentStableDict[str, object]: 缓存载荷。
    """
    payload: ConcurrentStableDict[str, object] = ConcurrentStableDict()
    payload.set("version", result.version)
    payload.set("items", [dict(item.model_dump(mode="json")) for item in result.items or ()])
    payload.set("has_more", result.has_more)
    payload.set("total", result.total)
    return payload


def _cache_snapshot(payload: object, version: int) -> DictTypeResult | None:
    """缓存载荷 → 结果（版本一致才算命中）。

    Args:
        payload: 缓存值。
        version: 当前版本号。

    Returns:
        DictTypeResult | None: 命中结果；未命中 / 版本不符返回 None。
    """
    if not isinstance(payload, Mapping):
        return None
    data = cast("Mapping[str, object]", payload)
    if int(data.get("version", -1)) != version:  # pyright: ignore[reportArgumentType]
        return None
    raw_items = data.get("items")
    items: tuple[DictItem, ...] = ()
    if isinstance(raw_items, list):
        items = tuple(DictItem.model_validate(item) for item in cast("list[object]", raw_items))
    return DictTypeResult(
        version=version,
        items=items,
        has_more=bool(data.get("has_more", False)),
        total=int(data.get("total", 0)),  # pyright: ignore[reportArgumentType]
    )


def _is_filtered(query: DictQuery) -> bool:
    """是否带过滤条件（关键字 / 级联 / 按值子集 / 上限）。

    Args:
        query: 单类型取数参数。

    Returns:
        bool: 带过滤返回 True。
    """
    return (
        query.keyword is not None or query.parent_id is not None or query.values is not None or query.limit is not None
    )


class RoutedDictSource(BaseDictSource):
    """统一出口·取数：按字典标识经 `DictOutlet` 路由到数据源 + 缓存。

    承载版本比对三态 / L1+Redis 缓存（双分区、版本键、SETNX 互斥锁、TTL）/ 关键字 / 级联 / 按值子集 /
    探针截断（功能一个不能少）。
    """

    def __init__(self, outlet: DictOutlet, cache: DictCacheRegion | None = None) -> None:
        """初始化。

        Args:
            outlet: 字典数据源出口。
            cache: 字典缓存域（缺省进程内实现；装配侧注入配置选定的实现）。
        """
        self._outlet = outlet
        self._cache = cache or MemoryDictCacheRegion()

    @property
    def cache(self) -> DictCacheRegion:
        """字典缓存域（供测试与登记核对）。

        Returns:
            DictCacheRegion: 缓存域实例。
        """
        return self._cache

    @property
    def outlet(self) -> DictOutlet:
        """字典数据源出口（供测试核对）。

        Returns:
            DictOutlet: 出口实例。
        """
        return self._outlet

    async def by_type(self, query: DictQuery) -> DictTypeResult:
        """按字典标识取数（路由 + 缓存 + 过滤 + 截断）。

        Args:
            query: 单类型取数参数对象。

        Returns:
            DictTypeResult: 取数结果（版本一致时 `items=None`；未登记 / 停用为空结果）。
        """
        provider = self._outlet.provider_for(query.dict_key)
        if provider is None:
            return _empty_result()
        locale = current_dict_locale.get() or DEFAULT_LOCALE
        tenant = current_tenant_id_str()
        version = await self._cache.aversion(tenant)
        if query.version is not None and query.version == version:
            return DictTypeResult(version=version, items=None)
        filtered = _is_filtered(query)
        cacheable_read = not filtered
        if cacheable_read:
            snapshot = _cache_snapshot(await self._cache.aget_type(tenant, locale, query.dict_key), version)
            if snapshot is not None:
                return snapshot
        token = uuid4().hex
        locked = await self._cache.alock(tenant, locale, query.dict_key, token, LOCK_TTL_SECONDS)
        if not locked:
            await asyncio.sleep(LOCK_WAIT_SECONDS)
            if cacheable_read:
                snapshot = _cache_snapshot(await self._cache.aget_type(tenant, locale, query.dict_key), version)
                if snapshot is not None:
                    return snapshot
        try:
            loaded = await provider.load(query.dict_key, locale)
            items = _apply_filters(loaded, query)
            total = len(items)
            has_more = query.limit is not None and total > query.limit
            if query.limit is not None:
                items = items[: query.limit]
        finally:
            if locked:
                await self._cache.arelease_lock(tenant, locale, query.dict_key, token)
        result = DictTypeResult(version=version, items=items, has_more=has_more, total=total)
        if cacheable_read:
            await self._cache.aset_type(tenant, locale, query.dict_key, _snapshot_payload(result))
        return result

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
            cached_read = query.version
            result = await self.by_type(DictQuery(dict_key=dict_key, version=cached_read, limit=DICT_PROBE_LIMIT))
            version = max(version, result.version)
            items.set(dict_key, result)
        return DictBatchResult(version=version, items=items)


class RoutedDictTranslator(BaseDictTranslator):
    """统一出口·翻译：按字典标识经 `DictOutlet` 路由 + 与取数共用同一份 L1 缓存。"""

    def __init__(self, outlet: DictOutlet, cache: DictCacheRegion | None = None) -> None:
        """初始化。

        Args:
            outlet: 字典数据源出口。
            cache: 字典缓存域（与取数共用同一实例；缺省进程内实现）。
        """
        self._outlet = outlet
        self._cache = cache or MemoryDictCacheRegion()

    async def translate(self, query: DictTranslateQuery) -> ConcurrentStableDict[str, str]:
        """按 value 批量翻译为 label（当前 locale；未命中不占位）。

        Args:
            query: 翻译参数对象。

        Returns:
            ConcurrentStableDict[str, str]: value → label（仅命中项；未登记 / 停用返回空）。
        """
        provider = self._outlet.provider_for(query.dict_key)
        if provider is None:
            return ConcurrentStableDict()
        locale = query.locale or DEFAULT_LOCALE
        values = ConcurrentStableList(dict.fromkeys(query.values))
        if not values:
            return ConcurrentStableDict()
        loaded = await provider.load(query.dict_key, locale)
        wanted = set(values)
        mapping: ConcurrentStableDict[str, str] = ConcurrentStableDict()
        for item in loaded:
            if item.value in wanted:
                mapping.set(item.value, item.label)
        return ConcurrentStableDict((value, mapping[value]) for value in values if value in mapping)


_PROVIDERS: ConcurrentStableDict[str, BaseDictDataProvider] = ConcurrentStableDict()
"""平台内建数据源提供者注册表（各服务在装配期注入，口径同目录读取器 / 权限实现注册）。"""


def register_dict_provider(provider: BaseDictDataProvider) -> None:
    """登记平台内建数据源提供者（按 `data_source` 覆盖写）。

    Args:
        provider: 数据源提供者实例。
    """
    _PROVIDERS.set(provider.data_source, provider)


def registered_dict_providers() -> ConcurrentStableDict[str, BaseDictDataProvider]:
    """取已登记的平台内建数据源提供者（副本）。

    Returns:
        ConcurrentStableDict[str, BaseDictDataProvider]: `data_source` → 提供者。
    """
    return ConcurrentStableDict(_PROVIDERS)


def build_dict_outlet() -> DictOutlet:
    """按构建期清单（+ 已注入提供者）构造字典出口（应用装配期入口）。

    Returns:
        DictOutlet: 字典数据源出口。
    """
    return DictOutlet(DictRegistry(merge_dict_records()), registered_dict_providers())
