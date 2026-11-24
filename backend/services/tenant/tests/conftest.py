"""pytest 公共夹具：ASGI 内存客户端（免启服务器）+ 配置环境隔离 + 平台库租户种子。"""

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
from tests_support.tenant_base import tenant_base as tenant_base  # pytest 夹具须在本模块命名空间可见
from tests_support.tenant_source import install_fake_tenant_source, installed_fake_tenant_source


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
    monkeypatch.setenv("BMS_PLATFORM_TENANT__AUTO_BOOTSTRAP", "false")
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
    """会话级平台库：**共享平台库**（04-6-2 单库化；种子租户与主键对齐由准备集一次性负责）。

    演示 / 示例租户主键对齐（`demo ↔ 1001` / `acme ↔ 2002`）已并入
    `tests_support.shared_db.prepare_platform` 的 `_align_seed_tenant_ids`，本夹具只做转发。

    Args:
        shared_platform_db_url: 共享平台库连接串（会话级）。

    Returns:
        str: 会话级平台库连接串。
    """
    return shared_platform_db_url


@pytest.fixture
def platform_tenant_serial() -> Iterator[None]:
    """平台租户是**全库唯一行**：多个用例文件对它做状态编排，用专用文件锁串行。

    为什么不用数据库门：门只覆盖**一次写操作**，而这里的临界区跨「读现状 → 编排 → 断言」多步；
    两个 worker 同时改同一行会撞 ORM 版本谓词（`StaleDataError: UPDATE ... 0 were matched`）。
    锁名语义化、锁文件落 `.cache/test/`，与会话入口的残留锁清理同源。

    Yields:
        None: 持锁区间。
    """
    from bms_core.testing.locks import file_lock

    with file_lock("platform-tenant-bootstrap"):
        yield


@pytest.fixture(autouse=True)
def fake_tenant_source(monkeypatch: pytest.MonkeyPatch) -> None:
    """租户源替身：应用装配时改注入 `FakeTenantSource`（令牌主键经 `by_id` 可解析）。"""
    install_fake_tenant_source(monkeypatch)


@pytest.fixture(scope="module")
def tenant_module_env(
    bms_isolated_env_module: None, shared_platform_db_url: str, shared_tenant_db_url: str
) -> Iterator[None]:
    """模块级服务环境：常驻装配前就位库 URL / fakeredis / 令牌 / 租户源 / 自举开关。

    Args:
        bms_isolated_env_module: 基座模块级隔离环境（保证顺序）。
        shared_platform_db_url: 会话级共享平台库连接串。
        shared_tenant_db_url: 会话级共享租户库连接串。

    Yields:
        None: 模块运行期。
    """
    from tests_support.redis import install_process_fake_redis_client

    os.environ["BMS_DATABASE__PLATFORM__URL"] = shared_platform_db_url
    os.environ["BMS_DATABASE__TENANTS__URL"] = shared_tenant_db_url
    os.environ["BMS_PLATFORM_TENANT__AUTO_BOOTSTRAP"] = "false"
    install_process_fake_redis_client()
    configure_token_env(set_env=os.environ.__setitem__)
    get_settings.cache_clear()
    with installed_fake_tenant_source():
        yield


def pytest_collection_modifyitems(items: ConcurrentStableList[pytest.Item]) -> None:
    """租户服务异步用例统一使用模块级事件循环（装配常驻 B1）。"""
    apply_module_loop_scope(items, Path(__file__).parent)


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
    app = assembled_system.app("tenant")
    clear_tenant_cache(app)
    try:
        yield app
    finally:
        clear_tenant_cache(app)


@pytest_asyncio.fixture(loop_scope="module")
async def client(service_app: FastAPI) -> AsyncIterator[AsyncClient]:
    """ASGITransport 异步客户端夹具（复用常驻 `service_app`）。

    平台库与租户种子由 autouse 的 `platform_db` 夹具提供；租户缓存用例前后清空。
    """
    clear_tenant_cache(service_app)
    try:
        async with AsyncClient(transport=ASGITransport(app=service_app), base_url="http://test") as c:
            c.headers.update(auth_headers())
            yield c
    finally:
        clear_tenant_cache(service_app)
