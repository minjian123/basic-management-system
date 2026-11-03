"""语言清单能力域测试（Kiwi 2404）：纯解析 / 快照 / 默认语言 / RTL / 归一。"""

import pytest

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.i18n.base import DEFAULT_LOCALE
from bms_core.i18n.locale import LOCALE_DISABLED, LocaleInfo, match_locale
from bms_core.i18n.registry import SEED_DEFAULT_LOCALE, SEED_LOCALES, seed_locale_infos
from bms_core.i18n.registry_null import NullLocaleRegistry

pytestmark = [pytest.mark.kiwi_id(2404)]


def test_match_locale_prefers_exact_then_prefix() -> None:
    """精确命中优先、其次主语言前缀、最后默认语言。"""
    supported = ConcurrentStableList(("zh-CN", "en-US", "ar-SA"))
    assert match_locale("en-US,en;q=0.9", supported, "zh-CN") == "en-US"
    assert match_locale("en,zh-CN;q=0.5", supported, "zh-CN") == "en-US"
    assert match_locale("ZH-cn", supported, "zh-CN") == "zh-CN"
    assert match_locale("fr-FR,de;q=0.8", supported, "zh-CN") == "zh-CN"
    assert match_locale("", supported, "zh-CN") == "zh-CN"
    assert match_locale(None, supported, "zh-CN") == "zh-CN"
    assert match_locale(" ,  ;q=0.1", supported, "zh-CN") == "zh-CN"


def test_locale_info_enabled_flag() -> None:
    """`enabled` 派生自状态。"""
    assert LocaleInfo(code="zh-CN").enabled is True
    assert LocaleInfo(code="zh-CN", status=LOCALE_DISABLED).enabled is False


def test_seed_locales_shape() -> None:
    """种子清单：`zh-CN` 默认、英文非默认。"""
    assert SEED_DEFAULT_LOCALE == DEFAULT_LOCALE
    assert SEED_LOCALES[0][0] == "zh-CN"
    infos = seed_locale_infos()
    assert [item.code for item in infos] == ["zh-CN", "en-US"]
    assert [item.is_default for item in infos] == [True, False]


async def test_null_registry_contract() -> None:
    """占位实现：种子清单 / 默认语言 / RTL 否 / 解析回退 / 归一。"""
    registry = NullLocaleRegistry()
    all_locales = await registry.list_locales()
    enabled = await registry.list_locales(enabled_only=True)
    assert [item.code for item in all_locales] == ["zh-CN", "en-US"]
    assert [item.code for item in enabled] == ["zh-CN", "en-US"]
    assert registry.default_locale() == "zh-CN"
    assert registry.is_rtl("zh-CN") is False
    assert registry.is_rtl("ar-SA") is False
    assert registry.resolve_locale("en-US") == "en-US"
    assert registry.resolve_locale("fr") == "zh-CN"
    assert await registry.ensure_supported("EN-us") == "en-US"
    assert await registry.ensure_supported("fr-FR") == "zh-CN"
    assert await registry.ensure_supported(None) == "zh-CN"
    await registry.refresh()
    assert registry.snapshot()[0].code == "zh-CN"


async def test_snapshot_replace_sorts_and_derives_default() -> None:
    """快照替换：按 `sort` 排序、默认语言取标记、无标记取首个启用。"""
    registry = NullLocaleRegistry()
    registry._replace_snapshot(  # pyright: ignore[reportPrivateUsage]
        ConcurrentStableList(
            (
                LocaleInfo(code="en-US", sort=20, is_default=True),
                LocaleInfo(code="ar-SA", sort=10, rtl=True, status=LOCALE_DISABLED),
                LocaleInfo(code="zh-CN", sort=5),
            )
        )
    )
    assert [item.code for item in registry.snapshot()] == ["zh-CN", "ar-SA", "en-US"]
    assert registry.default_locale() == "en-US"
    assert registry.is_rtl("AR-sa") is True
    # 停用语言不参与解析 → 回退默认语言（en-US）
    assert registry.resolve_locale("ar-SA") == "en-US"

    registry._replace_snapshot(  # pyright: ignore[reportPrivateUsage]
        ConcurrentStableList(
            (
                LocaleInfo(code="fr-FR", sort=1),
                LocaleInfo(code="de-DE", sort=2, status=LOCALE_DISABLED),
            )
        )
    )
    assert registry.default_locale() == "fr-FR"


async def test_empty_snapshot_falls_back_to_seed() -> None:
    """空快照回退种子清单与默认语言。"""
    registry = NullLocaleRegistry()
    registry._snapshot = ConcurrentStableList()  # pyright: ignore[reportPrivateUsage]
    registry._default = ""  # pyright: ignore[reportPrivateUsage]
    assert [item.code for item in registry.snapshot()] == ["zh-CN", "en-US"]
    assert registry.default_locale() == "zh-CN"
    assert registry.resolve_locale("en-US") == "en-US"
