"""masking 能力域缺省实现（Null Object）：占位返回、无副作用（02-3 自 bms_core.masking.base.py 迁入）。"""

from bms_core.core.capability import BaseNullObject
from bms_core.masking.base import BaseMasker

__all__ = [
    "NullMasker",
]


class NullMasker(BaseMasker, BaseNullObject):
    """占位脱敏：原样返回（不掩码、不解密，未接入真实规则时使用）。"""

    def mask(self, field: str, value: object) -> object:
        """原样返回（占位不掩码）。

        Args:
            field: 字段名（占位不区分）。
            value: 原始值。

        Returns:
            object: 传入值本身。
        """
        return value

    def reveal(self, field: str, value: object) -> object:
        """原样返回（占位不解密）。

        Args:
            field: 字段名（占位不区分）。
            value: 存储值。

        Returns:
            object: 传入值本身。
        """
        return value
