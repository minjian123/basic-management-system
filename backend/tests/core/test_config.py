"""配置管理测试：Kiwi 32（结构占位回归）+ Kiwi 62（真实加载 / 分层 / 覆盖 / 校验）。"""

from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core import config
from app.core.config import (
    AppSettings,
    BaseSettings,
    Settings,
    get_settings,
    load_settings,
    validate_startup,
)
from app.core.exceptions import ConfigError

_VALID_BASE = """
[app]
name = "BMS 基础管理系统"
env = "{env}"

[server]
host = "0.0.0.0"
port = 8000

[log]
level = "INFO"

[database.platform]
url = "sqlite+aiosqlite:///./bms_platform.db"
"""

_MISSING_URL_BASE = """
[app]
name = "BMS 基础管理系统"
env = "dev"

[server]
host = "0.0.0.0"
port = 8000

[log]
level = "INFO"

[database.platform]
"""

_UNKNOWN_KEY_BASE = """
[app]
name = "BMS 基础管理系统"
env = "dev"

[server]
host = "0.0.0.0"
port = 8000

[log]
level = "INFO"
levle = "X"

[database.platform]
url = "sqlite+aiosqlite:///./bms_platform.db"
"""


def _use_config_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, body: str) -> None:
    """把配置目录指向临时目录并写入 config.toml。

    Args:
        monkeypatch: monkeypatch 夹具。
        tmp_path: 临时目录。
        body: config.toml 内容。
    """
    (tmp_path / "config.toml").write_text(body, encoding="utf-8")
    monkeypatch.setattr(config, "_config_dir", lambda: tmp_path)


# ===== Kiwi 32：结构占位回归 =====


@pytest.mark.kiwi_id(32)
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


@pytest.mark.kiwi_id(32)
def test_nested_defaults_not_shared() -> None:
    """嵌套 / 集合默认值不共享（避免可变默认串改）。"""
    first = Settings()
    second = Settings()
    assert first.cors.allow_origins is not second.cors.allow_origins
    assert first.database.platform.pool is not second.database.platform.pool
    assert first.database.platform.replicas == []


@pytest.mark.kiwi_id(32)
def test_get_settings_singleton() -> None:
    """读取接口为单例，cache_clear 后可重载。"""
    get_settings.cache_clear()
    first = get_settings()
    assert get_settings() is first
    get_settings.cache_clear()
    assert get_settings() is not first


@pytest.mark.kiwi_id(32)
def test_env_validation() -> None:
    """env 取值受 Literal 约束。"""
    assert AppSettings(name="x", env="prod").env == "prod"
    with pytest.raises(ValidationError):
        AppSettings.model_validate({"name": "x", "env": "bad"})


@pytest.mark.kiwi_id(32)
def test_base_settings_config() -> None:
    """配置分区公共基：拒绝未知键，并继承 BaseSchema 公共配置。"""
    assert BaseSettings.model_config.get("extra") == "forbid"
    assert BaseSettings.model_config.get("from_attributes") is True
    assert BaseSettings.model_config.get("str_strip_whitespace") is True
    with pytest.raises(ValidationError):
        AppSettings.model_validate({"name": "x", "unknown": 1})


@pytest.mark.kiwi_id(32)
def test_serialization() -> None:
    """Settings 经 BaseSchema 稳定序列化。"""
    data = Settings().to_dict()
    assert {"app", "server", "log", "database", "redis", "minio", "security", "cors"} <= set(data)
    assert Settings().to_json().startswith("{")


# ===== Kiwi 62：真实加载 / 分层 / 覆盖 / 校验 =====


@pytest.mark.kiwi_id(62)
def test_default_env_is_dev() -> None:
    """缺省环境为 dev，dev 覆盖生效（日志 / CORS / debug）。"""
    settings = Settings()
    assert settings.app.env == "dev"
    assert settings.log.level == "DEBUG"
    assert settings.log.format == "console"
    assert settings.app.debug is True
    assert "http://localhost:5173" in settings.cors.allow_origins


@pytest.mark.kiwi_id(62)
def test_test_env_overlay(monkeypatch: pytest.MonkeyPatch) -> None:
    """BMS_ENV=test 时 test 覆盖生效。"""
    monkeypatch.setenv("BMS_ENV", "test")
    settings = Settings()
    assert settings.app.env == "test"
    assert settings.log.level == "INFO"
    assert settings.log.format == "json"
    assert settings.cors.allow_origins == []
    assert settings.app.debug is False


@pytest.mark.kiwi_id(62)
def test_prod_env_overlay(monkeypatch: pytest.MonkeyPatch) -> None:
    """BMS_ENV=prod 时 prod 覆盖生效。"""
    monkeypatch.setenv("BMS_ENV", "prod")
    settings = Settings()
    assert settings.app.env == "prod"
    assert settings.log.level == "WARNING"
    assert settings.log.format == "json"


@pytest.mark.kiwi_id(62)
def test_env_selector_fallback_to_app_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """BMS_ENV 未设置时取 [app].env 并回写。"""
    _use_config_dir(monkeypatch, tmp_path, _VALID_BASE.format(env="test"))
    settings = Settings()
    assert settings.app.env == "test"
    assert settings.log.level == "INFO"


@pytest.mark.kiwi_id(62)
def test_env_selector_from_dotenv(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """BMS_ENV 可写在 backend/.env（进程环境缺失时）。"""
    (tmp_path / "config.toml").write_text(_VALID_BASE.format(env="dev"), encoding="utf-8")
    (tmp_path / ".env").write_text("BMS_ENV=test\n", encoding="utf-8")
    monkeypatch.setattr(config, "_config_dir", lambda: tmp_path)
    assert Settings().app.env == "test"


@pytest.mark.kiwi_id(62)
def test_env_defaults_when_no_config(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """无 BMS_ENV、无 config.toml 时环境取 dev。"""
    monkeypatch.setattr(config, "_config_dir", lambda: tmp_path)
    assert config._resolve_environment() == "dev"  # pyright: ignore[reportPrivateUsage]


@pytest.mark.kiwi_id(62)
def test_env_defaults_when_app_not_dict(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """config.toml 的 [app] 非表时环境回落 dev。"""
    (tmp_path / "config.toml").write_text('app = "not-a-dict"\n', encoding="utf-8")
    monkeypatch.setattr(config, "_config_dir", lambda: tmp_path)
    assert config._resolve_environment() == "dev"  # pyright: ignore[reportPrivateUsage]


@pytest.mark.kiwi_id(62)
def test_env_variable_override(monkeypatch: pytest.MonkeyPatch) -> None:
    """BMS_ 环境变量覆盖生效（URL 完整覆盖 + 普通键覆盖）。"""
    monkeypatch.setenv("BMS_DATABASE__PLATFORM__URL", "mysql+aiomysql://bms:pw@db:3306/bms_dev")
    monkeypatch.setenv("BMS_SERVER__PORT", "9001")
    settings = Settings()
    assert settings.database.platform.url == "mysql+aiomysql://bms:pw@db:3306/bms_dev"
    assert settings.server.port == 9001


@pytest.mark.kiwi_id(62)
def test_password_field_injection(monkeypatch: pytest.MonkeyPatch) -> None:
    """密码分字段注入：resolved_url 合成；无密码时原样返回。"""
    assert Settings().database.platform.resolved_url() == Settings().database.platform.url
    monkeypatch.setenv("BMS_DATABASE__PLATFORM__URL", "postgresql+psycopg://bms@db:5432/bms_dev")
    monkeypatch.setenv("BMS_DATABASE__PLATFORM__PASSWORD", "s3cr3t")
    resolved = Settings().database.platform.resolved_url()
    assert resolved == "postgresql+psycopg://bms:s3cr3t@db:5432/bms_dev"


@pytest.mark.kiwi_id(62)
def test_invalid_bms_env_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    """BMS_ENV 取非法值启动失败并指出键名。"""
    monkeypatch.setenv("BMS_ENV", "staging")
    with pytest.raises(ConfigError) as excinfo:
        Settings()
    assert "BMS_ENV" in str(excinfo.value)


@pytest.mark.kiwi_id(62)
def test_missing_required_key_fails(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """缺必填键启动失败并指出键路径。"""
    _use_config_dir(monkeypatch, tmp_path, _MISSING_URL_BASE)
    with pytest.raises(ConfigError) as excinfo:
        load_settings()
    assert "database.platform.url" in str(excinfo.value)


@pytest.mark.kiwi_id(62)
def test_unknown_key_fails(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """未知 / 拼错键启动失败并指出键路径。"""
    _use_config_dir(monkeypatch, tmp_path, _UNKNOWN_KEY_BASE)
    with pytest.raises(ConfigError) as excinfo:
        load_settings()
    assert "levle" in str(excinfo.value)


@pytest.mark.kiwi_id(62)
def test_invalid_value_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    """类型 / 取值非法启动失败并指出键路径。"""
    monkeypatch.setenv("BMS_SERVER__PORT", "abc")
    with pytest.raises(ConfigError) as excinfo:
        load_settings()
    assert "server.port" in str(excinfo.value)


@pytest.mark.kiwi_id(62)
def test_invalid_log_level_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    """日志级别取值非法启动失败。"""
    monkeypatch.setenv("BMS_LOG__LEVEL", "verbose")
    with pytest.raises(ConfigError) as excinfo:
        load_settings()
    assert "log.level" in str(excinfo.value)


@pytest.mark.kiwi_id(62)
def test_prod_requires_secret_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """prod 环境缺少 security.secret_key 时启动校验失败。"""
    monkeypatch.setenv("BMS_ENV", "prod")
    settings = Settings()
    with pytest.raises(ConfigError) as excinfo:
        validate_startup(settings)
    assert "security.secret_key" in str(excinfo.value)


@pytest.mark.kiwi_id(62)
def test_worker_id_wiring(monkeypatch: pytest.MonkeyPatch) -> None:
    """WorkerId 由配置接线：validate_startup 后雪花 ID 可正常产出。"""
    monkeypatch.setenv("BMS_APP__WORKER_ID", "7")
    settings = Settings()
    assert settings.app.worker_id == 7
    validate_startup(settings)
    from app.core.id import generate_id

    assert isinstance(generate_id(), int)
