"""单元测试：配置加载（BMS_ENV 切换、环境变量覆盖、环境段合并）。"""

from __future__ import annotations

import pytest

from app.core.config import Settings, get_settings


def test_default_env_is_test() -> None:
    """conftest 强制 BMS_ENV=test，默认配置应落在测试环境。"""
    settings = get_settings()
    assert settings.app.env == "test"
    assert settings.app.debug is False  # [env.test].debug=false
    assert settings.database.dev_tenants == ["demo", "demo2"]  # [env.test.database] 深合并生效


def test_env_switch_by_bms_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """BMS_ENV=prod 时环境段覆盖生效（[env.prod].debug=false）。"""
    monkeypatch.setenv("BMS_ENV", "prod")
    settings = Settings()
    assert settings.app.env == "prod"
    assert settings.app.debug is False


def test_env_var_override(monkeypatch: pytest.MonkeyPatch) -> None:
    """环境变量 BMS_<节>_<键> 覆盖 config.toml（最高优先级）。"""
    monkeypatch.setenv("BMS_LOG_LEVEL", "DEBUG")
    settings = get_settings()
    assert settings.log.level == "DEBUG"


def test_env_var_mapping(monkeypatch: pytest.MonkeyPatch) -> None:
    """BMS_ENV 特例映射 app.env；未知段忽略。"""
    monkeypatch.setenv("BMS_ENV", "prod")
    monkeypatch.setenv("BMS_UNKNOWN_KEY", "x")
    settings = get_settings()
    assert settings.app.env == "prod"
