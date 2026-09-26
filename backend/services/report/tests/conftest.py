"""pytest 公共夹具：ASGI 内存客户端（免启服务器）+ 配置环境隔离 + 平台库租户种子。"""

import asyncio
import os
from collections.abc import AsyncIterator, Iterator

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from bms_core.cache.memory import MemoryCacheRegion
from bms_core.core.config import Settings, get_settings
from bms_core.core.context import (
    current_client_ip,
    current_request_id,
    current_tenant,
    current_tenant_context_var,
    current_trace_id,
    current_user_id,
)
from bms_report.main import ApplicationFactory
from ops.seed_tenant import seed_tenants


@pytest.fixture(autouse=True)
def isolate_settings(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """隔离配置：清除 `BMS_` 环境变量与 `.env` 读取，重置配置单例。

    Args:
        monkeypatch: pytest monkeypatch 夹具。

    Yields:
        None: 用例运行期。
    """
    for key in list(os.environ):
        if key.startswith("BMS_") and not key.startswith("BMS_TEST_"):
            monkeypatch.delenv(key, raising=False)
    # 测试会话固定关闭库连接串模板：dev 默认启用「每服务每租户」模板（06_01），
    # 会让用例显式指定的 `BMS_DATABASE__*__URL` 失效；模板行为由专门用例显式开启覆盖。
    monkeypatch.setenv("BMS_DATABASE__PLATFORM__URL_TEMPLATE", "")
    monkeypatch.setenv("BMS_DATABASE__TENANTS__URL_TEMPLATE", "")
    monkeypatch.setitem(Settings.model_config, "env_file", None)
    # 可观测真实 provider 关闭（08_01）：避免单元用例引入全局 TracerProvider / 后台导出线程与网络噪声；
    # 真实实现用例显式开启（monkeypatch 覆盖 provider / 端点或注入 in-memory exporter）。
    monkeypatch.setenv("BMS_METRICS__PROVIDER", "")
    monkeypatch.setenv("BMS_TRACER__PROVIDER", "")
    # 跨服务调用 / 会话存储 / 限流真实实现关闭（01_03）：单测不真实外呼、不连 Redis
    monkeypatch.setenv("BMS_SERVICE_CLIENT__PROVIDER", "")
    monkeypatch.setenv("BMS_SESSION_STORE__PROVIDER", "")
    monkeypatch.setenv("BMS_RATE_LIMITER__PROVIDER", "")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture(scope="session")
def platform_db_url(tmp_path_factory: pytest.TempPathFactory) -> str:
    """会话级平台库：临时 `sys_tenant` 种子库（建库 / 播种整个测试会话只做一次）。

    Returns:
        str: 会话级平台库连接串。
    """
    platform_url = f"sqlite+aiosqlite:///{tmp_path_factory.mktemp('platform') / 'app.db'}"
    asyncio.run(seed_tenants(platform_url))
    return platform_url


@pytest.fixture(autouse=True)
def platform_db(platform_db_url: str, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """平台库隔离：把平台库 URL 指向会话级种子库（用例间不重复建库，仅重置配置单例）。

    Yields:
        None: 用例运行期。
    """
    monkeypatch.setenv("BMS_DATABASE__PLATFORM__URL", platform_db_url)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def reset_request_context() -> Iterator[None]:
    """用例结束后复位请求上下文（链路 / 请求 / 来源 / 租户 / 用户），防跨用例污染。

    Yields:
        None: 用例运行期。
    """
    yield
    current_trace_id.set(None)
    current_request_id.set(None)
    current_client_ip.set(None)
    current_tenant.set(None)
    current_tenant_context_var.set(None)
    current_user_id.set(None)


def clear_tenant_cache(app: object) -> None:
    """清空应用租户源的进程内缓存 Region（进程级缓存实例，防跨用例残留）。

    Args:
        app: 应用实例（取 `state.tenant_source.cache`）。
    """
    state = getattr(app, "state", None)
    source = getattr(state, "tenant_source", None)
    cache = getattr(source, "cache", None)
    if isinstance(cache, MemoryCacheRegion):
        cache.clear()


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
        yield c
