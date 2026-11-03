"""翻译实现测试（Kiwi 2404）：取词回退链 / 插值 / 语言包缓存。

`_load`（回源库）以打桩替代：本文件只验证**回退与缓存语义**，真库读写由种子与集成用例覆盖。
"""

from typing import cast

import pytest

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.db.registry import EngineRegistry
from bms_core.i18n.cache import MemoryI18nCacheRegion
from bms_core.i18n.db import DbTranslator
from bms_core.i18n.null import NullLocaleRegistry

pytestmark = [pytest.mark.kiwi_id(2404)]

_ZH = "zh-CN"
_EN = "en-US"


def _translator(
    monkeypatch: pytest.MonkeyPatch,
    data: ConcurrentStableDict[str, ConcurrentStableDict[str, str] | None],
    calls: ConcurrentStableList[str],
) -> DbTranslator:
    """构造打桩回源的翻译器。

    Args:
        monkeypatch: pytest 打桩器。
        data: 语言 → 文案映射（None 模拟回源异常）。
        calls: 回源调用记录（断言缓存生效用）。

    Returns:
        DbTranslator: 翻译器实例。
    """
    translator = DbTranslator(
        engines=cast("EngineRegistry", object()),
        registry=NullLocaleRegistry(),
        cache=MemoryI18nCacheRegion(),
    )

    async def fake_load(locale: str) -> ConcurrentStableDict[str, str] | None:
        calls.append(locale)
        return data.get(locale)

    monkeypatch.setattr(translator, "_load", fake_load)
    return translator


def _messages(**values: str) -> ConcurrentStableDict[str, str]:
    """构造文案映射。

    Args:
        **values: key → 文案（点号在关键字参数里不可用，测试用下划线并在内部还原）。

    Returns:
        ConcurrentStableDict[str, str]: 文案映射。
    """
    result: ConcurrentStableDict[str, str] = ConcurrentStableDict()
    for key, value in values.items():
        result.set(key.replace("__", "."), value)
    return result


async def test_translate_uses_target_then_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """命中当前语言 → 插值；缺当前语言 → 回退默认语言；两语言都缺 → 返回 key。"""
    data: ConcurrentStableDict[str, ConcurrentStableDict[str, str] | None] = ConcurrentStableDict()
    data.set(_ZH, _messages(common__confirm="确认", common__greet="你好 {name}"))
    data.set(_EN, _messages(common__confirm="Confirm"))
    calls: ConcurrentStableList[str] = ConcurrentStableList()
    translator = _translator(monkeypatch, data, calls)

    assert await translator.translate("common.confirm", locale=_EN) == "Confirm"
    assert await translator.translate("common.greet", locale=_EN, params=ConcurrentStableDict({"name": "小明"})) == (
        "你好 小明"
    )
    assert await translator.translate("common.greet", locale=_EN) == "你好 {name}"
    assert await translator.translate("common.missing", locale=_EN) == "common.missing"
    assert translator.resolve_locale("en-US") == _EN


async def test_translate_default_locale_and_empty_params(monkeypatch: pytest.MonkeyPatch) -> None:
    """未指定语言走默认语言；无参数时不插值。"""
    data: ConcurrentStableDict[str, ConcurrentStableDict[str, str] | None] = ConcurrentStableDict()
    data.set(_ZH, _messages(common__greet="你好 {name}"))
    calls: ConcurrentStableList[str] = ConcurrentStableList()
    translator = _translator(monkeypatch, data, calls)

    assert await translator.translate("common.greet") == "你好 {name}"
    assert await translator.translate("common.greet", params=ConcurrentStableDict[str, object]()) == "你好 {name}"


async def test_load_messages_caches_and_degrades(monkeypatch: pytest.MonkeyPatch) -> None:
    """语言包缓存命中不回源；回源异常降级为空映射（取词回退 key）。"""
    data: ConcurrentStableDict[str, ConcurrentStableDict[str, str] | None] = ConcurrentStableDict()
    data.set(_ZH, _messages(common__confirm="确认"))
    calls: ConcurrentStableList[str] = ConcurrentStableList()
    translator = _translator(monkeypatch, data, calls)

    first = await translator.load_messages(_ZH)
    second = await translator.load_messages(_ZH)
    assert first == second == _messages(common__confirm="确认")
    assert tuple(calls) == (_ZH,)

    empty = await translator.load_messages("fr-FR")
    assert not empty
    assert tuple(calls) == (_ZH, "fr-FR")
