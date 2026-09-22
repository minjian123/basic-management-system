"""游标契约：keyset 游标载荷与编解码（base64url JSON）。

- 游标 = `base64url(JSON{version, specs, values, id})`：`specs` 为生效排序规格指纹
  （字段 + 方向），`values` 为末行排序键值，`id` 为主键（键集比较的兜底键）；
- 规格指纹与本次请求的生效排序不一致 → 拒绝（防跨排序复用游标导致漏行 / 重行）；
- 值编解码：`None` / `bool` / `int` / `float` / `str` / `datetime` / `date`（后两者带类型标记）；
  其余类型明确拒绝（`ParamError`），不静默降级；
- 非法游标（编码 / JSON / 版本 / 载荷形态）一律 `ParamError`（10001），不静默回落首页。
"""

import base64
import binascii
import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from typing import cast

from bms_core.core.base import BaseObject
from bms_core.core.exceptions import ParamError
from bms_core.schemas.sorting import SortDirection, SortSpec

CURSOR_VERSION = 1
"""游标载荷版本（结构变更时递增，旧游标自然失效）。"""

_TYPE_KEY = "__type__"
_DATETIME_TYPE = "datetime"
_DATE_TYPE = "date"


@dataclass(frozen=True)
class CursorPayload(BaseObject):
    """游标载荷（排序规格指纹 + 末行排序键值 + 主键）。"""

    specs: tuple[tuple[str, str], ...]
    """生效排序规格指纹（`(字段, 方向)` 序列）。"""

    values: tuple[object, ...]
    """末行排序键值（与规格一一对应）。"""

    item_id: int
    """末行主键（键集比较兜底键）。"""

    def matches(self, sort: Sequence[SortSpec]) -> bool:
        """规格指纹是否与生效排序一致。

        Args:
            sort: 本次请求的生效排序规格。

        Returns:
            bool: 一致 True。
        """
        return self.specs == spec_fingerprint(sort)


def spec_fingerprint(sort: Sequence[SortSpec]) -> tuple[tuple[str, str], ...]:
    """排序规格指纹（字段 + 方向）。

    Args:
        sort: 生效排序规格。

    Returns:
        tuple[tuple[str, str], ...]: 指纹元组。
    """
    return tuple((spec.field, spec.direction.value) for spec in sort)


def encode_cursor(sort: Sequence[SortSpec], values: Sequence[object], item_id: int) -> str:
    """编码 keyset 游标。

    Args:
        sort: 生效排序规格。
        values: 末行排序键值（与规格一一对应）。
        item_id: 末行主键。

    Returns:
        str: 游标令牌（base64url，无填充）。

    Raises:
        ParamError: 排序键值类型不支持（如 `Decimal`）。
    """
    payload = {
        "version": CURSOR_VERSION,
        "specs": [[field, direction] for field, direction in spec_fingerprint(sort)],
        "values": [_encode_value(value) for value in values],
        "id": item_id,
    }
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_cursor(token: str) -> CursorPayload:
    """解码 keyset 游标（不做规格比对，比对见 `decode_cursor_for`）。

    Args:
        token: 游标令牌。

    Returns:
        CursorPayload: 载荷。

    Raises:
        ParamError: 编码 / JSON / 版本 / 载荷形态 / 值类型非法。
    """
    padded = token + "=" * (-len(token) % 4)
    try:
        decoded = base64.urlsafe_b64decode(padded.encode("ascii"))
        raw = json.loads(decoded.decode("utf-8"))
    except (binascii.Error, UnicodeDecodeError, ValueError) as exc:
        raise ParamError("游标格式非法（请从首页重新分页）") from exc
    if not isinstance(raw, dict):
        raise ParamError("游标载荷非法（应为对象）")
    mapping = cast("dict[str, object]", raw)
    if mapping.get("version") != CURSOR_VERSION:
        raise ParamError("游标版本不支持（请从首页重新分页）")
    specs_raw = mapping.get("specs")
    values_raw = mapping.get("values")
    item_id = mapping.get("id")
    if not isinstance(specs_raw, list) or not isinstance(values_raw, list) or not isinstance(item_id, int):
        raise ParamError("游标载荷不完整")
    specs = tuple(_decode_spec(item) for item in cast("list[object]", specs_raw))
    raw_values = cast("list[object]", values_raw)
    if len(specs) != len(raw_values):
        raise ParamError("游标排序键数量与规格不一致")
    values = tuple(_decode_value(item) for item in raw_values)
    return CursorPayload(specs=specs, values=values, item_id=item_id)


def decode_cursor_for(token: str, sort: Sequence[SortSpec]) -> CursorPayload:
    """解码游标并校验与本次生效排序一致。

    Args:
        token: 游标令牌。
        sort: 本次请求的生效排序规格。

    Returns:
        CursorPayload: 载荷。

    Raises:
        ParamError: 载荷非法或规格不一致。
    """
    payload = decode_cursor(token)
    if not payload.matches(sort):
        raise ParamError("游标与当前排序不一致（请从首页重新分页）")
    return payload


def _decode_spec(raw: object) -> tuple[str, str]:
    """解析单条排序规格指纹。

    Args:
        raw: 原始规格项。

    Returns:
        tuple[str, str]: `(字段, 方向)`。

    Raises:
        ParamError: 形态非法。
    """
    if not isinstance(raw, list):
        raise ParamError("游标排序规格非法")
    parts = cast("list[object]", raw)
    if len(parts) != 2 or not all(isinstance(part, str) for part in parts):
        raise ParamError("游标排序规格非法")
    field, direction = (str(parts[0]), str(parts[1]))
    if direction not in (SortDirection.ASC.value, SortDirection.DESC.value):
        raise ParamError(f"游标排序方向非法：{direction}")
    return field, direction


def _encode_value(value: object) -> object:
    """编码排序键值（时间类带类型标记）。

    Args:
        value: 排序键值。

    Returns:
        object: 可 JSON 序列化的值。

    Raises:
        ParamError: 值类型不支持。
    """
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, datetime):
        return {_TYPE_KEY: _DATETIME_TYPE, "value": value.isoformat()}
    if isinstance(value, date):
        return {_TYPE_KEY: _DATE_TYPE, "value": value.isoformat()}
    raise ParamError(f"游标排序键类型不支持：{type(value).__name__}")


def _decode_value(raw: object) -> object:
    """解码排序键值（还原时间类标记）。

    Args:
        raw: 载荷中的值。

    Returns:
        object: 还原后的值。

    Raises:
        ParamError: 值类型 / 标记非法。
    """
    if raw is None or isinstance(raw, (bool, int, float, str)):
        return raw
    if isinstance(raw, dict):
        mapping = cast("dict[str, object]", raw)
        kind = mapping.get(_TYPE_KEY)
        text = str(mapping.get("value", ""))
        try:
            if kind == _DATETIME_TYPE:
                return datetime.fromisoformat(text)
            if kind == _DATE_TYPE:
                return date.fromisoformat(text)
        except ValueError as exc:
            raise ParamError(f"游标排序键值非法：{text}") from exc
        raise ParamError(f"游标排序键类型标记非法：{kind}")
    raise ParamError(f"游标排序键值类型非法：{type(raw).__name__}")
