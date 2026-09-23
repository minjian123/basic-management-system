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

from bms_core.core.exceptions import ConfigError
from bms_core.schemas.base import BaseSchema

_ENVIRONMENTS = ("dev", "test", "prod")
_ENV_SELECTOR = "BMS_ENV"
_BASE_CONFIG = "config.toml"
_ENV_FILE = ".env"
_LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")


def _find_config_dir() -> Path:
    """定位配置目录（后端工程根）：自本文件向上取首个含 `config.toml` 的目录。

    工作区形态下配置随 `backend/` 工程根（非包内），故用向上搜根代替硬编码层级。

    Returns:
        Path: 含 `config.toml` 的最近祖先目录；未命中时回落最顶层祖先（避免导入期抛错）。
    """
    parents = Path(__file__).resolve().parents
    for parent in parents:
        if (parent / _BASE_CONFIG).is_file():
            return parent
    return parents[-1]


_CONFIG_DIR = _find_config_dir()  # backend/


class BaseSettings(BaseSchema):
    """配置分区公共基：拒绝未知键、允许字段名填充（继承 BaseSchema 公共配置）。"""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class AppSettings(BaseSettings):
    """应用元信息。"""

    name: str
    env: Literal["dev", "test", "prod"] = "dev"
    debug: bool = False
    worker_id: int = Field(default=0, ge=0, le=1023)
    service: str = ""
    """服务标识（微服务名；空则取服务包声明，启动期 `attach_service` 回写解析结果）。

    用于选取按服务的连接池覆盖与租户库 `url_template` 的 `{service}` 占位（见 `core/service.py`）。
    """


class ServerSettings(BaseSettings):
    """HTTP 服务。"""

    host: str
    port: int
    workers: int = 1
    workers_by_service: dict[str, int] = Field(default_factory=dict[str, int])
    """按服务的 worker 数覆盖：`{服务标识 → worker 数}`；缺省回落 `workers`（连接预算按服务核算用）。"""

    def workers_for(self, service: str) -> int:
        """取该服务生效的 worker 数（服务覆盖优先，缺省回落全局 `workers`）。

        Args:
            service: 服务标识（`[app].service`）。

        Returns:
            int: 生效 worker 数。
        """
        return self.workers_by_service.get(service, self.workers)


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


class PaginationSettings(BaseSettings):
    """分页契约限制（页码限深；游标分页不受限）。"""

    max_page: int = Field(default=100, ge=1)
    """页码分页最大深度（`BasePageQuery.page` 上限；超限按参数非法 10001）。"""


class TenantSettings(BaseSettings):
    """多租户解析与引擎生命周期（租户注册表缓存 / 引擎上限与阈值 / 豁免路径 / 回落策略）。"""

    resolve_cache_ttl: int = Field(default=60, ge=1)
    """租户解析缓存 TTL（秒；经缓存基座写入，命中即用）。"""
    source: str = ""
    """租户源实现（`local` / `remote`；空串 = 自动：租户服务用 `local`、其余服务用 `remote`）。"""
    engine_max_active: int = Field(default=32, ge=1)
    """租户引擎活跃上限（超出按 LRU 逐出最久未用租户引擎）。"""
    engine_idle_timeout: float = Field(default=1800.0, ge=0)
    """租户引擎闲置回收阈值（秒；每次访问先清扫）。"""
    allow_demo_fallback: bool = True
    """无任何来源时是否回落演示租户（开发兜底；生产应置 false 直接拒绝）。"""
    exempt_paths: list[str] = Field(
        default_factory=lambda: [
            "/",
            "/docs",
            "/redoc",
            "/openapi.json",
            "/healthz",
            "/readyz",
            "/metrics",
            "/.well-known/jwks.json",
            "/api/v1/auth/introspect",
        ]
    )
    """租户解析豁免路径（精确匹配；这些路径不解析租户、不设置租户上下文）。"""
    dev_tenants: list[str] = Field(default_factory=lambda: ["demo"])
    """开发库自动建表覆盖的租户编码（仅 `[database].auto_create` 且方言为 SQLite 时生效）；
    每服务按 `tenant_{code}` 相对键建表，实际库名由 `url_template` 解析。"""


class DbPoolSettings(BaseSettings):
    """数据库连接池参数。"""

    pool_size: int = 5
    max_overflow: int = 10
    pool_timeout: float = 30.0
    pool_recycle: int = 1800
    connect_timeout: float = 10.0
    """建连超时（秒）；非 SQLite 经驱动 `connect_args` 传入（达梦口径随阶段二 01-05 实测）。"""


class DatabaseTargetSettings(BaseSettings):
    """单个数据库目标（url 不含密码；密码经环境变量注入）。"""

    url: str
    replicas: list[str] = Field(default_factory=list)
    url_template: str = ""
    """连接串模板（空串回落 `url` 单库）。**平台目标**占位 `{service}` / `{database}`（= `bms_{service}`）；
    **租户目标**占位 `{service}` / `{tenant}` / `{database}`（= `bms_{service}_{tenant}`）。
    服务化后平台目标亦按模板拆分（各服务连自身平台服务库）；基础默认不启用。"""
    password: str = ""
    max_connections: int = Field(default=0, ge=0)
    """该库最大连接数；`0` 表示不校验连接预算。"""
    max_connections_by_service: dict[str, int] = Field(default_factory=dict[str, int])
    """按服务的最大连接数覆盖：`{服务标识 → max_connections}`；缺省回落目标级（每服务独立库口径）。"""
    pool: DbPoolSettings = Field(default_factory=DbPoolSettings)
    services: dict[str, DbPoolSettings] = Field(default_factory=dict[str, DbPoolSettings])
    """按服务的连接池覆盖：`{服务标识 → 池参数}`（服务标识取 `[app].service`）。"""

    def max_connections_for(self, service: str) -> int:
        """取该服务生效的最大连接数（服务覆盖优先，缺省回落目标级）。

        Args:
            service: 服务标识（`[app].service`）。

        Returns:
            int: 生效最大连接数（`0` = 不校验）。
        """
        return self.max_connections_by_service.get(service, self.max_connections)

    def resolved_url(self) -> str:
        """取最终连接串（分字段密码优先合成，供建引擎使用）。

        Returns:
            str: 可能含密码的连接串（禁止写入日志）。
        """
        if not self.password:
            return self.url
        return make_url(self.url).set(password=self.password).render_as_string(hide_password=False)

    def effective_pool(self, service: str) -> DbPoolSettings:
        """取该服务生效的连接池参数（服务覆盖优先，缺省回落到目标默认池）。

        Args:
            service: 服务标识（`[app].service`）。

        Returns:
            DbPoolSettings: 生效的池参数。
        """
        return self.services.get(service, self.pool)


class DatabaseSettings(BaseSettings):
    """三库目标（平台 / 租户 / 归档；dev 默认多 SQLite 文件）。"""

    auto_create: bool = True
    """SQLite 开发库自动建表开关（仅当方言为 SQLite 时生效；prod 置 false，建表统一走 Alembic）。"""
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


class TracerSettings(PluginSelection):
    """链路配置（`[tracer]`；在能力选择之外追加 OTLP 端点 / 采样 / 导出参数）。

    真实实现（`provider = "otel"`）经 `bms_core.tracing.setup` 配置全局 TracerProvider 与自动埋点；
    端点 / 采样率属非敏感配置，密钥一律经环境变量注入、不入日志。
    """

    otlp_endpoint: str = "http://localhost:4318"
    """OTLP/HTTP 端点（collector；容器化后经 `BMS_TRACER__OTLP_ENDPOINT` 覆盖为 `http://otel-collector:4318`）。"""

    sampler: Literal[
        "always_on",
        "always_off",
        "traceidratio",
        "parentbased_always_on",
        "parentbased_traceidratio",
    ] = "parentbased_traceidratio"
    """采样器（父级比例采样为缺省，兼顾排查与开销）。"""

    sampler_ratio: float = Field(default=1.0, ge=0.0, le=1.0)
    """比例采样率（0~1；dev 全采，prod 可下调）。"""

    export_timeout_ms: int = Field(default=10000, ge=1)
    """OTLP 导出超时（毫秒）。"""

    insecure: bool = True
    """OTLP/HTTP 明文（内网；生产经 TLS 时可关）。"""


class EdgeSettings(PluginSelection):
    """边缘信任与请求净化配置（`[edge]`；在能力选择之外追加旁路开关与豁免路径）。"""

    require_gateway_identity: bool = False
    """旁路防护开关：true 时非豁免路径缺网关注入身份即拒（dev/test 关，prod 开）。"""

    exempt_paths: list[str] = Field(default_factory=list)
    """旁路拒绝 / 租户净化豁免路径（精确匹配；空取基座缺省集）。"""


class GatewaySettings(PluginSelection):
    """网关认证接线配置（`[gateway]`；公开路径 / 网关服务标识 / 服务 JWT 时长）。

    认证接线经网关 `forward-auth` 转认证服务内部校验端点完成（07_03）；IdP 凭据归
    `[identity_provider]`、服务 JWT 私钥归 `[service_token]`，本分区只放非敏感接线参数。
    """

    service_identity: str = "gateway"
    """网关换发服务 JWT 的 `service` 标识（服务 JWT `sub`；代表「来自网关」的服务身份）。"""

    token_ttl_seconds: int = Field(default=60, ge=1)
    """网关服务 JWT 有效期（秒；短时令牌）。"""

    public_paths: list[str] = Field(
        default_factory=lambda: [
            "/api/identity/v1/auth/login",
            "/api/identity/v1/auth/refresh",
            "/api/identity/v1/captcha",
        ]
    )
    """公开路径（免认证，网关外部路径形态、前缀匹配；认证端点据此放行前置端点）。"""


class IdentityProviderSettings(PluginSelection):
    """身份源配置（`[identity_provider]`；客户端密钥只走环境变量 / Secret，不写入配置文件）。"""

    issuer: str = ""
    """OIDC issuer（发现基点；如 `http://idp:8090/realms/bms`）。"""

    client_id: str = "bms-backend"
    """OIDC 客户端标识。"""

    client_secret: str = ""
    """OIDC 客户端密钥（空串；经 `BMS_IDENTITY_PROVIDER__CLIENT_SECRET` 注入）。"""

    redirect_uri: str = "http://localhost:8000/api/v1/auth/callback"
    """授权回调地址（须注册于 IdP redirectUris）。"""

    scopes: list[str] = Field(default_factory=lambda: ["openid", "profile", "email"])
    """请求 scope。"""

    discovery_cache_ttl: float = 3600.0
    """Discovery 元数据缓存 TTL（秒）。"""

    jwks_cache_ttl: float = 300.0
    """JWKS 缓存 TTL（秒）。"""


class TokenKeySettings(BaseSettings):
    """服务 JWT 单把密钥（kid 为映射键；公钥可入配置，私钥只经环境变量 / Secret 注入）。"""

    algorithm: str = "RS256"
    """签名算法（白名单 RS256 / ES256）。"""

    public_key: str = ""
    """公钥 PEM（非敏感，可入配置）。"""

    private_key: str = ""
    """私钥 PEM（空串；经 `BMS_SERVICE_TOKEN__KEYS` 等环境变量注入）。"""


class ServiceTokenSettings(PluginSelection):
    """服务 JWT 自签配置（`[service_token]`；私钥只走环境变量 / Secret，不写入配置文件）。"""

    issuer: str = "bms"
    """自签签发方（服务 JWT `iss`；生产建议配置稳定 URI）。"""

    ttl_seconds: int = Field(default=300, ge=1)
    """服务 JWT 默认有效期（秒；短时令牌）。"""

    active_kid: str = ""
    """当前签名密钥 kid（多把签名私钥时必填）。"""

    keys: dict[str, TokenKeySettings] = Field(default_factory=dict[str, TokenKeySettings])
    """密钥集（kid → 密钥材料）；空集允许（仅校验方时只需公钥，签发时无可用私钥才拒）。"""


class DataOwnershipSettings(PluginSelection):
    """数据所有权守卫配置（`[data_ownership]`；在能力选择之外追加运行模式与例外白名单文件）。"""

    mode: Literal["off", "warn", "enforce"] = "warn"
    """运行模式：`off` 不检测 / `warn` 记录 + 计数 + 告警 / `enforce` 越界阻断（500 / 10008）。"""

    exceptions_file: str = "deploy/boundaries/data_ownership_exceptions.json"
    """读侧出口例外白名单文件（相对仓库根；缺文件视为空集）。"""


class OutboxSettings(PluginSelection):
    """发件箱投递器配置（`[outbox]`；在能力选择之外追加轮询与重试参数）。"""

    enabled: bool = False
    """后台轮询开关（真实投递器仍可经依赖注入 / CLI 手动调用）。"""

    poll_interval_seconds: float = Field(default=5.0, gt=0)
    """后台轮询间隔（秒）。"""

    batch_size: int = Field(default=100, ge=1)
    """单轮单库取待投递上限。"""

    max_retries: int = Field(default=5, ge=1)
    """转死信前的最大重试次数。"""

    retry_backoff_seconds: float = Field(default=1.0, ge=0)
    """指数退避基数（秒）：`backoff × 2^(retry_count-1)`。"""

    db_keys: list[str] = Field(default_factory=list)
    """后台轮询库键；空 = 平台库 + 引擎注册表活跃租户库键。"""


class EventSettings(PluginSelection):
    """事件配置（`[event]`；在能力选择之外追加签发契约校验模式）。"""

    contract_mode: Literal["off", "warn", "enforce"] = "enforce"
    """签发契约校验模式：`off` 不校验 / `warn` 记录告警放行 / `enforce` 未登记即拒发（10010）。"""


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
    pagination: PaginationSettings = Field(default_factory=PaginationSettings)
    tenant: TenantSettings = Field(default_factory=TenantSettings)
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
    code_validator: PluginSelection = Field(default_factory=PluginSelection)
    dashboard_card_registry: PluginSelection = Field(default_factory=PluginSelection)
    data_ownership: DataOwnershipSettings = Field(default_factory=DataOwnershipSettings)
    data_scope: PluginSelection = Field(default_factory=PluginSelection)
    dict_cache_region: PluginSelection = Field(default_factory=PluginSelection)
    dict_source: PluginSelection = Field(default_factory=PluginSelection)
    dict_translator: PluginSelection = Field(default_factory=PluginSelection)
    distributed_lock: PluginSelection = Field(default_factory=PluginSelection)
    edge: EdgeSettings = Field(default_factory=EdgeSettings)
    event: EventSettings = Field(default_factory=EventSettings)
    event_consumer: PluginSelection = Field(default_factory=PluginSelection)
    exporter: PluginSelection = Field(default_factory=PluginSelection)
    fallback: PluginSelection = Field(default_factory=PluginSelection)
    field_type_registry: PluginSelection = Field(default_factory=PluginSelection)
    file_content_search: PluginSelection = Field(default_factory=PluginSelection)
    gateway: GatewaySettings = Field(default_factory=GatewaySettings)
    global_search: PluginSelection = Field(default_factory=PluginSelection)
    hash_chain: PluginSelection = Field(default_factory=PluginSelection)
    health_check_registry: PluginSelection = Field(default_factory=PluginSelection)
    http_client: PluginSelection = Field(default_factory=PluginSelection)
    icon_registry: PluginSelection = Field(default_factory=PluginSelection)
    idempotency: PluginSelection = Field(default_factory=PluginSelection)
    identity_provider: IdentityProviderSettings = Field(default_factory=IdentityProviderSettings)
    importer: PluginSelection = Field(default_factory=PluginSelection)
    llm_provider: PluginSelection = Field(default_factory=PluginSelection)
    masking: PluginSelection = Field(default_factory=PluginSelection)
    metrics: PluginSelection = Field(default_factory=PluginSelection)
    multipart_upload: PluginSelection = Field(default_factory=PluginSelection)
    notifier: PluginSelection = Field(default_factory=PluginSelection)
    notification_center: PluginSelection = Field(default_factory=PluginSelection)
    oauth_server: PluginSelection = Field(default_factory=PluginSelection)
    org_data_source: PluginSelection = Field(default_factory=PluginSelection)
    org_name_resolver: PluginSelection = Field(default_factory=PluginSelection)
    outbox: OutboxSettings = Field(default_factory=OutboxSettings)
    outbox_store: PluginSelection = Field(default_factory=PluginSelection)
    password_policy: PluginSelection = Field(default_factory=PluginSelection)
    permission: PluginSelection = Field(default_factory=PluginSelection)
    preference: PluginSelection = Field(default_factory=PluginSelection)
    print_exporter: PluginSelection = Field(default_factory=PluginSelection)
    print_template: PluginSelection = Field(default_factory=PluginSelection)
    query_provider_registry: PluginSelection = Field(default_factory=PluginSelection)
    query_scheme_store: PluginSelection = Field(default_factory=PluginSelection)
    rate_limiter: PluginSelection = Field(default_factory=PluginSelection)
    realtime_publisher: PluginSelection = Field(default_factory=PluginSelection)
    replay_guard: PluginSelection = Field(default_factory=PluginSelection)
    saga: PluginSelection = Field(default_factory=PluginSelection)
    scope_checker: PluginSelection = Field(default_factory=PluginSelection)
    search_index: PluginSelection = Field(default_factory=PluginSelection)
    service_client: PluginSelection = Field(default_factory=PluginSelection)
    service_token: ServiceTokenSettings = Field(default_factory=ServiceTokenSettings)
    session_store: PluginSelection = Field(default_factory=PluginSelection)
    sharding: PluginSelection = Field(default_factory=PluginSelection)
    storage: PluginSelection = Field(default_factory=PluginSelection)
    task: PluginSelection = Field(default_factory=PluginSelection)
    tenant_self_service: PluginSelection = Field(default_factory=PluginSelection)
    token_verifier: PluginSelection = Field(default_factory=PluginSelection)
    tracer: TracerSettings = Field(default_factory=TracerSettings)
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
    from bms_core.core.id import id_generator

    id_generator.reconfigure(settings.app.worker_id)
