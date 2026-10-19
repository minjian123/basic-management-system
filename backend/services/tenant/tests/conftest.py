"""pytest 公共夹具：ASGI 内存客户端（免启服务器）+ 配置环境隔离 + 平台库租户种子。"""

import asyncio
from collections.abc import AsyncIterator, Iterator

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from bms_core.core.config import get_settings
from bms_core.testing.fixtures import (
    clear_tenant_cache,
    platform_db,
    reset_plugin_registry,
    reset_request_context,
)
from bms_core.testing.fixtures import (
    isolate_settings as bms_isolate_settings,
)

__all__ = ("bms_isolate_settings", "platform_db", "reset_plugin_registry", "reset_request_context")
from bms_tenant.main import ApplicationFactory
from ops.seed_tenant import seed_tenants
from tests_support.auth import auth_headers, configure_token_env
from tests_support.tenant_source import install_fake_tenant_source


@pytest.fixture(autouse=True)
def _plugin_fixtures(  # pyright: ignore[reportUnusedFunction]
    platform_db: None, reset_plugin_registry: None, reset_request_context: None
) -> None:
    """启用测试公共基座的公共夹具（平台库 / 插件注册表 / 请求上下文复位）。"""


@pytest.fixture(autouse=True)
def isolate_settings(bms_isolate_settings: None, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """服务专属隔离：在公共隔离之后追加 fakeredis 与测试令牌密钥。

    Args:
        bms_isolate_settings: 公共隔离夹具（保证顺序）。
        monkeypatch: pytest monkeypatch 夹具。

    Yields:
        None: 用例运行期。
    """
    from tests_support.redis import install_process_fake_redis_client

    install_process_fake_redis_client()
    configure_token_env(monkeypatch)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture(scope="session")
def platform_db_url(tmp_path_factory: pytest.TempPathFactory) -> str:
    """会话级平台库：临时 `sys_tenant` 种子库（建库 / 播种整个测试会话只做一次）。

    播种后把演示 / 示例租户主键对齐到测试租户源口径（`demo ↔ 1001` / `acme ↔ 2002`）——11_01 起
    用户↔租户可达关系表 `sys_user_tenant` 按雪花租户主键与 `sys_tenant` **同库 join**，主键须与
    令牌租户位（测试租户源口径）一致才能命中。

    Returns:
        str: 会话级平台库连接串。
    """
    platform_url = f"sqlite+aiosqlite:///{tmp_path_factory.mktemp('platform') / 'app.db'}"
    asyncio.run(seed_tenants(platform_url))
    asyncio.run(_align_tenant_ids(platform_url))
    return platform_url


async def _align_tenant_ids(platform_url: str) -> None:
    """把种子租户主键对齐到测试租户源口径（`demo → 1001` / `acme → 2002`；含库名对照行）。

    Args:
        platform_url: 平台库连接串。
    """
    for code, tenant_id in (("demo", 1001), ("acme", 2002)):
        engine = create_async_engine(platform_url)
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "UPDATE sys_tenant_database SET tenant_id = :new WHERE tenant_id = "
                    "(SELECT id FROM sys_tenant WHERE code = :code AND deleted_at IS NULL)"
                ),
                {"new": tenant_id, "code": code},
            )
            await connection.execute(
                text("UPDATE sys_tenant SET id = :new WHERE code = :code AND deleted_at IS NULL"),
                {"new": tenant_id, "code": code},
            )
        await engine.dispose()


@pytest.fixture(autouse=True)
def fake_tenant_source(monkeypatch: pytest.MonkeyPatch) -> None:
    """租户源替身：应用装配时改注入 `FakeTenantSource`（令牌主键经 `by_id` 可解析）。"""
    install_fake_tenant_source(monkeypatch)


@pytest.fixture
async def service_app() -> AsyncIterator[FastAPI]:
    """本服务应用实例夹具（经 lifespan 装配；供探针 / 应用级断言与 `client` 共用）。

    Yields:
        object: FastAPI 应用实例。
    """
    app = ApplicationFactory().create(None)
    clear_tenant_cache(app)
    try:
        async with app.router.lifespan_context(app):
            yield app
    finally:
        clear_tenant_cache(app)


@pytest.fixture
async def client(service_app: FastAPI) -> AsyncIterator[AsyncClient]:
    """ASGITransport 异步客户端夹具（复用 `service_app`）。

    平台库与租户种子由 autouse 的 `platform_db` 夹具提供；租户缓存用例前后清空。
    """
    async with AsyncClient(transport=ASGITransport(app=service_app), base_url="http://test") as c:
        c.headers.update(auth_headers())
        yield c
