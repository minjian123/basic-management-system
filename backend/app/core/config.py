"""core 层配置基座：分区模型与读取接口（结构占位）。

- 占位实现返回默认值，**不读 `config.toml` / 环境变量**；真实读取、`BMS_` 覆盖、
  `BMS_ENV` 分层与启动校验由 03-1 配置管理落地后回填本基座登记。
- 所有模型继承 `BaseSchema`（纳入基类体系，稳定序列化）。
"""

from functools import lru_cache
from typing import Literal

from pydantic import ConfigDict, Field

from app.schemas.base import BaseSchema


class BaseSettings(BaseSchema):
    """配置分区公共基：拒绝未知键、允许字段名填充（继承 BaseSchema 公共配置）。"""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class AppSettings(BaseSettings):
    """应用元信息。"""

    name: str = "BMS 基础管理系统"
    env: Literal["dev", "test", "prod"] = "dev"
    debug: bool = True


class ServerSettings(BaseSettings):
    """HTTP 服务。"""

    host: str = "0.0.0.0"
    port: int = 8000
    workers: int = 1


class LogSettings(BaseSettings):
    """日志（真实实现见 03-2）。"""

    level: str = "DEBUG"
    format: str = "console"
    slow_request_ms: int = 1000


class DbPoolSettings(BaseSettings):
    """数据库连接池参数。"""

    pool_size: int = 5
    max_overflow: int = 10
    pool_timeout: float = 30.0
    pool_recycle: int = 1800


class DatabaseTargetSettings(BaseSettings):
    """单个数据库目标（url 不含密码；密码经环境变量注入）。"""

    url: str = ""
    replicas: list[str] = Field(default_factory=list)
    pool: DbPoolSettings = Field(default_factory=DbPoolSettings)


class DatabaseSettings(BaseSettings):
    """三库目标（平台 / 租户 / 归档；dev 默认多 SQLite 文件）。"""

    platform: DatabaseTargetSettings = Field(
        default_factory=lambda: DatabaseTargetSettings(url="sqlite+aiosqlite:///./bms_platform.db")
    )
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
    """对象存储（占位）。"""

    endpoint: str = ""
    access_key: str = ""
    secret_key: str = ""
    bucket: str = "bms"
    secure: bool = False


class SecuritySettings(BaseSettings):
    """安全（占位；真实实现随认证阶段）。"""

    secret_key: str = ""
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60


class CorsSettings(BaseSettings):
    """跨域。"""

    allow_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])
    allow_methods: list[str] = Field(default_factory=lambda: ["*"])
    allow_headers: list[str] = Field(default_factory=lambda: ["*"])
    allow_credentials: bool = True


class Settings(BaseSettings):
    """应用配置（占位：默认值，不读文件 / 环境变量）。"""

    app: AppSettings = Field(default_factory=AppSettings)
    server: ServerSettings = Field(default_factory=ServerSettings)
    log: LogSettings = Field(default_factory=LogSettings)
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    minio: MinioSettings = Field(default_factory=MinioSettings)
    security: SecuritySettings = Field(default_factory=SecuritySettings)
    cors: CorsSettings = Field(default_factory=CorsSettings)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """取应用配置（占位：返回默认值；真实读取由 03-1 接入）。

    Returns:
        Settings: 应用配置单例。
    """
    return Settings()
