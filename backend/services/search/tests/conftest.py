"""检索 服务 pytest 夹具：仅保留服务专属接线。

公共夹具（配置隔离 / 平台库 / 请求上下文 / 插件注册表）由测试公共基座
`bms_core.testing` 提供（13_04）；本文件保留服务专属的令牌密钥 / fakeredis 接线、
租户源替身与应用 / 客户端夹具。
"""

import asyncio
from collections.abc import AsyncIterator, Iterator

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from bms_core.core.config import get_settings
from bms_core.testing.fixtures import (
    clear_tenant_cache,
    platform_db,
    reset_request_context,
)
from bms_core.testing.fixtures import (
    isolate_settings as bms_isolate_settings,
)

__all__ = ("bms_isolate_settings", "platform_db", "reset_request_context")
from bms_search.main import ApplicationFactory
from ops.seed_tenant import seed_tenants
from tests_support.auth import auth_headers, configure_token_env
from tests_support.tenant_source import install_fake_tenant_source


@pytest.fixture(autouse=True)
def _plugin_fixtures(  # pyright: ignore[reportUnusedFunction]
    platform_db: None, reset_request_context: None, reset_plugin_registry: None
) -> None:
    """启用测试公共基座的公共夹具（平台库 / 请求上下文 / 插件注册表复位）。

    夹具实现单源在 `bms_core.testing.fixtures`；本包装只负责在本套件启用
    （交易服务单测不依赖平台库，故不启用）。
    """


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
    """会话级平台库：临时 `sys_tenant` 种子库（整个测试会话只建一次）。

    Args:
        tmp_path_factory: pytest 临时目录工厂。

    Returns:
        str: 会话级平台库连接串。
    """
    platform_url = f"sqlite+aiosqlite:///{tmp_path_factory.mktemp('platform') / 'app.db'}"
    asyncio.run(seed_tenants(platform_url))
    return platform_url


@pytest.fixture(autouse=True)
def fake_tenant_source(monkeypatch: pytest.MonkeyPatch) -> None:
    """租户源替身：应用装配时改注入 `FakeTenantSource`。

    Args:
        monkeypatch: pytest monkeypatch 夹具。
    """
    install_fake_tenant_source(monkeypatch)


@pytest.fixture
async def service_app() -> AsyncIterator[FastAPI]:
    """服务应用实例（经 lifespan 装配）。

    Yields:
        FastAPI: 应用实例。
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
    """ASGITransport 异步客户端（带认证头）。

    Args:
        service_app: 应用实例。

    Yields:
        AsyncClient: 测试客户端。
    """
    async with AsyncClient(transport=ASGITransport(app=service_app), base_url="http://test") as c:
        c.headers.update(auth_headers())
        yield c
