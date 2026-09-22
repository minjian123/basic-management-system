"""core 层稳定序列化：统一 JSON 序列化参数（稳定序、中文不转义、降级 str）。

- 全项目稳定序输出复用本模块，避免各基类 / 封装重复 JSON 参数。
- 将来统一日期 / Decimal 等口径只改此处（单点）。
"""

import json
from collections.abc import Iterable
from typing import cast

_ID_KEYS = ("id",)


def stringify_ids(value: object) -> object:
    """递归把 `id` / `*_id` 的整型值转字符串（雪花 ID 防 JS 精度丢失）。

    Args:
        value: 待转换的序列化结果。

    Returns:
        object: 转换后的结果。
    """
    if isinstance(value, dict):
        mapping = cast("dict[object, object]", value)
        result: dict[object, object] = {}
        for key, item in mapping.items():
            is_id_key = isinstance(key, str) and (key in _ID_KEYS or key.endswith("_id"))
            if is_id_key and type(item) is int:
                result[key] = str(item)
            else:
                result[key] = stringify_ids(item)
        return result
    if isinstance(value, (list, tuple)):
        return [stringify_ids(item) for item in cast("Iterable[object]", value)]
    return value


def stable_json_dumps(value: object, *, sort_keys: bool = True) -> str:
    """稳定 JSON 序列化。

    Args:
        value: 待序列化对象。
        sort_keys: 是否按键排序（默认 True，保证输出稳定）。

    Returns:
        str: JSON 字符串（ensure_ascii=False，不可序列化值降级 str）。
    """
    return json.dumps(value, ensure_ascii=False, sort_keys=sort_keys, default=str)


def stable_json_loads(raw: bytes | str) -> object:
    """JSON 反序列化（bytes 自动解码）。

    Args:
        raw: Redis / 文件读取的原始值。

    Returns:
        object: 反序列化结果。
    """
    return json.loads(raw.decode() if isinstance(raw, bytes) else raw)
