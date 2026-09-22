"""租户数据拓扑测试（Kiwi 1019）：模板解析 / 会话按租户路由 / 物理隔离 / 租户过滤钩子。"""

from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, cast

import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from bms_core.api.middleware import TenantMiddleware
from bms_core.core.config import Settings
from bms_core.core.context import (
    reset_current_tenant,
    reset_tenant_context,
    set_current_tenant,
    set_tenant_context,
)
from bms_core.core.exceptions import ConfigError
from bms_core.db.engine import EngineFactory
from bms_core.db.registry import EngineRegistry
from bms_core.db.session import SessionFactory, get_db, get_read_db, get_uow, get_write_db
from bms_core.db.tenant import TenantContext
from bms_core.repositories.base_memory_repository import BaseMemoryRepository


class _Source:
    """内存租户源替身（单演示租户）。"""

    def __init__(self, tenants: list[TenantContext]) -> None:
        self.tenants = {tenant.tenant_code: tenant for tenant in tenants}

    async def by_code(self, code: str) -> TenantContext:
        """按编码取租户。"""
        from bms_core.core.exceptions import TenantNotFoundError

        tenant = self.tenants.get(code)
        if tenant is None:
            raise TenantNotFoundError(f"未知租户：{code}")
        return tenant

    async def by_domain(self, domain: str) -> TenantContext:
        """按子域名取租户。"""
        for tenant in self.tenants.values():
            if tenant.domain == domain:
                return tenant
        from bms_core.core.exceptions import TenantNotFoundError

        raise TenantNotFoundError(f"未知租户域名：{domain}")


def _settings(tmp_path: Path) -> Settings:
    """构造临时平台库 + 租户库模板的配置（服务标识取启动期回写后的平台服务名）。"""
    settings = Settings()
    settings.app.service = "platform"
    settings.database.platform.url = f"sqlite+aiosqlite:///{tmp_path / 'platform.db'}"
    settings.database.tenants.url_template = f"sqlite+aiosqlite:///{tmp_path}/bms_tenant_{{tenant}}.db"
    return settings


@pytest.mark.kiwi_id(1019)
def test_tenant_url_template_resolution(tmp_path: Path) -> None:
    """租户库键经模板解析（service / tenant / database）；空模板回落单库；非法键报错。"""
    settings = _settings(tmp_path)
    factory = EngineFactory(settings)
    engine = factory.create("tenant_demo")
    assert str(engine.url).endswith("bms_tenant_demo.db")

    settings.database.tenants.url_template = "sqlite+aiosqlite:///{database}.db"
    assert str(factory.create("tenant_acme").url).endswith("bms_platform_acme.db")

    settings.database.tenants.url_template = ""
    fallback = EngineFactory(settings).create("tenant_demo")
    assert str(fallback.url).endswith("bms_tenant_demo.db")  # 回落 database.tenants.url

    with pytest.raises(ConfigError):
        EngineFactory(settings).create("tenant_")

    illegal = _settings(tmp_path)
    illegal.database.tenants.url_template = "sqlite+aiosqlite:///{unknown}.db"
    with pytest.raises(ConfigError):
        EngineFactory(illegal).create("tenant_demo")


@pytest.mark.kiwi_id(1019)
async def test_session_routes_by_tenant_db_key(tmp_path: Path) -> None:
    """`get_db` / `get_read_db` / `get_write_db` / `get_uow` 按请求租户库键取引擎；无租户回落平台库。"""
    settings = _settings(tmp_path)
    settings.tenant.allow_demo_fallback = False
    settings.tenant.exempt_paths = ["/platform-db"]
    registry = EngineRegistry(EngineFactory(settings))
    source = _Source([TenantContext(tenant_code="demo", db_key="tenant_demo", name="演示租户")])

    app = FastAPI()
    app.state.settings = settings
    app.state.engine_registry = registry
    app.state.session_factory = SessionFactory()
    app.state.tenant_source = source
    app.add_middleware(TenantMiddleware)

    def _bind_name(session: AsyncSession) -> str:
        return str(cast("AsyncEngine", session.bind).url).rsplit("/", 1)[-1]

    @app.get("/api/v1/db")
    async def db(session: Annotated[AsyncSession, Depends(get_db)]) -> dict[str, str]:  # pyright: ignore[reportUnusedFunction]
        return {"bind": _bind_name(session)}

    @app.get("/api/v1/read")
    async def read(session: Annotated[AsyncSession, Depends(get_read_db)]) -> dict[str, str]:  # pyright: ignore[reportUnusedFunction]
        return {"bind": _bind_name(session)}

    @app.get("/api/v1/write")
    async def write(session: Annotated[AsyncSession, Depends(get_write_db)]) -> dict[str, str]:  # pyright: ignore[reportUnusedFunction]
        return {"bind": _bind_name(session)}

    @app.get("/api/v1/uow")
    async def uow(unit: Annotated[object, Depends(get_uow)]) -> dict[str, str]:  # pyright: ignore[reportUnusedFunction]
        session = cast("AsyncSession | None", getattr(unit, "session", None))
        assert session is not None
        return {"bind": _bind_name(session)}

    @app.get("/platform-db")
    async def platform(session: Annotated[AsyncSession, Depends(get_db)]) -> dict[str, str]:  # pyright: ignore[reportUnusedFunction]
        return {"bind": _bind_name(session)}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        for path in ("/api/v1/db", "/api/v1/read", "/api/v1/write", "/api/v1/uow"):
            response = await client.get(path, headers={"X-Tenant-ID": "demo"})
            assert response.status_code == 200
            assert response.json()["bind"] == "bms_tenant_demo.db", path

        exempt = await client.get("/platform-db", headers={"X-Tenant-ID": "demo"})
        assert exempt.json()["bind"] == "platform.db"

        unknown = await client.get("/api/v1/db", headers={"X-Tenant-ID": "nope"})
        assert unknown.status_code == 404

    await registry.aclose()


@pytest.mark.kiwi_id(1019)
async def test_cross_tenant_physical_isolation(tmp_path: Path) -> None:
    """跨租户物理隔离：租户 A 写入在租户 B 库不可见（各自独立库文件）。"""
    settings = _settings(tmp_path)
    registry = EngineRegistry(EngineFactory(settings))
    try:
        engine_a = await registry.get("tenant_demo")
        engine_b = await registry.get("tenant_acme")
        assert engine_a is not engine_b

        for engine in (engine_a, engine_b):
            async with engine.begin() as connection:
                await connection.execute(
                    text("CREATE TABLE demo_note (id INTEGER PRIMARY KEY, tenant_id INTEGER, note TEXT)")
                )
        async with async_sessionmaker(engine_a, expire_on_commit=False)() as session:
            await session.execute(text("INSERT INTO demo_note (id, tenant_id, note) VALUES (1, 1, 'demo-note')"))
            await session.commit()
        async with async_sessionmaker(engine_b, expire_on_commit=False)() as session:
            rows = (await session.execute(text("SELECT note FROM demo_note WHERE id = 1"))).all()
        assert rows == []
    finally:
        await registry.aclose()


@dataclass
class _Note:
    """租户维度记录（隔离过滤用例实体）。"""

    id: int
    tenant_id: int
    deleted_at: str | None = None


class _NoteRepo(BaseMemoryRepository[_Note]):
    """租户过滤内存仓储（`tenant_scoped=True`）。"""

    tenant_scoped = True

    def _build(self, item_id: int, values: dict[str, object]) -> _Note:
        return _Note(
            id=item_id,
            tenant_id=int(cast("int", values.get("tenant_id", 0))),
            deleted_at=cast("str | None", values.get("deleted_at")),
        )

    def _apply(self, item: _Note, values: dict[str, object]) -> _Note:
        return _Note(
            id=item.id,
            tenant_id=int(cast("int", values.get("tenant_id", item.tenant_id))),
            deleted_at=cast("str | None", values.get("deleted_at", item.deleted_at)),
        )


class _PlainRepo(_NoteRepo):
    """未启用租户隔离的仓储（对照：不注入租户条件）。"""

    tenant_scoped = False


@pytest.mark.kiwi_id(1019)
async def test_tenant_filter_condition_injection() -> None:
    """租户过滤钩子：条件次序（软删除 → 租户）、上下文主键驱动、未启用 / 无主键不注入。"""
    repo = _NoteRepo()
    await repo.create(tenant_id=1)
    await repo.create(tenant_id=2)

    token = set_tenant_context(TenantContext(tenant_code="demo", db_key="tenant_demo", name="演示租户", tenant_id=1))
    try:
        assert [item.tenant_id for item in await repo.list()] == [1]
        assert await repo.count() == 1
    finally:
        reset_tenant_context(token)

    assert await repo.count() == 2  # 无租户上下文：不注入（物理库隔离为第一层）

    code_token = set_current_tenant("demo")
    try:
        assert await repo.count() == 2  # 上下文无主键：不注入
    finally:
        reset_current_tenant(code_token)

    plain = _PlainRepo()
    await plain.create(tenant_id=1)
    await plain.create(tenant_id=2)
    token = set_tenant_context(TenantContext(tenant_code="demo", db_key="tenant_demo", name="演示租户", tenant_id=1))
    try:
        assert await plain.count() == 2  # 未启用租户隔离：不注入
    finally:
        reset_tenant_context(token)
