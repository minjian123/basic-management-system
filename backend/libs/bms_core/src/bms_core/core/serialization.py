"""core 层稳定序列化：统一 JSON 序列化参数（稳定序、中文不转义、降级 str）。

- 全项目稳定序输出复用本模块，避免各基类 / 封装重复 JSON 参数。
- 将来统一日期 / Decimal 等口径只改此处（单点）。
- **基座集合类识别**（08_02）：按 `collections.abc` 只读面（`Mapping` / `Sequence` / `Set`）识别并发集合，
  `stringify_ids` 同型重组、`stable_json_dumps` 前置规整为内置容器；**不反向 import `core.collections` /
  `core.concurrent`**（规避循环导入），`str` / `bytes` 不参与识别。
"""

import json
from collections.abc import Callable, Iterable, Mapping, Sequence, Set
from typing import cast

_ID_KEYS = ("id",)


def is_id_key(key: object) -> bool:
    """是否 ID 键（`id` 本身，或以 `_id` 结尾的字符串键）。

    唯一判定来源：运行时 `stringify_ids`（ID 值字符串化）与 JSON Schema 侧（`id` / `*_id`
    字段的输出类型标为字符串）共用本函数，避免两处规则漂移。

    Args:
        key: 待判定键（映射键名或字段名）。

    Returns:
        bool: 是 ID 键 True。
    """
    return isinstance(key, str) and (key in _ID_KEYS or key.endswith("_id"))


def rebuild_mapping(original: object, items: Iterable[tuple[object, object]]) -> object:
    """按原映射形态重建（内置 `dict` 保内置，基座映射类同型重组）。

    Args:
        original: 原映射实例（取其类型）。
        items: 转换后的键值对。

    Returns:
        object: 同型实例（类型不可按可迭代构造时回退内置 `dict`）。
    """
    pairs = list(items)
    if type(original) is dict:
        return dict(pairs)
    factory = cast("Callable[[Iterable[tuple[object, object]]], object]", type(original))
    try:
        return factory(pairs)
    except TypeError:
        return dict(pairs)


def rebuild_sequence(original: object, items: Iterable[object]) -> object:
    """按原序列 / 集合形态重建（`list` / `tuple` 按列表输出，基座集合类同型重组）。

    Args:
        original: 原序列 / 集合实例（取其类型）。
        items: 转换后的元素。

    Returns:
        object: 同型实例（类型不可按可迭代构造时回退内置 `list`）。
    """
    materialized = list(items)
    if type(original) in (list, tuple):
        return materialized
    factory = cast("Callable[[Iterable[object]], object]", type(original))
    try:
        return factory(materialized)
    except TypeError:
        return materialized


def _stringify_entry(key: object, item: object) -> tuple[object, object]:
    """单个键值对转换（`id` / `*_id` 的整型值转字符串，其余递归 `stringify_ids`）。

    Args:
        key: 键。
        item: 值。

    Returns:
        tuple[object, object]: 转换后的键值对。
    """
    id_key = is_id_key(key)
    return key, str(item) if id_key and type(item) is int else stringify_ids(item)


def stringify_ids(value: object) -> object:
    """递归把 `id` / `*_id` 的整型值转字符串（雪花 ID 防 JS 精度丢失）。

    按 `collections.abc` 只读面识别映射 / 序列 / 集合（含基座并发集合类并**同型重组**），
    `str` / `bytes` / `bytearray` 不参与识别；内置 `set` / `frozenset` 保持原样（其元素为可哈希标量）。

    Args:
        value: 待转换的序列化结果。

    Returns:
        object: 转换后的结果。
    """
    if isinstance(value, Mapping):
        mapping = cast("Mapping[object, object]", value)
        return rebuild_mapping(mapping, (_stringify_entry(key, item) for key, item in mapping.items()))
    if isinstance(value, (str, bytes, bytearray)):
        return value
    if isinstance(value, Sequence):
        sequence = cast("Sequence[object]", value)
        return rebuild_sequence(sequence, (stringify_ids(item) for item in sequence))
    if isinstance(value, Set):
        members = cast("Set[object]", value)
        if type(members) in (set, frozenset):
            return members
        return rebuild_sequence(members, (stringify_ids(item) for item in members))
    return value


def normalize_collections(value: object) -> object:
    """把基座集合类**前置规整**为内置容器（JSON 载荷），递归处理嵌套。

    内置 `set` / `frozenset` 保持原样（沿用既有 `default=str` 降级口径）；`str` / `bytes` 不参与识别。

    Args:
        value: 待规整的值。

    Returns:
        object: 仅含内置容器与标量的 JSON 载荷。
    """
    if isinstance(value, Mapping):
        mapping = cast("Mapping[object, object]", value)
        return {key: normalize_collections(item) for key, item in mapping.items()}
    if isinstance(value, (str, bytes, bytearray)):
        return value
    if isinstance(value, (list, tuple)):
        sequence = cast("Sequence[object]", value)
        return [normalize_collections(item) for item in sequence]
    if isinstance(value, (set, frozenset)):
        return cast("object", value)
    if isinstance(value, (Sequence, Set)):
        collection = cast("Iterable[object]", value)
        return [normalize_collections(item) for item in collection]
    return value


def stable_json_dumps(value: object, *, sort_keys: bool = True) -> str:
    """稳定 JSON 序列化（基座集合类前置规整为内置容器）。

    Args:
        value: 待序列化对象。
        sort_keys: 是否按键排序（默认 True，保证输出稳定）。

    Returns:
        str: JSON 字符串（ensure_ascii=False，不可序列化值降级 str）。
    """
    return json.dumps(normalize_collections(value), ensure_ascii=False, sort_keys=sort_keys, default=str)


def stable_json_loads(raw: bytes | str) -> object:
    """JSON 反序列化（bytes 自动解码）。

    Args:
        raw: Redis / 文件读取的原始值。

    Returns:
        object: 反序列化结果。
    """
    return json.loads(raw.decode() if isinstance(raw, bytes) else raw)
