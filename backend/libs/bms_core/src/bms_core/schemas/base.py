"""schemas 层基类：Pydantic 公共配置、ID 序列化与敏感字段掩码口径。"""

from collections.abc import Callable
from typing import Any, ClassVar, cast

from pydantic import BaseModel, ConfigDict, SerializationInfo, model_serializer

from bms_core.core.base import BaseObject
from bms_core.core.context import get_current_masker
from bms_core.core.serialization import stringify_ids


def _apply_masking(masked_fields: frozenset[str], data: object) -> object:
    """按当前掩码器掩码敏感字段。

    未注入掩码器（`current_masker` 为 None）/ 无敏感字段声明 / 序列化结果非字典时**原样返回**
    （占位期行为与既有完全一致）。

    Args:
        masked_fields: 需掩码的字段集合。
        data: 序列化结果。

    Returns:
        object: 掩码后的结果。
    """
    masker = get_current_masker()
    if masker is None or not masked_fields or not isinstance(data, dict):
        return data
    fields = cast("dict[str, object]", data)
    for field in masked_fields:
        if field in fields:
            fields[field] = masker.mask(field, fields[field])
    return fields


class BaseSchema(BaseModel, BaseObject):
    """Pydantic 模型基类：请求/响应模型统一继承。

    - from_attributes：允许 ORM/实体对象直接校验（响应模型使用）
    - str_strip_whitespace：字符串字段自动去除首尾空白
    - 序列化：继承 `BaseObject`（声明字段优先）；统一把 `id` / `*_id` 按字符串输出（JS 安全整数）
    - 敏感字段：类属性 `masked_fields` 声明的字段在序列化时经当前掩码器掩码（未注入掩码器时直通）
    """

    model_config = ConfigDict(from_attributes=True, str_strip_whitespace=True)

    masked_fields: ClassVar[frozenset[str]] = frozenset()
    """需掩码的敏感字段（默认空集＝不掩码）；真实规则随性能与安全阶段回补。"""

    @model_serializer(mode="wrap")
    def _serialize_ids(self, serializer: Callable[..., Any], info: SerializationInfo) -> Any:
        """序列化包装：字段 ID 值字符串化 + 敏感字段掩码。

        Args:
            serializer: Pydantic 序列化器。
            info: 序列化信息。

        Returns:
            Any: 序列化结果。
        """
        del info
        return _apply_masking(type(self).masked_fields, stringify_ids(serializer(self)))
