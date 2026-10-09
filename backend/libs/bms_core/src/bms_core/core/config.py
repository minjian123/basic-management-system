"""core 层配置基座：真实读取 config.toml + 环境分层 + `BMS_` 覆盖 + 启动校验。

- 加载优先级（高 → 低）：生效环境回写 `app.env` → 显式入参 → 进程环境变量（`BMS_` 前缀，
  嵌套键双层下划线）→ `backend/.env` → `config.{env}.toml`（环境覆盖）→ `config.toml`（基线）。
- 生效环境由 `BMS_ENV`（进程环境 / `backend/.env`）指定，未设置时取 `[app].env`，再缺省 `dev`；
  非法值、缺必填键、类型 / 取值非法、未知或拼错键一律启动即报错并指出键名（不打印键值）。
- 密钥类配置只走环境变量，不入 `config.toml` / `.env.example` / 日志。
- 所有模型继承 `BaseSchema`（纳入基类体系，稳定序列化）。
"""

import os
import re
import tomllib
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any, Literal, cast

from dotenv import dotenv_values
from pydantic import ConfigDict, Field, ValidationError, field_validator, model_validator
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

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.exceptions import ConfigError
from bms_core.permission.profile import DEFAULT_PROFILE, ensure_profile_supported, normalize_profile
from bms_core.schemas.base import (
    CONTRACT_COLLECTION,
    CONTRACT_STABLE_DICT,
    CONTRACT_STABLE_LIST,
    BaseSchema,
)

_PACKAGE_PREFIX_RE = re.compile(r"^[a-z][a-z0-9_]*$")
"""服务包名前缀格式（`[app].package_prefix`）：小写字母起、仅小写字母 / 数字 / 下划线。"""

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

    docs_enabled: bool = True
    """文档端点开关（Swagger `/docs` / ReDoc `/redoc` / OpenAPI `/openapi.json`）。

    基线开（dev / test 便于联调），`config.prod.toml` 置 `false` 关闭（契约唯一来源为 CI 快照
    `deploy/contracts/`）；`app.openapi()` 方法不受影响，CI 契约生成仍可用。
    """

    package_prefix: str = "bms"
    """服务包名前缀（env `BMS_APP__PACKAGE_PREFIX`）——链的服务模型模块按
    `{package_prefix}_{service}.models` 解析（见 `db/migration.py::service_model_modules`）。

    默认 `bms`（平台既有口径，现有部署零影响）；**产品部署配自有前缀**（如 mdm 配 `mdm`，服务包
    `mdm_org`），使模型解析、迁移与开发库自动建表按产品包名取模型（12_04）。
    """

    @field_validator("package_prefix")
    @classmethod
    def _validate_package_prefix(cls, value: str) -> str:
        """校验包名前缀（小写字母起、仅小写字母 / 数字 / 下划线）。

        Args:
            value: 配置值。

        Returns:
            str: 校验后的值。

        Raises:
            ValueError: 取值非法。
        """
        if not _PACKAGE_PREFIX_RE.match(value):
            raise ValueError(f"app.package_prefix 取值非法：{value}（须为小写字母起、仅小写字母 / 数字 / 下划线）")
        return value


class ServerSettings(BaseSettings):
    """HTTP 服务。"""

    host: str
    port: int
    workers: int = 1
    workers_by_service: Annotated[ConcurrentStableDict[str, int], CONTRACT_COLLECTION] = Field(
        default_factory=CONTRACT_STABLE_DICT
    )
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
    redact_keys: Annotated[ConcurrentStableList[str], CONTRACT_COLLECTION] = Field(default_factory=CONTRACT_STABLE_LIST)
    """追加的敏感日志键名（内置名单恒生效，配置**只可追加不可移除**）。"""
    redact_suffixes: Annotated[ConcurrentStableList[str], CONTRACT_COLLECTION] = Field(
        default_factory=CONTRACT_STABLE_LIST
    )
    """追加的敏感日志键名后缀（同上，只可追加）。"""

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


class TenantMembershipSettings(BaseSettings):
    """用户↔租户可达关系数据源（段 `[tenant_membership]`；11_01）。"""

    source: str = ""
    """关系数据源实现（`local` / `remote`；空串 = 自动：租户服务用 `local`、其余服务用 `remote`）。"""


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
    exempt_paths: Annotated[ConcurrentStableList[str], CONTRACT_COLLECTION] = Field(
        default_factory=lambda: ConcurrentStableList(
            [
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
    )
    """租户解析豁免路径（精确匹配；这些路径不解析租户、不设置租户上下文）。"""
    deferred_paths: Annotated[ConcurrentStableList[str], CONTRACT_COLLECTION] = Field(
        default_factory=lambda: ConcurrentStableList(
            [
                "/api/v1/auth/login",
                "/api/v1/auth/forgot-password",
                "/api/v1/auth/reset-password",
                "/api/v1/captcha",
                "/api/v1/auth/sso",
            ]
        )
    )
    """免登录链路延迟解析路径（前缀匹配；有来源则解析、无来源置空放行，由端点层再解析）。"""
    dev_tenants: Annotated[ConcurrentStableList[str], CONTRACT_COLLECTION] = Field(
        default_factory=lambda: ConcurrentStableList(["demo"])
    )
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
    replicas: Annotated[ConcurrentStableList[str], CONTRACT_COLLECTION] = Field(default_factory=CONTRACT_STABLE_LIST)
    url_template: str = ""
    """连接串模板（空串回落 `url` 单库）。**平台目标**占位 `{service}` / `{database}`（= `bms_{service}`）；
    **租户目标**占位 `{service}` / `{tenant}` / `{database}`（= `bms_{service}_{tenant}`）。
    服务化后平台目标亦按模板拆分（各服务连自身平台服务库）；基础默认不启用。"""
    password: str = ""
    max_connections: int = Field(default=0, ge=0)
    """该库最大连接数；`0` 表示不校验连接预算。"""
    max_connections_by_service: Annotated[ConcurrentStableDict[str, int], CONTRACT_COLLECTION] = Field(
        default_factory=CONTRACT_STABLE_DICT
    )
    """按服务的最大连接数覆盖：`{服务标识 → max_connections}`；缺省回落目标级（每服务独立库口径）。"""
    pool: DbPoolSettings = Field(default_factory=DbPoolSettings)
    services: Annotated[ConcurrentStableDict[str, DbPoolSettings], CONTRACT_COLLECTION] = Field(
        default_factory=CONTRACT_STABLE_DICT
    )
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


_SQLITE_BACKEND = "sqlite"


def resolve_sqlite_dir(url: str, sqlite_dir: str) -> str:
    """按 `sqlite_dir` 基址归一 SQLite 连接串的相对文件路径。

    - `sqlite_dir` 为空、连接串非 SQLite、内存库（`:memory:`）或无文件名时原样返回；
    - 文件路径为绝对路径时原样返回；
    - 相对 `sqlite_dir` 以配置目录（`backend/`）为锚，避免随进程 CWD 漂移；
    - 基址非空时自动创建目录（新克隆 / CI 首次运行无需预建）。

    Args:
        url: 数据库连接串（不含或含密码均可，仅改写文件路径部分）。
        sqlite_dir: SQLite 相对路径基址（空串表示不介入）。

    Returns:
        str: 可能改写文件路径后的连接串（方言与其余部分不变）。
    """
    if not sqlite_dir:
        return url
    parsed = make_url(url)
    if parsed.get_backend_name() != _SQLITE_BACKEND:
        return url
    database = parsed.database
    if not database or database == ":memory:":
        return url
    path = Path(database)
    if path.is_absolute():
        return url
    base = Path(sqlite_dir)
    if not base.is_absolute():
        base = _CONFIG_DIR / base
    base = base.resolve()
    base.mkdir(parents=True, exist_ok=True)
    target = (base / path).resolve()
    return parsed.set(database=str(target)).render_as_string(hide_password=False)


class DatabaseSettings(BaseSettings):
    """三库目标（平台 / 租户 / 归档；dev 默认多 SQLite 文件）。"""

    auto_create: bool = True
    """SQLite 开发库自动建表开关（仅当方言为 SQLite 时生效；prod 置 false，建表统一走 Alembic）。"""
    name_prefix: str = "bms"
    """库名前缀（env `BMS_DATABASE__NAME_PREFIX`）——平台库 `{prefix}_{service}`、服务租户库
    `{prefix}_{service}_{code}`、归档库 `{prefix}_archive` 的统一来源（`db/keys.py` 派生）。

    默认 `bms`（基座既有口径，现有部署零影响）；产品部署可配自有前缀（如 mdm 配 `mdm`），
    使库名体现产品标识而仍经基座统一派生（禁止业务侧自拼库名，见《后端开发规范》）。"""
    sqlite_dir: str = ""
    """SQLite 相对文件路径统一基址（env `BMS_DATABASE__SQLITE_DIR`）。

    空串表示不介入，相对路径沿用「当前工作目录」语义；非空时仅对 SQLite 方言的相对文件路径生效，
    相对基址以配置目录（`backend/`）为锚（不随进程 CWD 漂移），首次解析自动建目录。"""
    platform: DatabaseTargetSettings
    tenants: DatabaseTargetSettings
    archive: DatabaseTargetSettings

    def apply_sqlite_dir(self, url: str) -> str:
        """按 `sqlite_dir` 基址归一相对 SQLite 路径（引擎 / 迁移解析连接串时统一调用）。

        Args:
            url: 数据库连接串（不含或含密码均可，仅改写文件路径部分）。

        Returns:
            str: 归一后的连接串（`sqlite_dir` 为空或非适用连接串时原样返回）。
        """
        return resolve_sqlite_dir(url, self.sqlite_dir)


class RedisSettings(BaseSettings):
    """Redis 基础能力（`[redis]`）：连接参数 + 客户端实现选择（03_04 / 需求 03-5）。

    - 连接参数一处集中，经统一客户端能力域（`redis_client`）共享给各能力域使用
      （单进程同步 / 异步各一个连接池，禁止各域自建连）。
    - `required=true`（缺省）表示 Redis 为**基础（必需）能力**：`provider` 不得为空，
      取客户端失败即报 `RedisUnavailableError`（`10012` / 503），不静默降级；
      `provider=null` 仅作应急旁路，须同时置 `required=false`（启动期校验拦截）。
    """

    provider: str = "redis"
    """客户端实现名（缺省 `redis` 即启用；`null` 仅应急旁路）。"""

    url: str = "redis://localhost:6379/0"
    """连接串（`BMS_REDIS__URL`）。"""

    db: int | None = None
    """库号覆盖（非空时覆盖 url 中的库号）。"""

    pool_size: int = Field(default=0, ge=0)
    """单进程连接池上限（0 = 客户端默认）。"""

    socket_timeout_ms: int = Field(default=500, ge=1)
    """命令超时（毫秒）——架构要求「Redis 操作短超时快速失败」。"""

    socket_connect_timeout_ms: int = Field(default=500, ge=1)
    """建连超时（毫秒）。"""

    health_check_interval_s: int = Field(default=30, ge=0)
    """连接健康探测间隔（秒）。"""

    key_prefix: str = "bms"
    """统一键前缀（键口径 `{前缀}:{租户|global}:{域}:{业务键}`）。"""

    required: bool = True
    """必需标志：为真时 `provider` 不得为空（启动期校验），缺省实现取客户端即报 `10012`。"""


class MinioSettings(BaseSettings):
    """对象存储端点 / 凭据（桶名统一取 `[storage].options.bucket`）。"""

    endpoint: str = ""
    access_key: str = ""
    secret_key: str = ""
    secure: bool = False


class TokenKeySettings(BaseSettings):
    """JWT 单把密钥（kid 为映射键；公钥可入配置，私钥只经环境变量 / Secret 注入）。

    服务 JWT（`[service_token].keys`）与用户令牌（`[security].keys`）共用本结构。
    """

    algorithm: str = "RS256"
    """签名算法（白名单 RS256 / ES256）。"""

    public_key: str = ""
    """公钥 PEM（非敏感，可入配置）。"""

    private_key: str = ""
    """私钥 PEM（空串；经 `BMS_SERVICE_TOKEN__KEYS` / `BMS_SECURITY__KEYS` 等环境变量注入）。"""


class SecuritySettings(BaseSettings):
    """安全配置（`[security]`；认证原语口径，密钥只走环境变量 / Secret）。"""

    secret_key: str = ""
    """通用密钥（会话指纹 HMAC 与生产启动校验）；生产必填（`BMS_SECURITY__SECRET_KEY`）。"""

    access_token_expire_minutes: int = Field(default=30, ge=1)
    """access token 有效期（分钟；架构 14 定为 30 分钟）。"""

    refresh_token_expire_days: int = Field(default=14, ge=1)
    """refresh token 有效期（天；架构 14 定为 14 天滚动轮换）。"""

    session_refresh_expire_hours: int = Field(default=24, ge=1)
    """会话级 refresh 有效期（小时；`remember_me=false` 未勾选「记住我」时取此值）。

    会话级登录同时下发**会话 Cookie**（浏览器关闭即失效）；本值为其有界安全上限
    （refresh JWT `exp` / `sys_session.expires_at` / Redis 会话标记 TTL 三者对齐）。
    """

    active_kid: str = ""
    """当前签名密钥 kid（用户令牌多把签名私钥时必填）。"""

    keys: Annotated[ConcurrentStableDict[str, TokenKeySettings], CONTRACT_COLLECTION] = Field(
        default_factory=CONTRACT_STABLE_DICT
    )
    """用户令牌密钥集（kid → 密钥材料；kid 须带 `usr-` 前缀；空集允许装配，使用时 fail-closed）。"""


class CorsSettings(BaseSettings):
    """跨域。"""

    allow_origins: Annotated[ConcurrentStableList[str], CONTRACT_COLLECTION] = Field(
        default_factory=CONTRACT_STABLE_LIST
    )
    allow_methods: Annotated[ConcurrentStableList[str], CONTRACT_COLLECTION] = Field(
        default_factory=lambda: ConcurrentStableList(["*"])
    )
    allow_headers: Annotated[ConcurrentStableList[str], CONTRACT_COLLECTION] = Field(
        default_factory=lambda: ConcurrentStableList(["*"])
    )
    allow_credentials: bool = True


class PluginSelection(BaseSettings):
    """能力实现选择：`provider` + 非敏感 `options`（密钥只走 Secret / 环境变量）。"""

    provider: str = ""
    """实现名（空串 / 未配置 → 解析到 `null` 缺省实现）。"""

    options: Annotated[ConcurrentStableDict[str, object], CONTRACT_COLLECTION] = Field(
        default_factory=CONTRACT_STABLE_DICT
    )
    """非敏感选项（键位由各实现解读；密钥不入配置 / 不入日志）。"""


class PermissionSettings(PluginSelection):
    """权限引擎配置（`[permission]`；在能力选择之外追加引擎档位）。

    档位（`profile`）决定引擎能力集合：`smb`（中小企业基础版，当前已实现）/ `enterprise`（大型企业精细化）/
    `enterprise_hr`（大型企业人事结构化）；未实现的档位在启动期报错（fail-closed），不静默降级为 `smb`。

    `provider` 由 `null`（恒放行占位）切为 `rbac` 即启用真实校验；`options` 承载快照 TTL、豁免角色等实现参数。
    """

    profile: str = DEFAULT_PROFILE
    """引擎档位（缺省 `smb`；取值与含义见 `bms_core.permission.profile`）。"""

    @model_validator(mode="after")
    def _validate_profile(self) -> PermissionSettings:
        """校验档位合法且已实现（未实现即启动失败，不静默降级）。

        Returns:
            PermissionSettings: 自身。

        Raises:
            ConfigError: 档位非法或尚未实现。
        """
        ensure_profile_supported(normalize_profile(self.profile))
        return self


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

    exempt_paths: Annotated[ConcurrentStableList[str], CONTRACT_COLLECTION] = Field(
        default_factory=CONTRACT_STABLE_LIST
    )
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

    public_paths: Annotated[ConcurrentStableList[str], CONTRACT_COLLECTION] = Field(
        default_factory=lambda: ConcurrentStableList(
            [
                "/api/identity/v1/auth/login",
                "/api/identity/v1/auth/refresh",
                "/api/identity/v1/captcha",
                "/api/identity/v1/auth/sso",
                "/api/identity/v1/oidc",
            ]
        )
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

    scopes: Annotated[ConcurrentStableList[str], CONTRACT_COLLECTION] = Field(
        default_factory=lambda: ConcurrentStableList(["openid", "profile", "email"])
    )
    """请求 scope。"""

    discovery_cache_ttl: float = 3600.0
    """Discovery 元数据缓存 TTL（秒）。"""

    jwks_cache_ttl: float = 300.0
    """JWKS 缓存 TTL（秒）。"""

    cas_server_url: str = ""
    """CAS 服务基址（如 `https://<cas-host>/cas`；`provider="cas"` 时必填）。"""

    cas_login_path: str = "/login"
    """CAS 登录端点路径。"""

    cas_service_validate_path: str = "/p3/serviceValidate"
    """CAS 校验端点路径（3.0 `p3/serviceValidate` 含属性；2.0 用 `/serviceValidate`）。"""

    attribute_map: Annotated[ConcurrentStableDict[str, ConcurrentStableList[str]], CONTRACT_COLLECTION] = Field(
        default_factory=CONTRACT_STABLE_DICT
    )
    """CAS 属性映射覆盖（`{username|name|email: [候选属性名…]}`；空集用内置默认映射）。"""

    wecom_corp_id: str = ""
    """企业微信 CorpID（授权 `appid`；`provider="wecom"` 时必填）。"""

    wecom_agent_id: str = ""
    """企业微信应用 AgentID（扫码与 H5 授权携带）。"""

    wecom_secret: str = ""
    """企业微信应用密钥（空串；经 `BMS_IDENTITY_PROVIDER__WECOM_SECRET` 注入）。"""

    wecom_mode: str = "qr"
    """企业微信授权形态（`qr` PC 扫码 / `oauth` 内嵌 H5 网页授权）。"""

    wecom_login_url: str = "https://login.work.weixin.qq.com/wwlogin/sso/login"
    """企业微信扫码登录入口。"""

    wecom_oauth_url: str = "https://open.weixin.qq.com/connect/oauth2/authorize"
    """企业微信内嵌 H5 网页授权入口。"""

    wecom_api_base_url: str = "https://qyapi.weixin.qq.com"
    """企业微信服务端接口基址。"""

    wecom_scope: str = "snsapi_base"
    """企业微信网页授权 scope（`mode=oauth`）。"""

    wecom_login_type: str = "CorpApp"
    """企业微信扫码登录类型（`mode=qr`；`CorpApp` / `ServiceApp`）。"""

    dingtalk_client_id: str = ""
    """钉钉 Client ID / AppKey（`provider="dingtalk"` 时必填）。"""

    dingtalk_client_secret: str = ""
    """钉钉 Client Secret / AppSecret（空串；经 `BMS_IDENTITY_PROVIDER__DINGTALK_CLIENT_SECRET` 注入）。"""

    dingtalk_login_url: str = "https://login.dingtalk.com/oauth2/auth"
    """钉钉新版 OAuth2 授权入口。"""

    dingtalk_api_base_url: str = "https://api.dingtalk.com"
    """钉钉新版服务端接口基址。"""

    dingtalk_scope: str = "openid"
    """钉钉授权 scope（`openid` / `openid corpid`）。"""

    dingtalk_prompt: str = "consent"
    """钉钉授权确认方式。"""


class ServiceTokenSettings(PluginSelection):
    """服务 JWT 自签配置（`[service_token]`；私钥只走环境变量 / Secret，不写入配置文件）。"""

    issuer: str = "bms"
    """自签签发方（服务 JWT `iss`；生产建议配置稳定 URI）。"""

    ttl_seconds: int = Field(default=300, ge=1)
    """服务 JWT 默认有效期（秒；短时令牌）。"""

    active_kid: str = ""
    """当前签名密钥 kid（多把签名私钥时必填）。"""

    keys: Annotated[ConcurrentStableDict[str, TokenKeySettings], CONTRACT_COLLECTION] = Field(
        default_factory=CONTRACT_STABLE_DICT
    )
    """密钥集（kid → 密钥材料）；空集允许（仅校验方时只需公钥，签发时无可用私钥才拒）。"""


class LoginSettings(BaseSettings):
    """本地登录防爆破与验证码强制配置（`[login]`；阈值 / 窗口，敏感项无）。

    口径与《架构设计 · 认证与会话》「密码与账号策略」节一致（5 次失败锁 15 分钟、连续失败 3 次强制
    验证码）；后续按租户 `sys_config` 覆盖归账号治理阶段（03_04 / 03_07）。
    """

    max_failures: int = Field(default=5, ge=1)
    """连续失败锁定阈值（达到即锁定账号）。"""

    lock_seconds: int = Field(default=900, ge=1)
    """账号锁定时长（秒，默认 15 分钟）。"""

    ip_rate_limit: int = Field(default=60, ge=1)
    """每 IP 每分钟登录请求上限（限流基座）。"""

    account_rate_limit: int = Field(default=20, ge=1)
    """每账号每分钟登录请求上限（限流基座）。"""

    cookie_secure: bool = True
    """refresh cookie 是否带 `Secure`（生产 true；dev 经 `config.dev.toml` 关以支持 http 本地联调）。"""


class SessionSettings(BaseSettings):
    """会话治理配置（`[session]`；多端并发上限）。

    口径与《架构设计 · 认证与会话》「会话管理」节一致（活跃会话上限默认 5，超限自动作废最旧会话）；
    租户级 `sys_config` 覆盖归后续阶段，本期取平台默认。
    """

    max_active: int = Field(default=5, ge=1)
    """同一账号活跃会话上限（登录成功后超限自动作废最旧会话）。"""

    device_check: bool = False
    """每请求是否校验设备 / IP 一致性（可选强度；开启时比对会话标记内 `ip` / `ua` 与当前请求）。"""


class PasswordResetSettings(BaseSettings):
    """找回密码配置（`[password_reset]`；token TTL 与限流阈值）。

    口径与《架构设计 · 认证与会话》「密码与账号策略」节一致（token TTL 15 分钟、单次有效；
    每账号 1 次 / 5 分钟、每 IP 5 次 / 小时）；按租户 `sys_config` 覆盖归后续阶段，本期取平台默认。
    """

    token_ttl_seconds: int = Field(default=900, ge=60)
    """重置 token 有效期（秒，默认 15 分钟）。"""

    account_rate_limit: int = Field(default=1, ge=1)
    """每账号（标识 / 用户维度）窗口内找回请求上限。"""

    account_rate_window: int = Field(default=300, ge=1)
    """账号维度限流窗口（秒，默认 5 分钟）。"""

    ip_rate_limit: int = Field(default=5, ge=1)
    """每 IP 窗口内找回请求上限。"""

    ip_rate_window: int = Field(default=3600, ge=1)
    """IP 维度限流窗口（秒，默认 1 小时）。"""

    reset_url: str = ""
    """重置页基址（`{reset_url}?token=…&tenant=…`；空串 = 通知内容回退纯令牌文案）。"""


class SsoSettings(BaseSettings):
    """SSO 登录链路配置（`[sso]`；流程状态 TTL / 跳转地址 / 限流 / PKCE / 回调基址）。

    口径与《详细设计 · SSO 登录完整链路》「配置契约」节一致：跳转地址**只取配置**（防开放重定向），
    `pkce` 默认强制 S256；阈值后续按租户 `sys_config` 覆盖留待。
    """

    state_ttl_seconds: int = Field(default=300, ge=1)
    """state / nonce / PKCE 流程状态 TTL（秒；一次性消费，过期即回调失败）。"""

    success_redirect: str = ""
    """回调成功前端地址（空 = 回退 JSON 响应，联调便利）。"""

    failure_redirect: str = ""
    """回调失败前端地址（空 = 回退统一 JSON 错误体）。"""

    ip_rate_limit: int = Field(default=60, ge=1)
    """每 IP 每分钟 authorize / callback 请求上限（限流基座）。"""

    provider_rate_limit: int = Field(default=60, ge=1)
    """每 IdP 每分钟 authorize 请求上限（限流基座）。"""

    pkce: bool = True
    """是否强制 PKCE（S256；不支持的 IdP 以协议适配层处理，不做全局关闭）。"""

    callback_base_url: str = "http://localhost:8000"
    """回调地址基址（派生 `redirect_uri`；网关形态经行 `config.redirect_uri` 覆盖）。"""

    jit_enabled: bool = False
    """JIT 自动建号全局开关（IdP 行 `config.jit_enabled` 缺配时回落；缺省关闭，需显式开启）。"""

    jit_allowed_tenants: Annotated[ConcurrentStableList[str], CONTRACT_COLLECTION] = Field(
        default_factory=CONTRACT_STABLE_LIST
    )
    """JIT 租户白名单（空 = 不限制；非空时仅列内租户可自动建号）。"""

    jit_lock_ttl_seconds: int = Field(default=30, ge=1)
    """JIT 临界区分布式锁 TTL（秒）。"""

    jit_lock_wait_seconds: float = Field(default=5.0, ge=0)
    """JIT 临界区取锁等待时长（秒；0 = 不等待）。"""


class IdpManageSettings(BaseSettings):
    """外部 IdP 配置管理面配置（`[idp_manage]`；连通性测试限流与出站 URL 内网放行）。

    `allow_private_hosts` 为 `false` 时出站 URL（OIDC `issuer` / CAS `cas_server_url` / 企微与钉钉
    `api_base_url`）拒绝内网 / 回环 / 链路本地 / 元数据地址（SSRF）；企业自建内网 IdP 场景显式开启。
    """

    test_rate_limit: int = Field(default=10, ge=1)
    """连通性测试限流：每租户 + 操作者每分钟上限（防滥用）。"""

    allow_private_hosts: bool = False
    """出站 URL 是否允许私网 / 回环主机（企业内网 IdP 开启；生产默认关闭）。"""


class UserTokenSettings(PluginSelection):
    """用户令牌自签配置（`[user_token]`；密钥与 TTL 归 `[security]`，本分区只放选择与签发方）。"""

    issuer: str = "bms"
    """自签签发方（用户令牌 `iss`；与服务令牌同源标识，生产建议配置稳定 URI）。"""


class OidcProviderSettings(PluginSelection):
    """OIDC Provider 配置（`[oidc_provider]`；BMS 兼作 IdP 的 issuer / TTL / 未登录跳转）。

    密钥与算法沿用 `[security].keys`（`usr-` 前缀）；`issuer` 为 ID Token / access token 的 `iss`
    与四端点派生基点，可含 `{tenant}` 占位（生产按租户子域派生，dev 无占位则全租户同名）。
    """

    issuer: str = "http://localhost:8000/api/v1/oidc"
    """签发方（可含 `{tenant}` 占位；Discovery / 令牌 `iss` 与四端点据此派生）。"""

    authorization_code_ttl_seconds: int = Field(default=60, ge=1)
    """授权码一次性 TTL（秒）。"""

    id_token_ttl_seconds: int = Field(default=300, ge=1)
    """ID Token 有效期（秒）。"""

    access_token_ttl_seconds: int = Field(default=300, ge=1)
    """IdP access token 有效期（秒）。"""

    login_url: str = ""
    """`/authorize` 未登录跳转的前端登录页（空 = 直接 401；只取配置，防开放重定向）。"""


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

    db_keys: Annotated[ConcurrentStableList[str], CONTRACT_COLLECTION] = Field(default_factory=CONTRACT_STABLE_LIST)
    """后台轮询库键；空 = 平台库 + 引擎注册表活跃租户库键。"""


class ConsistencyBarrierSettings(PluginSelection):
    """一致性屏障配置（`[consistency_barrier]`；在能力选择之外追加等待 / 轮询参数）。"""

    default_timeout_ms: int = Field(default=3000, ge=1)
    """默认等待超时（毫秒）；超时抛 `ConsistencyBarrierTimeout`。"""

    default_poll_ms: int = Field(default=100, ge=1)
    """默认轮询间隔（毫秒）。"""


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

    # bare-collections:allow（pydantic-settings 配置源契约：须内置 dict，deep_update 依赖 dict.copy）
    def __call__(self) -> dict[str, Any]:
        """返回 `app.env` 覆盖。

        Returns:
            dict[str, Any]: 仅含生效环境的嵌套字典。
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
    config_cache_region: PluginSelection = Field(default_factory=PluginSelection)
    config_source: PluginSelection = Field(default_factory=PluginSelection)
    consistency_barrier: ConsistencyBarrierSettings = Field(default_factory=ConsistencyBarrierSettings)
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
    idp_manage: IdpManageSettings = Field(default_factory=IdpManageSettings)
    idp_state_store: PluginSelection = Field(default_factory=PluginSelection)
    importer: PluginSelection = Field(default_factory=PluginSelection)
    llm_provider: PluginSelection = Field(default_factory=PluginSelection)
    login: LoginSettings = Field(default_factory=LoginSettings)
    masking: PluginSelection = Field(default_factory=PluginSelection)
    metrics: PluginSelection = Field(default_factory=PluginSelection)
    multipart_upload: PluginSelection = Field(default_factory=PluginSelection)
    notifier: PluginSelection = Field(default_factory=PluginSelection)
    notification_center: PluginSelection = Field(default_factory=PluginSelection)
    oauth_server: PluginSelection = Field(default_factory=PluginSelection)
    oidc_provider: OidcProviderSettings = Field(default_factory=OidcProviderSettings)
    outbox: OutboxSettings = Field(default_factory=OutboxSettings)
    outbox_store: PluginSelection = Field(default_factory=PluginSelection)
    password_policy: PluginSelection = Field(default_factory=PluginSelection)
    password_hasher: PluginSelection = Field(default_factory=PluginSelection)
    password_reset: PasswordResetSettings = Field(default_factory=PasswordResetSettings)
    permission: PermissionSettings = Field(default_factory=PermissionSettings)
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
    session: SessionSettings = Field(default_factory=SessionSettings)
    session_security: PluginSelection = Field(default_factory=PluginSelection)
    session_store: PluginSelection = Field(default_factory=PluginSelection)
    sharding: PluginSelection = Field(default_factory=PluginSelection)
    sso: SsoSettings = Field(default_factory=SsoSettings)
    storage: PluginSelection = Field(default_factory=PluginSelection)
    task: PluginSelection = Field(default_factory=PluginSelection)
    tenant_membership: TenantMembershipSettings = Field(default_factory=TenantMembershipSettings)
    tenant_self_service: PluginSelection = Field(default_factory=PluginSelection)
    token_codec: PluginSelection = Field(default_factory=PluginSelection)
    token_verifier: PluginSelection = Field(default_factory=PluginSelection)
    tracer: TracerSettings = Field(default_factory=TracerSettings)
    translator: PluginSelection = Field(default_factory=PluginSelection)
    user_token: UserTokenSettings = Field(default_factory=UserTokenSettings)
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
    lines: ConcurrentStableList[str] = ConcurrentStableList()
    for item in error.errors():
        path = ".".join(str(part) for part in item["loc"]) or "(根)"
        lines.add(f"{path}：{item['msg']}")
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
