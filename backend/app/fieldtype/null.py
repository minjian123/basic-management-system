"""fieldtype 能力域缺省实现（Null Object）：占位返回、无副作用（02-3 自 app.fieldtype.base.py 迁入）。"""

from collections.abc import Mapping

from app.core.capability import BaseNullObject
from app.fieldtype.base import NULL_COLUMN_TYPE, BaseFieldType, BaseFieldTypeRegistry

__all__ = [
    "NullFieldTypeRegistry",
]


class NullFieldTypeRegistry(BaseFieldTypeRegistry, BaseNullObject):
    """占位注册表：注册空操作、无字段类型；校验恒定通过、类型映射固定返回（不校验 / 不映射）。"""

    def register(self, provider: BaseFieldType) -> None:
        """空操作（占位不注册）。

        Args:
            provider: 字段类型提供者（占位忽略）。
        """

    def get(self, key: str) -> BaseFieldType | None:
        """无字段类型。

        Args:
            key: 字段类型标识（占位忽略）。

        Returns:
            BaseFieldType | None: None。
        """
        return None

    def keys(self) -> tuple[str, ...]:
        """空字段类型清单。

        Returns:
            tuple[str, ...]: 空元组。
        """
        return ()

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
