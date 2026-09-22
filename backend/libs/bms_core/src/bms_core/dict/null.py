"""dict 能力域缺省实现（Null Object）：固定 / 批量占位数据、原样翻译与空缓存，不连库、不连 Redis。"""

from collections.abc import Mapping

from bms_core.core.capability import BaseNullObject
from bms_core.dict.base import (
    NULL_DICT_VERSION,
    BaseDictSource,
    BaseDictTranslator,
    DictBatchQuery,
    DictBatchResult,
    DictCacheRegion,
    DictItem,
    DictQuery,
    DictTranslateQuery,
    DictTypeResult,
)

__all__ = [
    "NullDictCacheRegion",
    "NullDictSource",
    "NullDictTranslator",
]

_TRANSLATE_PREFIX = "占位"
"""占位翻译前缀（`NullDictTranslator` 依此生成标签，便于断言）。"""


def _placeholder_items(dict_type: str) -> tuple[DictItem, ...]:
    """构造类型占位条目（两条：顶层 + 其子级，供级联断言）。

    Args:
        dict_type: 字典类型码。

    Returns:
        tuple[DictItem, ...]: 固定两条占位条目。
    """
    return (
        DictItem(
            value=f"{dict_type}-1",
            label=f"占位{dict_type}1",
            code=f"{dict_type}_1",
            parent_id=None,
            sort=0,
            status="enabled",
            color=None,
        ),
        DictItem(
            value=f"{dict_type}-2",
            label=f"占位{dict_type}2",
            code=f"{dict_type}_2",
            parent_id=f"{dict_type}-1",
            sort=1,
            status="enabled",
            color="#1677ff",
        ),
    )


def _apply_filters(items: tuple[DictItem, ...], query: DictQuery) -> tuple[DictItem, ...]:
    """按查询条件过滤占位条目（按值子集 / 关键字 / 级联父值）。

    Args:
        items: 占位条目。
        query: 单类型取数参数。

    Returns:
        tuple[DictItem, ...]: 过滤后的条目。
    """
    result = items
    if query.values is not None:
        result = tuple(item for item in result if item.value in query.values)
    if query.keyword:
        result = tuple(item for item in result if query.keyword in item.label or query.keyword in item.value)
    if query.parent_id is not None:
        result = tuple(item for item in result if item.parent_id == query.parent_id)
    return result


def _type_result(dict_type: str) -> DictTypeResult:
    """构造单类型占位结果（两条固定条目）。

    Args:
        dict_type: 字典类型码。

    Returns:
        DictTypeResult: 固定两条条目的占位结果。
    """
    items = _placeholder_items(dict_type)
    return DictTypeResult(version=NULL_DICT_VERSION, items=items, has_more=False, total=len(items))


class NullDictSource(BaseDictSource, BaseNullObject):
    """占位字典取数：固定两条条目、版本一致返空、按条件过滤；不连库、不做真实缓存。"""

    async def by_type(self, query: DictQuery) -> DictTypeResult:
        """按类型取字典（占位固定两条）。

        Args:
            query: 单类型取数参数。

        Returns:
            DictTypeResult: 版本一致 `items=None`；否则固定 / 过滤后的条目集。
        """
        current = NULL_DICT_VERSION
        if query.version == current:
            return DictTypeResult(version=current, items=None, has_more=False, total=0)

        items = _apply_filters(_placeholder_items(query.dict_type), query)
        total = len(items)
        has_more = query.limit is not None and total > query.limit
        if query.limit is not None:
            items = items[: query.limit]
        return DictTypeResult(version=current, items=items, has_more=has_more, total=total)

    async def batch(self, query: DictBatchQuery) -> DictBatchResult:
        """批量取字典（占位按类型固定两条；版本一致各类型返 None）。

        Args:
            query: 批量取数参数。

        Returns:
            DictBatchResult: 批量结果。
        """
        if query.version == NULL_DICT_VERSION:
            return DictBatchResult(version=NULL_DICT_VERSION, items={name: None for name in query.types})
        return DictBatchResult(
            version=NULL_DICT_VERSION,
            items={name: _type_result(name) for name in query.types},
        )


class NullDictTranslator(BaseDictTranslator, BaseNullObject):
    """占位字典翻译：按 value 原样生成占位标签；不查缓存、不查库。"""

    async def translate(self, query: DictTranslateQuery) -> Mapping[str, str]:
        """批量翻译（占位）。

        Args:
            query: 翻译参数。

        Returns:
            Mapping[str, str]: value → 占位标签。
        """
        return {value: f"{_TRANSLATE_PREFIX}{query.dict_type}:{value}" for value in query.values}


class NullDictCacheRegion(DictCacheRegion, BaseNullObject):
    """占位字典缓存域：读恒未命中、写 / 删空操作、全局版本号恒 0（不连 Redis、不做 L1）。"""

    def get(self, key: str) -> object | None:
        """读缓存（占位恒未命中）。

        Args:
            key: 缓存 key（占位忽略）。

        Returns:
            object | None: None。
        """
        return None

    def set(self, key: str, value: object, ttl: int | None = None) -> None:
        """写缓存（占位空操作）。

        Args:
            key: 缓存 key（占位忽略）。
            value: 缓存值（占位忽略）。
            ttl: 有效期（占位忽略）。
        """

    def delete(self, key: str) -> bool:
        """删缓存（占位恒不存在）。

        Args:
            key: 缓存 key（占位忽略）。

        Returns:
            bool: False。
        """
        return False

    def get_global_version(self) -> int:
        """取全局版本号（占位恒 0）。

        Returns:
            int: 0。
        """
        return 0
