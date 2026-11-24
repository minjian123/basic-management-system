"""文件 服务 pytest 夹具：仅保留服务专属接线。

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

from bms_core.api.deps import (
    get_config_source,
    get_multipart_upload,
    get_object_storage,
    get_outbox_store,
    get_service_client,
)
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
from file_fixtures import FilePorts

from bms_file.main import ApplicationFactory
from tests_support.auth import auth_headers, configure_token_env
from tests_support.tenant_source import install_fake_tenant_source, installed_fake_tenant_source


@pytest.fixture(autouse=True)
def _plugin_fixtures(  # pyright: ignore[reportUnusedFunction]
    platform_db: None, tenant_db: str, reset_request_context: None, reset_plugin_registry: None
) -> None:
    """启用测试公共基座的公共夹具（平台库 / 租户库 / 请求上下文 / 插件注册表复位）。

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
def file_module_env(
    bms_isolated_env_module: None, shared_platform_db_url: str, shared_tenant_db_url: str
) -> Iterator[None]:
    """模块级服务环境：常驻装配的首个用例前就把库 URL / fakeredis / 令牌 / 租户源就位。

    为什么需要库 URL：函数级 `_plugin_fixtures` 里的 `platform_db` / `tenant_db` 只在用例期设 URL，
    模块级装配先于它们执行；不在此显式注入，应用会按缺省配置连到别的库。

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
    install_process_fake_redis_client()
    configure_token_env(set_env=os.environ.__setitem__)
    get_settings.cache_clear()
    with installed_fake_tenant_source():
        yield


def pytest_collection_modifyitems(items: ConcurrentStableList[pytest.Item]) -> None:
    """文件服务异步用例统一使用模块级事件循环（装配常驻 B1）。"""
    apply_module_loop_scope(items, Path(__file__).parent)


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def service_app(file_module_env: None) -> AsyncIterator[FastAPI]:
    """服务应用实例（经 lifespan 装配，**模块级常驻**）。

    Args:
        file_module_env: 模块级服务环境（保证装配前环境就位）。

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


@pytest.fixture
def file_ports(service_app: FastAPI, tmp_path: Path) -> Iterator[FilePorts]:
    """把对象存储 / 分片 / 配额 / 参数 / 发件箱替换为可控替身（真实读写落临时目录）。

    Args:
        service_app: 服务应用（依赖覆盖挂载点）。
        tmp_path: 用例临时目录。

    Yields:
        FilePorts: 替身集合。
    """
    from file_fixtures import FilePorts

    from bms_core.storage.local import LocalObjectStorage
    from bms_core.storage.multipart_local import LocalMultipartUpload

    ports = FilePorts(LocalObjectStorage(root=tmp_path), LocalMultipartUpload(root=tmp_path))
    service_app.dependency_overrides[get_object_storage] = lambda: ports.storage
    service_app.dependency_overrides[get_multipart_upload] = lambda: ports.multipart
    service_app.dependency_overrides[get_service_client] = lambda: ports.quota
    service_app.dependency_overrides[get_config_source] = lambda: ports.config
    service_app.dependency_overrides[get_outbox_store] = lambda: ports.outbox
    try:
        yield ports
    finally:
        service_app.dependency_overrides.clear()
