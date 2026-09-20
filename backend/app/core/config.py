"""core 层配置基座：真实读取 config.toml + 环境分层 + `BMS_` 覆盖 + 启动校验。

- 加载优先级（高 → 低）：生效环境回写 `app.env` → 显式入参 → 进程环境变量（`BMS_` 前缀，
  嵌套键双层下划线）→ `backend/.env` → `config.{env}.toml`（环境覆盖）→ `config.toml`（基线）。
- 生效环境由 `BMS_ENV`（进程环境 / `backend/.env`）指定，未设置时取 `[app].env`，再缺省 `dev`；
  非法值、缺必填键、类型 / 取值非法、未知或拼错键一律启动即报错并指出键名（不打印键值）。
- 密钥类配置只走环境变量，不入 `config.toml` / `.env.example` / 日志。
- 所有模型继承 `BaseSchema`（纳入基类体系，稳定序列化）。
"""

import os
import tomllib
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, cast

from dotenv import dotenv_values
from pydantic import ConfigDict, Field, ValidationError, field_validator
from pydantic.fields import FieldInfo
from pydantic_settings import (
    BaseSettings as PydanticBaseSettings,
)
from pydantic_settings import (
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    TomlConfigSettingsSource,
)
from sqlalchemy.engine import make_url

from app.core.exceptions import ConfigError
from app.schemas.base import BaseSchema

_ENVIRONMENTS = ("dev", "test", "prod")
_ENV_SELECTOR = "BMS_ENV"
_CONFIG_DIR = Path(__file__).resolve().parents[2]  # backend/
_BASE_CONFIG = "config.toml"
_ENV_FILE = ".env"
_LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")


class BaseSettings(BaseSchema):
    """配置分区公共基：拒绝未知键、允许字段名填充（继承 BaseSchema 公共配置）。"""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class AppSettings(BaseSettings):
    """应用元信息。"""

    name: str
    env: Literal["dev", "test", "prod"] = "dev"
    debug: bool = False
    worker_id: int = Field(default=0, ge=0, le=1023)


class ServerSettings(BaseSettings):
    """HTTP 服务。"""

    host: str
    port: int
    workers: int = 1


class LogSettings(BaseSettings):
    """日志（真实渲染见 03-2）。"""

    level: str
    format: Literal["console", "json"] = "json"
    slow_request_ms: int = 1000

    @field_validator("level")
    @classmethod
    def _normalize_level(cls, value: str) -> str:
        """日志级别归一化为大写并校验取值。

        Args:
            value: 原始级别字符串。

        Returns:
            str: 归一化级别。

        Raises:
            ValueError: 取值不在允许集合内。
        """
        upper = value.strip().upper()
        if upper not in _LOG_LEVELS:
            raise ValueError(f"log.level 取值非法：{value}（允许 {'/'.join(_LOG_LEVELS)}）")
        return upper


class HealthSettings(BaseSettings):
    """健康检查（就绪探针超时，毫秒；见 03-3）。"""

    check_timeout_ms: int = Field(default=2000, ge=1)
    total_timeout_ms: int = Field(default=5000, ge=1)


class DbPoolSettings(BaseSettings):
    """数据库连接池参数。"""

    pool_size: int = 5
    max_overflow: int = 10
    pool_timeout: float = 30.0
    pool_recycle: int = 1800


class DatabaseTargetSettings(BaseSettings):
    """单个数据库目标（url 不含密码；密码经环境变量注入）。"""

    url: str
    replicas: list[str] = Field(default_factory=list)
    password: str = ""
    pool: DbPoolSettings = Field(default_factory=DbPoolSettings)

    def resolved_url(self) -> str:
        """取最终连接串（分字段密码优先合成，供建引擎使用）。

        Returns:
            str: 可能含密码的连接串（禁止写入日志）。
        """
        if not self.password:
            return self.url
        return make_url(self.url).set(password=self.password).render_as_string(hide_password=False)


class DatabaseSettings(BaseSettings):
    """三库目标（平台 / 租户 / 归档；dev 默认多 SQLite 文件）。"""

    platform: DatabaseTargetSettings
    tenants: DatabaseTargetSettings = Field(
        default_factory=lambda: DatabaseTargetSettings(url="sqlite+aiosqlite:///./bms_tenant_demo.db")
    )
    archive: DatabaseTargetSettings = Field(
        default_factory=lambda: DatabaseTargetSettings(url="sqlite+aiosqlite:///./bms_archive.db")
    )


class RedisSettings(BaseSettings):
    """Redis。"""

    url: str = "redis://localhost:6379/0"


class MinioSettings(BaseSettings):
    """对象存储端点 / 凭据（桶名统一取 `[storage].options.bucket`）。"""

    endpoint: str = ""
    access_key: str = ""
    secret_key: str = ""
    secure: bool = False


class SecuritySettings(BaseSettings):
    """安全（占位；真实实现随认证阶段）。"""

    secret_key: str = ""
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60


class CorsSettings(BaseSettings):
    """跨域。"""

    allow_origins: list[str] = Field(default_factory=list)
    allow_methods: list[str] = Field(default_factory=lambda: ["*"])
    allow_headers: list[str] = Field(default_factory=lambda: ["*"])
    allow_credentials: bool = True


class PluginSelection(BaseSettings):
    """能力实现选择：`provider` + 非敏感 `options`（密钥只走 Secret / 环境变量）。"""

    provider: str = ""
    """实现名（空串 / 未配置 → 解析到 `null` 缺省实现）。"""

    options: dict[str, object] = Field(default_factory=dict[str, object])
    """非敏感选项（键位由各实现解读；密钥不入配置 / 不入日志）。"""


def _config_dir() -> Path:
    """配置目录（默认 backend/ 根；测试可 monkeypatch）。

    Returns:
        Path: 配置目录。
    """
    return _CONFIG_DIR


def _read_base_app_env() -> str:
    """读取基线 `config.toml` 的 `[app].env`（不存在时返回空串）。

    Returns:
        str: `[app].env` 原始值，缺失返回空串。
    """
    base = _config_dir() / _BASE_CONFIG
    if not base.is_file():
        return ""
    raw = tomllib.loads(base.read_text(encoding="utf-8"))
    app = raw.get("app")
    if not isinstance(app, dict):
        return ""
    return str(cast("dict[str, Any]", app).get("env", "")).strip()


def _resolve_environment() -> str:
    """解析生效环境：`BMS_ENV`（进程 / `.env`）→ `[app].env` → `dev`。

    Returns:
        str: 生效环境（dev / test / prod）。

    Raises:
        ConfigError: 环境取值非法。
    """
    raw = os.environ.get(_ENV_SELECTOR, "").strip()
    env_file = _config_dir() / _ENV_FILE
    if not raw and env_file.is_file():
        raw = (dotenv_values(env_file).get(_ENV_SELECTOR) or "").strip()
    if not raw:
        raw = _read_base_app_env()
    if not raw:
        return "dev"
    if raw not in _ENVIRONMENTS:
        allowed = "/".join(_ENVIRONMENTS)
        raise ConfigError(f"环境取值非法：{raw}（允许 {allowed}；由 BMS_ENV 或 [app].env 指定）")
    return raw


class _EnvSelectorSource(PydanticBaseSettingsSource):
    """强制回写 `app.env = 生效环境` 的配置源（优先序最高）。"""

    def __init__(self, settings_cls: type[PydanticBaseSettings], env: str) -> None:
        """初始化。

        Args:
            settings_cls: Settings 类。
            env: 生效环境。
        """
        super().__init__(settings_cls)
        self._env = env

    def get_field_value(self, field: FieldInfo, field_name: str) -> tuple[Any, str, bool]:  # pragma: no cover
        """不按字段取单值（统一在 `__call__` 返回；协议要求实现，运行期不经此路径）。

        Args:
            field: 字段信息。
            field_name: 字段名。

        Returns:
            tuple: 固定空值占位。
        """
        del field, field_name
        return None, "", False

    def __call__(self) -> dict[str, Any]:
        """返回 `app.env` 覆盖。

        Returns:
            dict: 仅含生效环境的嵌套字典。
        """
        return {"app": {"env": self._env}}


class Settings(PydanticBaseSettings, BaseSettings):  # pyright: ignore[reportIncompatibleVariableOverride]
    """应用配置（真实读取 `config.toml` + 分层覆盖 + 启动校验）。"""

    model_config = SettingsConfigDict(
        extra="forbid",
        populate_by_name=True,
        env_prefix="BMS_",
        env_nested_delimiter="__",
        env_file=_CONFIG_DIR / _ENV_FILE,
        case_sensitive=False,
    )

    app: AppSettings
    server: ServerSettings
    log: LogSettings
    health: HealthSettings = Field(default_factory=HealthSettings)
    database: DatabaseSettings
    redis: RedisSettings = Field(default_factory=RedisSettings)
    minio: MinioSettings = Field(default_factory=MinioSettings)
    security: SecuritySettings = Field(default_factory=SecuritySettings)
    cors: CorsSettings = Field(default_factory=CorsSettings)

    # 能力实现选择（分区名 = plugin_key；`object_storage` 别名 `storage`；未列分区取默认 → null）
    archive_policy: PluginSelection = Field(default_factory=PluginSelection)
    archive_query_router: PluginSelection = Field(default_factory=PluginSelection)
    audit: PluginSelection = Field(default_factory=PluginSelection)
    audit_search: PluginSelection = Field(default_factory=PluginSelection)
    cache: PluginSelection = Field(default_factory=PluginSelection)
    captcha: PluginSelection = Field(default_factory=PluginSelection)
    chat_action_gate: PluginSelection = Field(default_factory=PluginSelection)
    chat_session_store: PluginSelection = Field(default_factory=PluginSelection)
    chat_stream: PluginSelection = Field(default_factory=PluginSelection)
    circuit_breaker: PluginSelection = Field(default_factory=PluginSelection)
    dashboard_card_registry: PluginSelection = Field(default_factory=PluginSelection)
    data_scope: PluginSelection = Field(default_factory=PluginSelection)
    dict_cache_region: PluginSelection = Field(default_factory=PluginSelection)
    dict_source: PluginSelection = Field(default_factory=PluginSelection)
    dict_translator: PluginSelection = Field(default_factory=PluginSelection)
    distributed_lock: PluginSelection = Field(default_factory=PluginSelection)
    event: PluginSelection = Field(default_factory=PluginSelection)
    event_consumer: PluginSelection = Field(default_factory=PluginSelection)
    exporter: PluginSelection = Field(default_factory=PluginSelection)
    fallback: PluginSelection = Field(default_factory=PluginSelection)
    field_type_registry: PluginSelection = Field(default_factory=PluginSelection)
    file_content_search: PluginSelection = Field(default_factory=PluginSelection)
    global_search: PluginSelection = Field(default_factory=PluginSelection)
    hash_chain: PluginSelection = Field(default_factory=PluginSelection)
    health_check_registry: PluginSelection = Field(default_factory=PluginSelection)
    http_client: PluginSelection = Field(default_factory=PluginSelection)
    idempotency: PluginSelection = Field(default_factory=PluginSelection)
    identity_provider: PluginSelection = Field(default_factory=PluginSelection)
    importer: PluginSelection = Field(default_factory=PluginSelection)
    llm_provider: PluginSelection = Field(default_factory=PluginSelection)
    masking: PluginSelection = Field(default_factory=PluginSelection)
    metrics: PluginSelection = Field(default_factory=PluginSelection)
    notifier: PluginSelection = Field(default_factory=PluginSelection)
    notification_center: PluginSelection = Field(default_factory=PluginSelection)
    oauth_server: PluginSelection = Field(default_factory=PluginSelection)
    org_data_source: PluginSelection = Field(default_factory=PluginSelection)
    org_name_resolver: PluginSelection = Field(default_factory=PluginSelection)
    password_policy: PluginSelection = Field(default_factory=PluginSelection)
    permission: PluginSelection = Field(default_factory=PluginSelection)
    preference: PluginSelection = Field(default_factory=PluginSelection)
    query_provider_registry: PluginSelection = Field(default_factory=PluginSelection)
    query_scheme_store: PluginSelection = Field(default_factory=PluginSelection)
    rate_limiter: PluginSelection = Field(default_factory=PluginSelection)
    realtime_publisher: PluginSelection = Field(default_factory=PluginSelection)
    replay_guard: PluginSelection = Field(default_factory=PluginSelection)
    scope_checker: PluginSelection = Field(default_factory=PluginSelection)
    search_index: PluginSelection = Field(default_factory=PluginSelection)
    session_store: PluginSelection = Field(default_factory=PluginSelection)
    sharding: PluginSelection = Field(default_factory=PluginSelection)
    storage: PluginSelection = Field(default_factory=PluginSelection)
    task: PluginSelection = Field(default_factory=PluginSelection)
    tracer: PluginSelection = Field(default_factory=PluginSelection)
    translator: PluginSelection = Field(default_factory=PluginSelection)
    webhook_sender: PluginSelection = Field(default_factory=PluginSelection)
    workflow_engine: PluginSelection = Field(default_factory=PluginSelection)
    engine_factory: PluginSelection = Field(default_factory=PluginSelection)
    session_factory: PluginSelection = Field(default_factory=PluginSelection)
    id_generator: PluginSelection = Field(default_factory=PluginSelection)

    if TYPE_CHECKING:
        # 仅类型检查期：真实初始化由 pydantic-settings 从多源装配，运行时字段键由源提供；
        # 该存根避免严格模式把「必填模型字段」误判为构造必传实参。
        def __init__(self, **data: Any) -> None: ...

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[PydanticBaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        """组装配置源（高 → 低：生效环境 → 入参 → 环境变量 → .env → 环境覆盖 → 基线）。

        Args:
            settings_cls: Settings 类。
            init_settings: 显式入参源。
            env_settings: 进程环境变量源。
            dotenv_settings: `.env` 源。
            file_secret_settings: 密钥目录源。

        Returns:
            tuple: 配置源元组（靠前优先）。
        """
        env = _resolve_environment()
        overlay = _config_dir() / f"config.{env}.toml"
        files = [_config_dir() / _BASE_CONFIG] + ([overlay] if overlay.is_file() else [])
        return (
            _EnvSelectorSource(settings_cls, env),
            init_settings,
            env_settings,
            dotenv_settings,
            file_secret_settings,
            TomlConfigSettingsSource(settings_cls, toml_file=files, deep_merge=True),
        )


def _summarize(error: ValidationError) -> str:
    """汇总校验错误（仅键路径与原因，不含键值）。

    Args:
        error: Pydantic 校验异常。

    Returns:
        str: 逐条「键路径：原因」的汇总文本。
    """
    lines: list[str] = []
    for item in error.errors():
        path = ".".join(str(part) for part in item["loc"]) or "(根)"
        lines.append(f"{path}：{item['msg']}")
    return "配置校验失败：" + "；".join(lines)


def load_settings() -> Settings:
    """读取并校验配置（缺必填键 / 类型取值非法 / 未知键 → 启动失败并指出键名）。

    Returns:
        Settings: 应用配置。

    Raises:
        ConfigError: 校验失败。
    """
    try:
        return Settings()
    except ValidationError as exc:
        raise ConfigError(_summarize(exc)) from exc


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """取应用配置单例（首次取用即读取 + 校验）。

    Returns:
        Settings: 应用配置单例。
    """
    return load_settings()


def validate_startup(settings: Settings) -> None:
    """启动期补充校验与接线（lifespan 调用）。

    Args:
        settings: 应用配置。

    Raises:
        ConfigError: 生产环境缺少必要密钥。
    """
    if settings.app.env == "prod" and not settings.security.secret_key:
        raise ConfigError("生产环境必须提供 security.secret_key（BMS_SECURITY__SECRET_KEY）")
    from app.core.id import id_generator

    id_generator.reconfigure(settings.app.worker_id)
