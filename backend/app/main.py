"""BMS 应用工厂：中间件、异常处理、路由注册与 SQLite 自动建表。

启动方式：uv run uvicorn app.main:app --reload --port 8000
- 中间件：RequestContextMiddleware（request_id / 租户上下文 / 访问日志）
- 异常处理：BizError / 参数校验 / 未知异常 → 统一 {code, message, data}
- SQLite（dev/test）启动时 Base.metadata.create_all 自动建表（含 dev_tenants 演练租户库）；
  MySQL/PostgreSQL 必须走 Alembic 迁移，不在此建表
- Swagger/ReDoc 仅 debug 环境开启（生产关闭）
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import models
from .api.router import api_router
from .api.v1.health import router as health_router
from .core.config import Settings, get_settings
from .core.errors import (
    BizError,
    biz_error_handler,
    http_error_handler,
    internal_error_handler,
    validation_error_handler,
)
from .core.logging import configure_logging
from .core.middleware import RequestContextMiddleware
from .db.base import Base
from .db.engine import get_registry
from .db.redis import close_redis

_ = models  # 保持模型注册（副作用导入），确保 Base.metadata 完整（Alembic 与建表依赖）


def _ensure_sqlite_dir(url: str) -> None:
    """确保 SQLite 文件所在目录存在（相对路径基于 backend 工作目录解析）。"""
    prefix = "sqlite+aiosqlite:///"
    if not url.startswith(prefix):
        return
    rel = url.removeprefix(prefix)
    if not rel or rel.startswith(":"):
        return  # 内存库或无路径
    Path(rel).parent.mkdir(parents=True, exist_ok=True)


async def _create_sqlite_tables(settings: Settings) -> None:
    """开发/测试环境 SQLite 自动建表：平台库 + dev_tenants 预注册租户库。"""
    if not settings.database.platform_url.startswith("sqlite"):
        return
    _ensure_sqlite_dir(settings.database.platform_url)
    _ensure_sqlite_dir(settings.database.tenant_url_template.replace("{code}", "probe"))
    registry = get_registry()
    engine = await registry.get("platform")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    for code in settings.database.dev_tenants:
        tenant_engine = await registry.get(f"tenant:{code}")
        async with tenant_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动时配置日志与 SQLite 建表，关闭时释放引擎与 Redis。"""
    _ = app
    settings = get_settings()
    configure_logging(settings.log.level, settings.app.env)
    if settings.app.env != "prod":
        await _create_sqlite_tables(settings)
    yield
    await get_registry().dispose()
    await close_redis()


def create_app() -> FastAPI:
    """应用工厂：组装中间件、异常处理器与路由。"""
    settings = get_settings()
    app = FastAPI(
        title="BMS",
        version="0.1.0",
        debug=settings.app.debug,
        docs_url="/docs" if settings.app.debug else None,
        redoc_url="/redoc" if settings.app.debug else None,
        openapi_url="/openapi.json" if settings.app.debug else None,
        lifespan=lifespan,
    )
    app.add_middleware(RequestContextMiddleware)
    app.add_exception_handler(BizError, biz_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(StarletteHTTPException, http_error_handler)
    app.add_exception_handler(Exception, internal_error_handler)
    app.include_router(api_router)
    app.include_router(health_router)  # /healthz、/readyz（根路径，编排探针专用）
    return app


app = create_app()
