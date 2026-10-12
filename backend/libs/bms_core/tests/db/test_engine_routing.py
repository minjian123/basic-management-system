"""引擎主 / 副本多绑定与请求上下文选引擎测试（Kiwi 984）。"""

from collections.abc import Awaitable, Callable
from types import SimpleNamespace
from typing import Annotated, cast

import pytest
from fastapi import Depends, FastAPI, Request, Response
from httpx import ASGITransport, AsyncClient
from sqlalchemy import Engine
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

import bms_core.api.deps as deps_module
from bms_core.api.deps import get_config_service, get_primary_health, get_tenant_source
from bms_core.api.errors import register_exception_handlers
from bms_core.api.middleware import ReadOnlyMiddleware
from bms_core.config.service import ConfigService
from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.config import Settings
from bms_core.core.exceptions import ConfigError
from bms_core.db.engine import EngineFactory
from bms_core.db.health import PrimaryHealth
from bms_core.db.registry import EngineRegistry
from bms_core.db.session import SessionFactory, get_db, get_platform_read_db, get_read_db, get_write_db

_MEMORY = "sqlite+aiosqlite:///:memory:"


def _settings() -> Settings:
    """构造 SQLite 内存配置（平台库 + 单副本）。"""
    settings = Settings()
    settings.database.platform.url = _MEMORY
    settings.database.platform.replicas = ConcurrentStableList([_MEMORY])
    return settings


@pytest.mark.kiwi_id(984)
def test_four_dialect_names() -> None:
    """四库方言识别：MySQL / PostgreSQL / 达梦 / SQLite。"""
    assert make_url("mysql+aiomysql://u@h/db").get_backend_name() == "mysql"
    assert make_url("postgresql+psycopg://u@h/db").get_backend_name() == "postgresql"
    assert make_url("dm+dmPython://u:p@h:5236/db").get_backend_name() == "dm"
    assert make_url("sqlite+aiosqlite:///./x.db").get_backend_name() == "sqlite"


@pytest.mark.kiwi_id(984)
async def test_write_and_read_binding_round_robin() -> None:
    """写取主引擎并缓存；只读轮询副本；副本列表可读。"""
    settings = _settings()
    settings.database.platform.replicas = ConcurrentStableList([_MEMORY, _MEMORY])
    factory = EngineFactory(settings)
    write = factory.create("platform")
    assert isinstance(write, AsyncEngine)
    assert factory.create("platform") is write

    first = factory.create("platform", read_only=True)
    second = factory.create("platform", read_only=True)
    assert first is not second
    assert first is not write
    assert factory.create("platform", read_only=True) is first
    assert factory.replicas("platform") == [_MEMORY, _MEMORY]
    await factory.aclose()


@pytest.mark.kiwi_id(984)
async def test_read_falls_back_to_write_without_replicas() -> None:
    """无副本时只读回落主引擎。"""
    settings = Settings()
    settings.database.platform.url = _MEMORY
    settings.database.platform.replicas = ConcurrentStableList([])
    factory = EngineFactory(settings)
    write = factory.create("platform")
    assert factory.create("platform", read_only=True) is write
    await factory.aclose()


@pytest.mark.kiwi_id(984)
async def test_dm_sync_only_dialect() -> None:
    """达梦：异步 create 抛 ConfigError；同步 create_sync 可建引擎。"""
    settings = Settings()
    settings.database.platform.url = "dm+dmPython://bms_dev:pw@localhost:5236/bms_dev"
    factory = EngineFactory(settings)
    with pytest.raises(ConfigError):
        factory.create("platform")
    sync_engine = factory.create_sync("platform")
    assert isinstance(sync_engine, Engine)
    # 达梦连接串方言归一为自定义 XA 方言 `dmxa`（全部达梦连接改走，见 db/dialects/dm_xa.py）
    assert sync_engine.dialect.name == "dmxa"
    assert factory.create_sync("platform") is sync_engine
    await factory.drop("platform")
    assert factory.create_sync("platform") is not sync_engine
    await factory.aclose()


async def _build_app(factory: EngineFactory, *, read_middleware: bool = False) -> FastAPI:
    """构造装配了注册表 / 会话工厂 / 主库状态的测试应用。"""
    app = FastAPI()
    if read_middleware:
        app.add_middleware(ReadOnlyMiddleware)
    register_exception_handlers(app)
    registry = EngineRegistry(factory)
    app.state.engine_registry = registry
    app.state.session_factory = SessionFactory()
    app.state.primary_health = PrimaryHealth(factory)

    @app.get("/marker")
    # bare-collections:allow（FastAPI 端点返回注解）
    async def _marker(session: Annotated[AsyncSession, Depends(get_db)]) -> dict[str, int]:  # pyright: ignore[reportUnusedFunction]
        return {"bind": id(session.bind)}

    @app.post("/marker")
    # bare-collections:allow（FastAPI 端点返回注解）
    async def _marker_write(session: Annotated[AsyncSession, Depends(get_db)]) -> dict[str, int]:  # pyright: ignore[reportUnusedFunction]
        return {"bind": id(session.bind)}

    @app.get("/read")
    # bare-collections:allow（FastAPI 端点返回注解）
    async def _read(session: Annotated[AsyncSession, Depends(get_read_db)]) -> dict[str, int]:  # pyright: ignore[reportUnusedFunction]
        return {"bind": id(session.bind)}

    @app.get("/write")
    # bare-collections:allow（FastAPI 端点返回注解）
    async def _write(session: Annotated[AsyncSession, Depends(get_write_db)]) -> dict[str, int]:  # pyright: ignore[reportUnusedFunction]
        return {"bind": id(session.bind)}

    @app.get("/platform")
    # bare-collections:allow（FastAPI 端点返回注解）
    async def _platform(session: Annotated[AsyncSession, Depends(get_platform_read_db)]) -> dict[str, int]:  # pyright: ignore[reportUnusedFunction]
        return {"bind": id(session.bind)}

    @app.middleware("http")
    async def _inject_tenant(  # pyright: ignore[reportUnusedFunction]
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        """测试中间件：带 `X-Test-Tenant` 头时注入租户库上下文（对照平台库强制行为）。"""
        if request.headers.get("X-Test-Tenant"):
            request.scope.setdefault("state", {})["tenant"] = SimpleNamespace(db_key="tenant_demo")
        return await call_next(request)

    return app


@pytest.mark.kiwi_id(984)
async def test_request_context_selects_engine() -> None:
    """get_db 按只读标记选引擎；get_read_db / get_write_db 显式强制。"""
    factory = EngineFactory(_settings())
    app = await _build_app(factory, read_middleware=True)
    write_id = id(factory.create("platform"))
    read_id = id(factory.create("platform", read_only=True))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.get("/marker")).json() == {"bind": read_id}
        assert (await client.post("/marker")).json() == {"bind": write_id}
        assert (await client.get("/read")).json() == {"bind": read_id}
        assert (await client.get("/write")).json() == {"bind": write_id}

    request = cast("Request", SimpleNamespace(app=app))
    assert get_primary_health(request) is app.state.primary_health
    await app.state.engine_registry.aclose()


@pytest.mark.kiwi_id(984)
def test_tenant_source_provider_reads_app_state() -> None:
    """`get_tenant_source`：直接取应用装配的租户源实例（契约类型）。"""
    source = object()
    request = cast(
        "Request",
        SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(tenant_source=source))),
    )
    assert get_tenant_source(request) is source


@pytest.mark.kiwi_id(984)
def test_config_service_provider_wires_engines_and_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    """`get_config_service`：请求级组装引擎注册表 + 配置缓存域。"""
    from bms_core.config.cache import MemoryConfigCacheRegion

    cache = MemoryConfigCacheRegion()

    def _cache_region(request: Request) -> MemoryConfigCacheRegion:
        """替身：恒定返回注入的缓存域。

        Args:
            request: 请求对象（忽略）。

        Returns:
            MemoryConfigCacheRegion: 缓存域实例。
        """
        del request
        return cache

    monkeypatch.setattr(deps_module, "get_config_cache_region", _cache_region)
    engines = object()
    request = cast(
        "Request",
        SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(engine_registry=engines))),
    )
    service = get_config_service(request)
    assert isinstance(service, ConfigService)


@pytest.mark.kiwi_id(984)
async def test_engine_kwargs_connect_timeout_branches() -> None:
    """建连超时分支：MySQL / PostgreSQL 附 `connect_args`；其余方言（含达梦）不附。"""
    settings = Settings()
    settings.database.platform.url = "mysql+aiomysql://bms@db:3306/bms_dev"
    factory = EngineFactory(settings)
    assert "connect_args" in factory._engine_kwargs(settings.database.platform, "mysql")  # pyright: ignore[reportPrivateUsage]
    assert "connect_args" in factory._engine_kwargs(settings.database.platform, "postgresql")  # pyright: ignore[reportPrivateUsage]
    dm_kwargs = factory._engine_kwargs(settings.database.platform, "dmxa")  # pyright: ignore[reportPrivateUsage]
    assert "connect_args" not in dm_kwargs
    assert dm_kwargs["pool_pre_ping"] is True


@pytest.mark.kiwi_id(984)
async def test_drop_skips_already_removed_engines() -> None:
    """`drop` 的并发回收防御：角色快照存在但条目已被移除时不重复 `dispose`（异步 / 同步两路）。"""
    factory = EngineFactory(Settings())
    # 模拟并发回收窗口：角色快照取自 `_engines` / `_sync_engines`，取回时条目已被移除
    factory._engines.set(("platform", "write"), cast("AsyncEngine", None))  # pyright: ignore[reportPrivateUsage]
    factory._sync_engines.set(("platform", "write"), cast("Engine", None))  # pyright: ignore[reportPrivateUsage]

    await factory.drop("platform")
    assert "platform" not in factory._engines  # pyright: ignore[reportPrivateUsage]
    await factory.aclose()


@pytest.mark.kiwi_id(2164)
async def test_platform_read_db_forces_platform_engine() -> None:
    """get_platform_read_db 带租户上下文时仍取平台库只读引擎；get_read_db 则命中租户库键（对照）。"""
    factory = EngineFactory(_settings())
    app = await _build_app(factory)
    platform_read_id = id(factory.create("platform", read_only=True))
    tenant_read_id = id(factory.create("tenant_demo", read_only=True))
    assert tenant_read_id != platform_read_id

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.get("/platform")).json() == {"bind": platform_read_id}
        assert (await client.get("/platform", headers={"X-Test-Tenant": "1"})).json() == {"bind": platform_read_id}
        assert (await client.get("/read", headers={"X-Test-Tenant": "1"})).json() == {"bind": tenant_read_id}

    await app.state.engine_registry.aclose()
