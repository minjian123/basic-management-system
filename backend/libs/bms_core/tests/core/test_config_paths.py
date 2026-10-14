"""配置基座补齐用例（`bms_core/core/config.py`）：配置目录定位与包名前缀校验。

配置目录定位已统一到 `bms_core.core.paths.resolve_backend_root`（环境变量优先、向上搜根、
缺根即报错不静默回落），专项用例见 `test_paths.py`；本文件保留配置目录的集成口径断言。
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

import bms_core.core.config as config_module
from bms_core.core.config import AppSettings
from bms_core.core.exceptions import ConfigError


def test_find_config_dir_returns_backend_root() -> None:
    """正常布局：配置目录即后端工程根（`config.toml` 所在目录）。"""
    config_dir = config_module._find_config_dir()  # pyright: ignore[reportPrivateUsage]
    assert config_dir.is_dir()
    assert (config_dir / "config.toml").is_file()


def test_find_config_dir_raises_when_marker_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    """异常布局：向上无标记文件即 `ConfigError`（不再静默回落最顶层祖先）。"""
    monkeypatch.setattr(config_module, "_BASE_CONFIG", "__unit_absent__.toml")
    with pytest.raises(ConfigError, match="__unit_absent__"):
        config_module._find_config_dir()  # pyright: ignore[reportPrivateUsage]


def test_find_config_dir_honours_root_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """环境变量优先：`BMS_BACKEND_ROOT` 指向含 `config.toml` 的目录时直接采用。"""
    (tmp_path / "config.toml").write_text("", encoding="utf-8")
    monkeypatch.setenv("BMS_BACKEND_ROOT", str(tmp_path))
    assert config_module._find_config_dir() == tmp_path  # pyright: ignore[reportPrivateUsage]


def test_find_config_dir_rejects_invalid_root_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """环境变量 fail-closed：指向不含标记文件的目录即报错（不静默回落）。"""
    monkeypatch.setenv("BMS_BACKEND_ROOT", str(tmp_path))
    with pytest.raises(ConfigError, match="BMS_BACKEND_ROOT"):
        config_module._find_config_dir()  # pyright: ignore[reportPrivateUsage]


def test_app_settings_package_prefix_validation() -> None:
    """包名前缀校验：合法值放行；非法值（非小写字母起）即拒。"""
    assert AppSettings(name="core-test", package_prefix="mdm").package_prefix == "mdm"
    with pytest.raises(ValidationError):
        AppSettings(name="core-test", package_prefix="1Bad")
