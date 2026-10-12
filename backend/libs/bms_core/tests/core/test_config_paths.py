"""配置基座补齐用例（`bms_core/core/config.py`）：配置目录回落与包名前缀校验。"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

import bms_core.core.config as config_module
from bms_core.core.config import AppSettings


def test_find_config_dir_falls_back_to_top_ancestor(monkeypatch: pytest.MonkeyPatch) -> None:
    """未命中 `config.toml` 时回落最顶层祖先（不抛错）。"""
    monkeypatch.setattr(config_module, "_BASE_CONFIG", "__unit_absent__.toml")
    assert config_module._find_config_dir().is_dir()  # pyright: ignore[reportPrivateUsage]


def test_app_settings_package_prefix_validation() -> None:
    """包名前缀校验：合法值放行；非法值（非小写字母起）即拒。"""
    assert AppSettings(name="core-test", package_prefix="mdm").package_prefix == "mdm"
    with pytest.raises(ValidationError):
        AppSettings(name="core-test", package_prefix="1Bad")
