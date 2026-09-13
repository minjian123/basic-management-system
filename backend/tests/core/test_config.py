"""配置基座结构占位测试（Kiwi 21）。"""

import pytest
from pydantic import ValidationError

from app.core.config import AppSettings, BaseSettings, Settings, get_settings


@pytest.mark.kiwi_id(21)
def test_defaults_and_sections() -> None:
    """八分区齐备、默认值正确。"""
    settings = Settings()
    assert settings.app.name == "BMS 基础管理系统"
    assert settings.app.env == "dev"
    assert settings.server.port == 8000
    assert settings.log.level == "DEBUG"
    assert settings.database.platform.url.endswith("bms_platform.db")
    assert settings.redis.url.startswith("redis://")
    assert settings.minio.bucket == "bms"
    assert settings.security.algorithm == "HS256"
    assert settings.cors.allow_credentials is True


@pytest.mark.kiwi_id(21)
def test_nested_defaults_not_shared() -> None:
    """嵌套 / 集合默认值不共享（避免可变默认串改）。"""
    first = Settings()
    second = Settings()
    assert first.cors.allow_origins is not second.cors.allow_origins
    assert first.database.platform.pool is not second.database.platform.pool
    assert first.database.platform.replicas == []


@pytest.mark.kiwi_id(21)
def test_get_settings_singleton() -> None:
    """读取接口为单例，cache_clear 后可重载。"""
    get_settings.cache_clear()
    first = get_settings()
    assert get_settings() is first
    get_settings.cache_clear()
    assert get_settings() is not first


@pytest.mark.kiwi_id(21)
def test_env_validation() -> None:
    """env 取值受 Literal 约束。"""
    assert AppSettings(env="prod").env == "prod"
    with pytest.raises(ValidationError):
        AppSettings.model_validate({"env": "bad"})


@pytest.mark.kiwi_id(21)
def test_base_settings_config() -> None:
    """配置分区公共基：拒绝未知键，并继承 BaseSchema 公共配置。"""
    assert BaseSettings.model_config.get("extra") == "forbid"
    assert BaseSettings.model_config.get("from_attributes") is True
    assert BaseSettings.model_config.get("str_strip_whitespace") is True
    with pytest.raises(ValidationError):
        AppSettings.model_validate({"unknown": 1})


@pytest.mark.kiwi_id(21)
def test_serialization() -> None:
    """Settings 经 BaseSchema 稳定序列化。"""
    data = Settings().to_dict()
    assert {"app", "server", "log", "database", "redis", "minio", "security", "cors"} <= set(data)
    assert Settings().to_json().startswith("{")
