"""应用配置加载。

加载顺序（后者覆盖前者）：
1. config.toml 公共段（[app] [log] [database] [redis] [snowflake] 等）
2. config.toml 环境段（[env.dev] / [env.test] / [env.prod]），由 BMS_ENV 指定选哪个
3. 环境变量 BMS_*（最高优先级；密钥类只走环境变量）

环境变量命名约定：BMS_<节>_<键>，如 BMS_DATABASE_PLATFORM_URL → database.platform_url；
BMS_ENV 特例映射到 app.env。
"""

from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Any, Literal, cast

from pydantic import BaseModel
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource

CONFIG_FILE = Path("config.toml")


def _as_dict(value: Any) -> dict[str, Any]:
    """将任意值收窄为字典，非字典返回空字典（tomllib 嵌套结构类型丢失时的收窄助手）。"""
    return cast(dict[str, Any], value) if isinstance(value, dict) else {}


def _find_section(merged: dict[str, Any], key: str) -> dict[str, Any] | None:
    """在公共段各小节中查找含指定键的小节（覆盖目标）。"""
    for section in merged.values():
        if isinstance(section, dict) and key in section:
            return cast(dict[str, Any], section)
    return None


class AppSettings(BaseModel):
    """应用基础配置。"""

    env: Literal["dev", "test", "prod"] = "dev"
    debug: bool = True
    name: str = "bms"


class LogSettings(BaseModel):
    """日志配置。"""

    level: str = "INFO"


class DatabaseSettings(BaseModel):
    """数据库配置（平台库 / 租户库 / 连接池）。"""

    platform_url: str = "sqlite+aiosqlite:///./data/platform.db"
    tenant_url_template: str = "sqlite+aiosqlite:///./data/tenant_{code}.db"
    pool_size: int = 5
    max_overflow: int = 10
    echo: bool = False
    dev_tenants: list[str] = []


class RedisSettings(BaseModel):
    """Redis 配置。"""

    url: str = "redis://localhost:6379/0"
    timeout: float = 0.5


class SnowflakeSettings(BaseModel):
    """雪花 ID 配置。"""

    worker_id: int = 0


class Settings(BaseSettings):
    """全局配置模型，所有配置项经此声明，禁止散落 os.getenv。"""

    app: AppSettings = AppSettings()
    log: LogSettings = LogSettings()
    database: DatabaseSettings = DatabaseSettings()
    redis: RedisSettings = RedisSettings()
    snowflake: SnowflakeSettings = SnowflakeSettings()

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        # 优先级（tuple 前者最高）：init 参数 > BMS_* 环境变量 > config.toml
        return init_settings, _EnvVarSource(settings_cls), _TomlSource(settings_cls)


class _TomlSource(PydanticBaseSettingsSource):
    """config.toml 数据源：公共段 + BMS_ENV 指定环境段合并。"""

    def get_field_value(self, field: Any, field_name: str) -> tuple[Any, str, bool]:
        raise NotImplementedError

    def __call__(self) -> dict[str, Any]:
        if not CONFIG_FILE.exists():
            return {}
        with CONFIG_FILE.open("rb") as f:
            data: dict[str, Any] = tomllib.load(f)
        env_name = os.environ.get("BMS_ENV") or str(data.get("app", {}).get("env", "dev"))
        merged: dict[str, Any] = {k: v for k, v in data.items() if k != "env"}
        env_section = _as_dict(_as_dict(data.get("env")).get(env_name))
        for key, value in env_section.items():
            if isinstance(value, dict) and key in merged and isinstance(merged[key], dict):
                merged[key] = {**merged[key], **value}
                continue
            # 扁平键（如 [env.prod] 下的 debug）：覆盖公共段含同名键的小节，找不到则并入 [app]
            target = _find_section(merged, key)
            if target is None:
                target = merged.setdefault("app", {})
            target[key] = value
        return merged


class _EnvVarSource(PydanticBaseSettingsSource):
    """BMS_ 前缀环境变量数据源：BMS_<节>_<键> → 嵌套字典。"""

    def get_field_value(self, field: Any, field_name: str) -> tuple[Any, str, bool]:
        raise NotImplementedError

    def __call__(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in os.environ.items():
            if not key.startswith("BMS_") or len(key) <= 4:
                continue
            rest = key[4:]
            if not rest:
                continue
            if rest == "ENV":
                result.setdefault("app", {})["env"] = value
                continue
            section, _, field_name = rest.lower().partition("_")
            if section not in ("app", "log", "database", "redis", "snowflake"):
                continue
            result.setdefault(section, {})[field_name] = value
        return result


def get_settings() -> Settings:
    """获取全局配置（应用内统一入口，禁止直接实例化 Settings）。"""
    return Settings()
