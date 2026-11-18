"""租户启用语言清单：只取启用、归一、默认语言优先、空清单回退出厂默认（12_01）。"""

from __future__ import annotations

from bms_core.i18n.base import DEFAULT_LOCALE
from bms_core.models.platform.i18n import SysI18nLocale
from bms_core.repositories.help_locale import load_help_default_locale, load_help_locales
from tests_support.help import memory_locale_session


def _locale(code: str, *, is_default: bool = False, status: str = "enabled") -> SysI18nLocale:
    """构造语言清单行（form_key 按语言唯一）。

    Args:
        code: 语言标识。
        is_default: 是否默认语言。
        status: 状态。

    Returns:
        SysI18nLocale: 语言行。
    """
    return SysI18nLocale(form_key=f"loc_{code.replace('-', '_')}", code=code, is_default=is_default, status=status)


async def test_load_locales_filters_and_orders() -> None:
    """只取启用语言；默认语言在首位；大小写归一；去重。"""
    async with memory_locale_session() as session:
        session.add_all(
            [
                _locale("zh-CN", is_default=True),
                _locale("en-US", status="disabled"),
                _locale("fr-FR"),
                _locale("zh-cn"),
            ]
        )
        await session.commit()
        assert await load_help_default_locale(session) == "zh-CN"
        assert list(await load_help_locales(session)) == ["zh-CN", "fr-FR"]


async def test_load_locales_falls_back_when_empty() -> None:
    """清单为空（或全停用）时回退出厂默认语言。"""
    async with memory_locale_session() as session:
        session.add(_locale("en-US", status="disabled"))
        await session.commit()
        assert await load_help_default_locale(session) == DEFAULT_LOCALE
        assert list(await load_help_locales(session)) == [DEFAULT_LOCALE]
