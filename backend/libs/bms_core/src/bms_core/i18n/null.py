"""i18n 能力域缺省实现（Null Object）：占位返回、无副作用（02-3 自 bms_core.i18n.base.py 迁入）。"""

from collections.abc import Mapping

from bms_core.core.capability import BaseNullObject
from bms_core.i18n.base import DEFAULT_LOCALE, BaseTranslator

__all__ = [
    "NullTranslator",
]


class NullTranslator(BaseTranslator, BaseNullObject):
    """占位翻译器：原样返回 key（不翻译），语言解析取默认，语言包为空。"""

    async def translate(
        self, key: str, *, locale: str | None = None, params: Mapping[str, object] | None = None
    ) -> str:
        """原样返回 key。

        Args:
            key: 文案 key（占位原样返回）。
            locale: 语言（占位忽略）。
            params: 插值参数（占位忽略）。

        Returns:
            str: 原样 key。
        """
        return key

    async def load_messages(self, locale: str) -> Mapping[str, str]:
        """返回空语言包。

        Args:
            locale: 语言（占位忽略）。

        Returns:
            Mapping[str, str]: 空映射。
        """
        return {}

    def resolve_locale(self, accept_language: str | None = None) -> str:
        """返回默认语言。

        Args:
            accept_language: 请求头（占位忽略）。

        Returns:
            str: `DEFAULT_LOCALE`。
        """
        return DEFAULT_LOCALE
