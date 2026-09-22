"""fieldtype 能力域缺省实现（Null Object）：占位返回、无副作用（02-3 自 bms_core.fieldtype.base.py 迁入）。"""

from collections.abc import Mapping

from bms_core.core.capability import BaseNullObject
from bms_core.fieldtype.base import NULL_COLUMN_TYPE, BaseFieldType, BaseFieldTypeRegistry

__all__ = [
    "NullFieldTypeRegistry",
]


class NullFieldTypeRegistry(BaseFieldTypeRegistry, BaseNullObject):
    """占位注册表：登记与解析继承公共实现（唯一性拒重）；校验恒定通过、类型映射固定返回（不校验 / 不映射）。"""

    @classmethod
    def _provider_key(cls, provider: BaseFieldType) -> str:
        """注册项键：字段类型 `key`。

        Args:
            provider: 字段类型提供者。

        Returns:
            str: 字段类型标识。
        """
        return provider.key

    def validate(
        self, field_type: str, value: object, *, options: Mapping[str, object] | None = None
    ) -> tuple[str, ...]:
        """恒定通过（占位不校验）。

        Args:
            field_type: 字段类型标识（占位忽略）。
            value: 字段值（占位忽略）。
            options: 字段选项（占位忽略）。

        Returns:
            tuple[str, ...]: 空违规元组。
        """
        return ()

    def column_type(self, field_type: str, dialect: str) -> str:
        """固定返回占位列类型（占位不映射）。

        Args:
            field_type: 字段类型标识（占位忽略）。
            dialect: 方言（占位忽略）。

        Returns:
            str: `NULL_COLUMN_TYPE`。
        """
        return NULL_COLUMN_TYPE
