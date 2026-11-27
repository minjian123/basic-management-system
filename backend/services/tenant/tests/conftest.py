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
from sqlalchemy.ext.asyncio import AsyncSession

from bms_core.testing.system import AssembledSystem
from bms_core.testing.transaction import write_session
from tests_support.auth import auth_headers, configure_token_env
from tests_support.shared_access import shared_engine
from tests_support.tenant_base import tenant_base as tenant_base  # pytest 夹具须在本模块命名空间可见
from tests_support.tenant_source import install_fake_tenant_source, installed_fake_tenant_source


@pytest.fixture(autouse=True)
def _plugin_fixtures(  # pyright: ignore[reportUnusedFunction]
    platform_db: None, reset_plugin_registry: None, reset_request_context: None
) -> None:
    """启用测试公共基座的公共夹具（平台库 / 插件注册表 / 请求上下文复位）。"""


@pytest.fixture(autouse=True)
def _restore_assembled_app(  # pyright: ignore[reportUnusedFunction]
    service_app: FastAPI,
) -> Iterator[None]:
    """每例恢复装配态：依赖覆盖与配置快照都回到用例开始前。

    装配常驻（13_10）后 app 跨用例复用，用例直接写 `app.dependency_overrides[...]` 的写法会把
    替身留给后继用例（实测：`test_tenant_membership.py` 之后 `test_tenant_self_service.py` 的令牌
    校验走到无 `token_id` 的替身 → 401 / AttributeError）。还原逻辑单源在 `tests_support.app_state`。

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
def platform_tenant_db_url(tmp_path: Path, platform_db_prepare: Callable[[str], None]) -> str:
    """每用例一份**独占平台库**连接串（同步建库 + 种子，避免在事件循环里 `asyncio.run`）。

    Args:
        tmp_path: 用例级临时目录。
        platform_db_prepare: 共享平台库准备集（建表 + 种子）。

    Returns:
        str: 独占平台库异步连接串。
    """
    url = f"sqlite+aiosqlite:///{tmp_path / 'platform_tenant.db'}"
    platform_db_prepare(url)
    return url


@pytest_asyncio.fixture
async def platform_tenant_session(platform_tenant_db_url: str) -> AsyncIterator[AsyncSession]:
    """每用例一份**独占平台库**会话：平台租户是全库唯一行，状态编排必须独占。

    平台租户（`settings.platform_tenant.code` 对应的那一行）只有一行，而多个用例要把它分别置成
    `provisioning` / `suspended` / `active` 再跑开通编排——共享库上必然互相踩（旧版靠
    `file_lock("platform-tenant-bootstrap")` 串行，锁既拖慢又把临界区拉到整条用例）。
    改为每例建一份 tmp 平台库（同构 schema + 种子），行归自己：用例可并发，也不需要任何锁。

    Args:
        platform_tenant_db_url: 独占平台库连接串。

    Yields:
        AsyncSession: 独占平台库门会话（操作级写门、写入即落库）。
    """
    engine = shared_engine(platform_tenant_db_url)
    try:
        async with write_session(engine) as session:
            yield session
    finally:
        await engine.dispose()


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
