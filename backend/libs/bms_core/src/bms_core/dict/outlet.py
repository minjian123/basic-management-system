"""数据源统一出口：按数据源标识经登记路由到数据源（02_09 起，02_10 泛化）。

口径（2026-10-11 用户拍板）：字典的取数 / 缓存 / 翻译 / 高级查询**全部保留**，只是**数据源改调统一
数据源出口**——按 `data_source_key` 查 `DataSourceRegistry` 登记 → 取 `data_source` → 路由到对应
数据源提供者（平台内建）。**未登记 / 停用 / 无提供者**一律返回空结果（版本 0、`items=()`），与空实现
同语义。

- `BaseGenericDataSource` / `BaseDictDataSource`（`bms_core/datasource/base.py`）：数据源提供者契约——只负责
  **加载某数据源全部启用行**（`DataSourceItem`）；版本比对 / 缓存（L1 双分区 + Redis）/ 关键字 / 级联 /
  按条目 id 子集 / 探针截断 **由出口统一承载**（功能一个不能少）。
- `DataSourceOutlet`：登记 + 提供者的只读路由视图（应用装配期构造）。
- `RoutedDataSource` / `RoutedDictTranslator`：统一出口的取数 / 翻译契约实现（经 `DataSourceOutlet`
  路由 + 缓存）；出口负责 `DataSourceItem → DictItem`（对外契约）映射。
- 产品来源数据源（`origin=product`）**不经平台出口**：由前端经网关直取产品命名空间
  （`/api/{product_key}/v1/...`）。
"""

import asyncio
from collections.abc import Mapping
from typing import cast
from uuid import uuid4

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.logging import get_logger
from bms_core.core.objects import BaseFrameworkObject
from bms_core.datasource.base import BaseDictDataSource, BaseGenericDataSource, DataSourceItem
from bms_core.datasource.registry import DataSourceRegistry, data_source_records_view
from bms_core.db.tenant import current_tenant_id_str
from bms_core.dict.base import (
    BaseDataSource,
    BaseDictTranslator,
    DictBatchQuery,
    DictBatchResult,
    DictCacheRegion,
    DictItem,
    DictOptions,
    DictQuery,
    DictTranslateQuery,
    DictTypeResult,
    current_dict_locale,
)
from bms_core.dict.cache import MemoryDictCacheRegion
from bms_core.i18n.base import DEFAULT_LOCALE

__all__ = [
    "DataSourceOutlet",
    "EmptyDictDataSource",
    "RoutedDataSource",
    "RoutedDictTranslator",
    "build_data_source_outlet",
    "register_data_source",
    "registered_data_sources",
]

_LOGGER = get_logger("bms")


def _empty_result() -> DictTypeResult:
    """构造空取数结果（未登记 / 停用 / 无提供者）。

    Returns:
        DictTypeResult: 版本 0、`items=()` 的空结果。
    """
    return DictTypeResult(version=0, items=ConcurrentStableList(()))


async def _load_rows(
    provider: BaseGenericDataSource, data_source_key: str, locale: str
) -> ConcurrentStableList[DataSourceItem] | None:
    """调提供者取数（异常边界：单个字典失败不拖垮调用方）。

    兜底范围**只到提供者调用边界**：把「表缺失 / 库不可用 / 权限异常」这类运行时故障转成空结果 +
    `warning`，且失败结果**不写缓存**（避免把一次故障固化一个 TTL）；出口自身的过滤 / 缓存逻辑不包，
    编程错误照常暴露。

    Args:
        provider: 数据源提供者。
        data_source_key: 数据源标识。
        locale: 语言。

    Returns:
        ConcurrentStableList[DataSourceItem] | None: 启用行；提供者抛错时返回 None（调用方按空结果处理）。
    """
    try:
        return await provider.load(data_source_key, locale)
    except Exception as exc:  # 字典取数失败不得拖垮表单页；范围限于提供者边界
        _LOGGER.warning(
            "dict_load_failed",
            data_source_key=data_source_key,
            locale=locale,
            error_type=type(exc).__name__,
        )
        return None


class EmptyDictDataSource(BaseDictDataSource):
    """空数据源提供者（占位数据源的缺省实现；恒定空行）。"""

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

    async def load(self, data_source_key: str, locale: str) -> ConcurrentStableList[DataSourceItem]:
        """恒返回空行。

        Args:
            data_source_key: 数据源标识。
            locale: 语言。

        Returns:
            tuple[DataSourceItem, ...]: 空元组。
        """
        return ConcurrentStableList(())


class DataSourceOutlet(BaseFrameworkObject):
    """数据源出口：登记 + 提供者的只读路由视图（运行期只读）。"""

    def __init__(
        self,
        registry: DataSourceRegistry,
        providers: ConcurrentStableDict[str, BaseGenericDataSource],
    ) -> None:
        """初始化。

        Args:
            registry: 统一数据源登记（应用装配视图）。
            providers: 提供者映射（`data_source` → 提供者）。
        """
        self._registry = registry
        self._providers: ConcurrentStableDict[str, BaseGenericDataSource] = ConcurrentStableDict(
            (str(key), value) for key, value in providers.items()
        )

    @property
    def registry(self) -> DataSourceRegistry:
        """登记注册表。

        Returns:
            DataSourceRegistry: 登记注册表。
        """
        return self._registry

    def provider_for(self, data_source_key: str) -> BaseGenericDataSource | None:
        """按数据源标识解析提供者（经登记 → `data_source` → 提供者）。

        Args:
            data_source_key: 数据源标识。

        Returns:
            BaseGenericDataSource | None: 命中且启用返回提供者；未登记 / 停用 / 无提供者返回 None。
        """
        record = self._registry.get(data_source_key)
        if record is None or record.status != "enabled":
            return None
        return self._providers.get(record.data_source)


def _to_dict_item(item: DataSourceItem) -> DictItem:
    """通用条目 → 字典对外契约条目（出口映射）。

    Args:
        item: 通用数据条目。

    Returns:
        DictItem: 字典条目。
    """
    return DictItem(
        id=item.id,
        value=item.value,
        label=item.label,
        code=item.code,
        parent_id=item.parent_id,
        sort=item.sort,
        status=item.status,
        color=item.color,
    )


def _apply_filters(items: ConcurrentStableList[DictItem], query: DictQuery) -> ConcurrentStableList[DictItem]:
    """按查询条件过滤条目（按条目 id 子集 / 关键字 / 上级条目 ID）。

    Args:
        items: 全量启用条目。
        query: 单类型取数参数。

    Returns:
        tuple[DictItem, ...]: 过滤后的条目。
    """
    result = items
    if query.ids is not None:
        wanted = set(query.ids)
        result = tuple(item for item in result if item.id in wanted)
    if query.keyword:
        keyword = query.keyword
        result = tuple(
            item for item in result if keyword in item.label or keyword in item.value or keyword in item.code
        )
    if query.parent_id is not None:
        parent = None if query.parent_id == 0 else query.parent_id
        result = tuple(item for item in result if item.parent_id == parent)
    return result  # pyright: ignore[reportReturnType]  # 08_05：注解落集合类，值形态由契约/外部决定


def _snapshot_payload(result: DictTypeResult) -> object:
    """结果 → 缓存载荷（版本 / 条目 / 截断 / 总数；**JSON 可往返的普通结构**）。

    载荷会进 Redis 共享层（`json.dumps` + `json.loads`），因此必须是普通 `dict` / `list`：
    早前用 `ConcurrentStableDict` 作载荷，`json.dumps(..., default=str)` 会把它变成一个
    repr 字符串，读回时 `json.loads` 失败 → 共享层**只写不读**（跨实例永远打不中）。
    集合类型约束只针对声明处的容器，这里跨 JSON 边界，按「序列化载荷用普通结构」处理。

    Args:
        result: 取数结果。

    Returns:
        object: 缓存载荷（`{"version": int, "items": [dict...], "has_more": bool, "total": int}`）。
    """
    return {
        "version": result.version,
        "items": [item.model_dump(mode="json") for item in result.items or ()],
        "has_more": result.has_more,
        "total": result.total,
    }


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
    items: ConcurrentStableList[DictItem] = ConcurrentStableList()
    if isinstance(raw_items, list):
        items = ConcurrentStableList(DictItem.model_validate(item) for item in cast("list[object]", raw_items))
    return DictTypeResult(
        version=version,
        items=items,
        has_more=bool(data.get("has_more", False)),
        total=int(data.get("total", 0)),  # pyright: ignore[reportArgumentType]
    )


def _is_filtered(query: DictQuery) -> bool:
    """是否带过滤条件（关键字 / 级联 / 按条目 id 子集 / 上限）。

    Args:
        query: 单类型取数参数。

    Returns:
        bool: 带过滤返回 True。
    """
    return query.keyword is not None or query.parent_id is not None or query.ids is not None or query.limit is not None


class RoutedDataSource(BaseDataSource):
    """统一出口·取数：按数据源标识经 `DataSourceOutlet` 路由到数据源 + 缓存。

    承载版本比对三态 / L1+Redis 缓存（双分区、版本键、SETNX 互斥锁、TTL）/ 关键字 / 级联 / 按条目 id 子集 /
    探针截断（功能一个不能少）；并负责通用条目 → 字典对外契约条目映射。
    """

    def __init__(
        self,
        outlet: DataSourceOutlet,
        cache: DictCacheRegion | None = None,
        options: DictOptions | None = None,
    ) -> None:
        """初始化。

        Args:
            outlet: 数据源出口。
            cache: 字典缓存域（缺省进程内实现；装配侧注入配置选定的实现）。
            options: 出口运行参数（缺省取配置缺省值；装配侧注入 `[dict]` 节）。
        """
        self._outlet = outlet
        self._cache = cache or MemoryDictCacheRegion()
        self._options = options or DictOptions()

    @property
    def cache(self) -> DictCacheRegion:
        """字典缓存域（供测试与登记核对）。

        Returns:
            DictCacheRegion: 缓存域实例。
        """
        return self._cache

    @property
    def outlet(self) -> DataSourceOutlet:
        """数据源出口（供测试核对）。

        Returns:
            DataSourceOutlet: 出口实例。
        """
        return self._outlet

    async def by_type(self, query: DictQuery) -> DictTypeResult:
        """按数据源标识取数（路由 + 缓存 + 过滤 + 截断）。

        Args:
            query: 单类型取数参数对象。

        Returns:
            DictTypeResult: 取数结果（版本一致时 `items=None`；未登记 / 停用为空结果）。
        """
        provider = self._outlet.provider_for(query.data_source_key)
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
            snapshot = _cache_snapshot(await self._cache.aget_type(tenant, locale, query.data_source_key), version)
            if snapshot is not None:
                return snapshot
        token = uuid4().hex
        locked = await self._cache.alock(tenant, locale, query.data_source_key, token, self._options.lock_ttl_seconds)
        if not locked:
            await asyncio.sleep(self._options.lock_wait_seconds)
            if cacheable_read:
                snapshot = _cache_snapshot(await self._cache.aget_type(tenant, locale, query.data_source_key), version)
                if snapshot is not None:
                    return snapshot
        try:
            loaded = await _load_rows(provider, query.data_source_key, locale)
            if loaded is None:
                return _empty_result()
            items = _apply_filters(ConcurrentStableList(_to_dict_item(item) for item in loaded), query)
            total = len(items)
            has_more = query.limit is not None and total > query.limit
            if query.limit is not None:
                items = items[: query.limit]
        finally:
            if locked:
                await self._cache.arelease_lock(tenant, locale, query.data_source_key, token)
        result = DictTypeResult(version=version, items=items, has_more=has_more, total=total)
        if cacheable_read:
            ttl = self._options.type_ttl_seconds if items else self._options.empty_ttl_seconds
            await self._cache.aset_type(tenant, locale, query.data_source_key, _snapshot_payload(result), ttl)
        return result

    async def batch(self, query: DictBatchQuery) -> DictBatchResult:
        """批量合并取数（逐标识路由合并；按入参 `locale` 生效）。

        `DictBatchQuery.locale` 的契约缺省值就是「未指定」（默认中文），故与上下文语言同时存在时：
        入参非缺省 → 以入参为准；入参为缺省 → 沿用请求上下文（`Accept-Language`）。

        Args:
            query: 批量取数参数对象。

        Returns:
            DictBatchResult: 批量结果（版本一致的类型 items=None）。
        """
        requested = query.locale if query.locale and query.locale != DEFAULT_LOCALE else None
        token = current_dict_locale.set(requested or current_dict_locale.get() or DEFAULT_LOCALE)
        try:
            items: ConcurrentStableDict[str, DictTypeResult | None] = ConcurrentStableDict()
            version = 0
            for data_source_key in query.types:
                result = await self.by_type(
                    DictQuery(
                        data_source_key=data_source_key,
                        version=query.version,
                        limit=self._options.probe_limit,
                    )
                )
                version = max(version, result.version)
                items.set(data_source_key, result)
        finally:
            current_dict_locale.reset(token)
        return DictBatchResult(version=version, items=items)


class RoutedDictTranslator(BaseDictTranslator):
    """统一出口·翻译：按数据源标识经 `DataSourceOutlet` 路由 + 与取数共用同一份 L1 缓存。"""

    def __init__(self, outlet: DataSourceOutlet, cache: DictCacheRegion | None = None) -> None:
        """初始化。

        Args:
            outlet: 数据源出口。
            cache: 字典缓存域（与取数共用同一实例；缺省进程内实现）。
        """
        self._outlet = outlet
        self._cache = cache or MemoryDictCacheRegion()

    async def translate(self, query: DictTranslateQuery) -> ConcurrentStableDict[int, str]:
        """按条目 id 批量翻译为 label（当前 locale；未命中不占位）。

        与取数**共用同一份缓存域**：先读 id 子集缓存，只对缺失 id 回源，回源后按缺失集合回填——
        表单列表页几十个 id 的展示不再整表拉取（原实现每次全量 `load`）。

        Args:
            query: 翻译参数对象。

        Returns:
            ConcurrentStableDict[int, str]: 条目 id → label（仅命中项；未登记 / 停用返回空）。
        """
        provider = self._outlet.provider_for(query.data_source_key)
        if provider is None:
            return ConcurrentStableDict()
        locale = query.locale or DEFAULT_LOCALE
        ids = ConcurrentStableList(dict.fromkeys(query.ids))
        if not ids:
            return ConcurrentStableDict()
        tenant = current_tenant_id_str()
        cached = await self._cache.aid_subset(tenant, locale, query.data_source_key, ids)
        missing = ConcurrentStableList(item_id for item_id in ids if item_id not in cached)
        if not missing:
            return cached
        loaded = await _load_rows(provider, query.data_source_key, locale)
        if loaded is None:
            return cached
        wanted = set(missing)
        fetched: ConcurrentStableDict[int, str] = ConcurrentStableDict()
        for item in loaded:
            if item.id in wanted:
                fetched.set(item.id, item.label)
        if fetched:
            await self._cache.aset_id_subset(tenant, locale, query.data_source_key, fetched)
        merged: ConcurrentStableDict[int, str] = ConcurrentStableDict(cached)
        merged.update(fetched.items())
        return ConcurrentStableDict((item_id, merged[item_id]) for item_id in ids if item_id in merged)


_PROVIDERS: ConcurrentStableDict[str, BaseGenericDataSource] = ConcurrentStableDict()
"""平台内建数据源提供者注册表（各服务在装配期注入，口径同目录读取器 / 权限实现注册）。"""


def register_data_source(provider: BaseGenericDataSource) -> None:
    """登记平台内建数据源提供者（按 `data_source` 覆盖写）。

    Args:
        provider: 数据源提供者实例。
    """
    _PROVIDERS.set(provider.data_source, provider)


def registered_data_sources() -> ConcurrentStableDict[str, BaseGenericDataSource]:
    """取已登记的平台内建数据源提供者（副本）。

    Returns:
        ConcurrentStableDict[str, BaseGenericDataSource]: `data_source` → 提供者。
    """
    return ConcurrentStableDict(_PROVIDERS)


def build_data_source_outlet() -> DataSourceOutlet:
    """按构建期清单（+ 已注入提供者）构造数据源出口（应用装配期入口）。

    Returns:
        DataSourceOutlet: 数据源出口。
    """
    return DataSourceOutlet(DataSourceRegistry(data_source_records_view()), registered_data_sources())
