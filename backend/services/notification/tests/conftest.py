"""通知 服务 pytest 夹具：仅保留服务专属接线。

公共夹具（配置隔离 / 平台库 / 请求上下文 / 插件注册表）由测试公共基座
`bms_core.testing` 提供（13_04）；本文件保留服务专属的令牌密钥 / fakeredis 接线、
租户源替身与应用 / 客户端夹具。
"""

import os
from collections.abc import AsyncIterator, Callable, Iterator
from pathlib import Path

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.config import get_settings
from bms_core.testing.fixtures import (
    apply_module_loop_scope,
    clear_tenant_cache,
    platform_db,
    reset_plugin_registry,
    reset_request_context,
)
from bms_core.testing.fixtures import (
    isolate_settings as bms_isolate_settings,
)
from bms_core.testing.fixtures import (
    isolated_env_module as bms_isolated_env_module,
)

__all__ = (
    "bms_isolate_settings",
    "bms_isolated_env_module",
    "platform_db",
    "reset_plugin_registry",
    "reset_request_context",
)
from bms_core.testing.system import AssembledSystem
from tests_support.auth import auth_headers, configure_token_env
from tests_support.tenant_source import install_fake_tenant_source, installed_fake_tenant_source


@pytest.fixture(autouse=True)
def _plugin_fixtures(  # pyright: ignore[reportUnusedFunction]
    platform_db: None, reset_request_context: None, reset_plugin_registry: None
) -> None:
    """启用测试公共基座的公共夹具（平台库 / 请求上下文 / 插件注册表复位）。

    夹具实现单源在 `bms_core.testing.fixtures`；本包装只负责在本套件启用
    （交易服务单测不依赖平台库，故不启用）。
    """


@pytest.fixture(autouse=True)
def _restore_assembled_app(  # pyright: ignore[reportUnusedFunction]
    service_app: FastAPI,
) -> Iterator[None]:
    """每例恢复装配态：依赖覆盖与配置快照都回到用例开始前。

    装配常驻（13_10）后 app 跨用例复用，用例直接写 `app.dependency_overrides[...]` 或就地改
    `app.state.settings.<段>.<字段>` 会把替身 / 改动留给后继用例。还原逻辑单源在
    `tests_support.app_state`。

    Args:
        service_app: 已装配的应用实例（会话级）。

    Yields:
        None: 用例运行期。
    """
    from tests_support.app_state import restore_assembled_app

    with restore_assembled_app(service_app):
        yield


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
def platform_db_prepare() -> Callable[[str], None]:
    """共享平台库准备集回调（子工程自成 rootdir 时的薄壳，实现单源在 `tests_support.shared_db`）。

    Returns:
        Callable[[str], None]: 接受连接串的准备函数。
    """
    from tests_support.shared_db import prepare_platform

    return prepare_platform


@pytest.fixture(scope="session")
def tenant_db_prepare() -> Callable[[str], None]:
    """共享租户库准备集回调（同上）。

    Returns:
        Callable[[str], None]: 接受连接串的准备函数。
    """
    from tests_support.shared_db import prepare_tenant

    return prepare_tenant


@pytest.fixture(scope="session")
def platform_db_url(shared_platform_db_url: str) -> str:
    """会话级平台库：**共享平台库**（04-6-2 单库化；建库 / 播种由准备集一次性负责）。

    Args:
        shared_platform_db_url: 共享平台库连接串（会话级）。

    Returns:
        str: 会话级平台库连接串。
    """
    return shared_platform_db_url


@pytest.fixture(autouse=True)
def fake_tenant_source(monkeypatch: pytest.MonkeyPatch) -> None:
    """租户源替身：应用装配时改注入 `FakeTenantSource`。

    Args:
        monkeypatch: pytest monkeypatch 夹具。
    """
    install_fake_tenant_source(monkeypatch)


@pytest.fixture(scope="module")
def notification_module_env(bms_isolated_env_module: None) -> Iterator[None]:
    """模块级服务环境：常驻装配的首个用例前就把 fakeredis / 令牌密钥 / 租户源替身就位。

    为什么需要：pytest 先建高作用域夹具，模块级 `service_app` 会早于函数级 `isolate_settings`
    执行；服务专属环境（假 Redis / 测试密钥 / 假租户源）必须同样按模块作用域先就位，
    否则应用会按真实 Redis 与真实租户源装配。

    Args:
        bms_isolated_env_module: 基座模块级隔离环境（保证顺序）。

    Yields:
        None: 模块运行期。
    """
    from tests_support.redis import install_process_fake_redis_client

    install_process_fake_redis_client()
    configure_token_env(set_env=os.environ.__setitem__)
    get_settings.cache_clear()
    with installed_fake_tenant_source():
        yield


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def service_app(assembled_system: AssembledSystem | None) -> AsyncIterator[FastAPI]:
    """本服务应用实例（取全系统装配的实例，**不再重建**）。

    Args:
        assembled_system: 会话级全系统装配（autouse）。

    Yields:
        FastAPI: 已装配的应用实例（每例前后清租户缓存）。

    Raises:
        RuntimeError: 全系统未装配（`BMS_TEST_ASSEMBLED=0`）。
    """
    if assembled_system is None:
        raise RuntimeError("全系统未装配（BMS_TEST_ASSEMBLED=0）：用例不得自建 app")
    app = assembled_system.app("notification")
    clear_tenant_cache(app)
    try:
        yield app
    finally:
        clear_tenant_cache(app)


def pytest_collection_modifyitems(items: ConcurrentStableList[pytest.Item]) -> None:
    """通知服务异步用例统一使用模块级事件循环（装配常驻 B1）。"""
    apply_module_loop_scope(items, Path(__file__).parent)


@pytest_asyncio.fixture(loop_scope="module")
async def client(service_app: FastAPI) -> AsyncIterator[AsyncClient]:
    """ASGITransport 异步客户端（带认证头；复用常驻 `service_app`）。

    Args:
        service_app: 应用实例。

    Yields:
        AsyncClient: 测试客户端。
    """
    clear_tenant_cache(service_app)
    try:
        async with AsyncClient(transport=ASGITransport(app=service_app), base_url="http://test") as c:
            c.headers.update(auth_headers())
            yield c
    finally:
        clear_tenant_cache(service_app)
