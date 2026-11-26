"""装配态还原护栏（Kiwi 2557）：依赖覆盖与配置快照必须每例回到用例开始前。

背景见 `tests_support/app_state.py`：全系统装配一次后 app 跨用例复用，用例换依赖 / 改配置
若不还原，会让后继用例读到上一条用例的状态（假绿 / 假红）。本用例只测还原入口本身，
故用替身对象承载状态，不触碰真实装配态（P5 口径）。
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import cast

import pytest
from fastapi import FastAPI
from pydantic import BaseModel

from bms_core.core.concurrent import ConcurrentStableDict
from tests_support.app_state import restore_assembled_app, restore_dependency_overrides, restore_settings

pytestmark = pytest.mark.kiwi_id(2557)


class _Section(BaseModel):
    """最小配置段（与 `Settings` 各段的字段写回口径一致）。"""

    value: int = 1
    text: str = "默认"


class _Config(BaseModel):
    """最小配置对象（顶层多段）。"""

    section: _Section = _Section()


def _original() -> str:
    """装配态的原始依赖提供者。"""
    return "original"


def _fake_app(overrides: ConcurrentStableDict[object, object], cfg: _Config) -> FastAPI:
    """构造只承载「依赖覆盖 + 配置」的替身应用。

    Args:
        overrides: 依赖覆盖表初值。
        cfg: 配置对象。

    Returns:
        FastAPI: 类型上按应用使用、运行时只是承载状态的替身。
    """
    fake = SimpleNamespace(dependency_overrides=overrides, state=SimpleNamespace(settings=cfg))
    return cast("FastAPI", fake)


def test_restore_dependency_overrides_restores_previous(monkeypatch: pytest.MonkeyPatch) -> None:
    """依赖覆盖在退出上下文后回到进入前的取值。"""
    app = _fake_app(ConcurrentStableDict({_original: lambda: "override"}), _Config())
    with restore_dependency_overrides(app):
        monkeypatch.setitem(app.dependency_overrides, _original, lambda: "leak")
        assert app.dependency_overrides[_original]() == "leak"
    assert app.dependency_overrides[_original]() == "override"


def test_restore_settings_restores_fields() -> None:
    """配置段字段在退出上下文后回到进入前的取值（对象身份不变）。"""
    cfg = _Config()
    section = cfg.section
    with restore_settings(cfg):
        cfg.section.value = 9
        cfg.section.text = "被改"
    assert cfg.section is section
    assert cfg.section.value == 1
    assert cfg.section.text == "默认"


def test_restore_assembled_app_covers_both(monkeypatch: pytest.MonkeyPatch) -> None:
    """统一入口同时还原依赖覆盖与配置快照。"""
    cfg = _Config()
    app = _fake_app(ConcurrentStableDict({_original: lambda: "override"}), cfg)
    with restore_assembled_app(app):
        monkeypatch.setitem(app.dependency_overrides, _original, lambda: "leak")
        cfg.section.value = 9
    assert app.dependency_overrides[_original]() == "override"
    assert cfg.section.value == 1
