"""pytest 公共夹具：ASGI 内存客户端（免启服务器）+ 配置环境隔离 + 平台库租户种子。"""

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
    ns,
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
    "ns",
    "platform_db",
    "reset_plugin_registry",
    "reset_request_context",
)
from bms_core.testing.system import AssembledSystem
from tests_support.auth import auth_headers, configure_token_env

DEMO_TENANT_ID = "1001"
"""演示租户主键（雪花 id 字符串；与测试令牌 / 身份映射口径一致）。"""

ACME_TENANT_ID = "2002"
"""示例租户主键（雪花 id 字符串）。"""


@pytest.fixture(autouse=True)
def _restore_app_overrides(  # pyright: ignore[reportUnusedFunction]
    service_app: FastAPI,
) -> Iterator[None]:
    """每例恢复装配态：依赖覆盖与配置快照都回到用例开始前。

    装配常驻（13_10）后 app 跨用例复用，历史用例里直接写 `app.dependency_overrides[...]` 或
    就地改 `app.state.settings.<段>.<字段>` 的写法会把替身 / 改动留给后继用例（实测：
    `sso/test_authorize.py` 之后 `sso/test_bind.py` 必红；`sso/test_callback.py` 的跳转配置
    让后继所有回调用例从 JSON 变 302）。还原逻辑单源在 `tests_support.app_state`。

    Args:
        service_app: 已装配的应用实例（会话级）。

    Yields:
        None: 用例运行期。
    """
    from tests_support.app_state import restore_assembled_app

    with restore_assembled_app(service_app):
        yield


@pytest.fixture(autouse=True)
def _plugin_fixtures(  # pyright: ignore[reportUnusedFunction]
    platform_db: None, reset_request_context: None, reset_plugin_registry: None
) -> None:
    """启用测试公共基座的公共夹具（平台库 / 请求上下文 / 插件注册表复位）。

    夹具实现单源在 `bms_core.testing.fixtures`；本包装只负责在本套件启用
    （交易服务单测不依赖平台库，故不启用）。
    """


@pytest.fixture(autouse=True)
def _permission_exempt(service_app: FastAPI, monkeypatch: pytest.MonkeyPatch) -> None:
    """identity 套件权限放行：把**本应用**的权限 provider 回落占位实现（恒放行）。

    `04_01` 下沉后 identity 的 5 个端点（`session:query` / `session:kick` / `open:manage` /
    `idp:manage` / `sso:bind`）走真实 RBAC；本套件绝大多数用例测的是 SSO / 会话 / IdP 的业务
    语义，不是授权链路。权限码级判定与 fail-closed 分支由 `tests/permission/` 专项用例覆盖。

    为什么改 provider 而不是写库（13_11 两轮实测教训）：
    - 写共享租户库（`setup_min_tenant`）会把「测试主体 → 系统管理员」留给同一进程的其它服务
      用例——platform 的 `job:*` / `archive:*` 无权限断言立即从 403 变 200；
    - 直接改 `app.state` 装配结果是 P5 前提护栏禁止项（装配结果由系统装配器唯一决定）。
    改 `app.state.settings.permission.provider` 是配置面：`get_permission_checker` 每请求读它，
    `resolve_plugin(..., "")` 解析到 `null` 占位检查器，且 `monkeypatch` 退出自动还原。

    Args:
        service_app: 本服务应用实例（会话级装配）。
        monkeypatch: pytest 补丁夹具（退出还原配置）。
    """
    monkeypatch.setattr(service_app.state.settings.permission, "provider", "")


@pytest.fixture(autouse=True)
def isolate_settings(bms_isolate_settings: None, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """服务专属隔离：在公共隔离之后追加 SSO 状态存储关闭、fakeredis 与测试令牌密钥。

    Args:
        bms_isolate_settings: 公共隔离夹具（保证顺序）。
        monkeypatch: pytest monkeypatch 夹具。

    Yields:
        None: 用例运行期。
    """
    from tests_support.redis import install_process_fake_redis_client

    install_process_fake_redis_client()
    # SSO 流程状态存储（02_01）：单测不连 Redis，回落 Null
    monkeypatch.setenv("BMS_IDP_STATE_STORE__PROVIDER", "")
    # 登录态依赖真实化（01_05）：注入测试用户令牌密钥，使受保护路由在真实鉴权下可验签
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


@pytest.fixture(scope="session")
def tenant_db_url(shared_tenant_db_url: str) -> str:
    """会话级租户库：**共享租户库**（04-6-2 单库化；建表 / 参数种子由准备集一次性负责）。

    Args:
        shared_tenant_db_url: 共享租户库连接串（会话级）。

    Returns:
        str: 会话级租户库连接串。
    """
    return shared_tenant_db_url


@pytest.fixture(autouse=True)
def tenant_db(tenant_db_url: str, monkeypatch: pytest.MonkeyPatch) -> None:  # pyright: ignore[reportUnusedFunction]
    """把租户库连接串指向**共享租户库**（单库化默认路径）。

    为什么必须显式注入：`[database.tenants]` 的缺省 url 是 `./bms_tenant_demo.db`（相对 cwd），
    不注入就会把会话行写到工作区 `database/bms/` 下的常驻文件，跨会话残留、也不在
    `.cache/test/` 之下——既违背「一次会话只有 platform / tenant 两个库文件」，也让用例结果
    依赖历史残留。

    依赖它的夹具（如各目录的 `ensure_schema`）必须**显式声明**：引擎工厂在应用创建时固化
    连接串，接线晚于 app 装配等于没接。

    Args:
        tenant_db_url: 会话级共享租户库连接串。
        monkeypatch: pytest monkeypatch 夹具。
    """
    monkeypatch.setenv("BMS_DATABASE__TENANTS__URL", tenant_db_url)
    get_settings.cache_clear()


@pytest.fixture
def isolated_platform_db_url(tmp_path: Path, platform_db_prepare: Callable[[str], None]) -> str:
    """白名单（`own_db`）用例专用**独占**平台库：每用例一份 tmp 库 + 播种。

    用于「逐例整表清场」（SSO 会话 / 提供方 / 身份映射）的用例：共享库上清场会删掉并行中
    他人用例的数据。

    Args:
        tmp_path: 用例级临时目录。
        platform_db_prepare: 共享平台库准备集（保证种子租户与主键对齐同源）。

    Returns:
        str: 独占平台库连接串。
    """
    url = f"sqlite+aiosqlite:///{tmp_path / 'platform_isolated.db'}"
    platform_db_prepare(url)
    return url


@pytest.fixture
def isolated_tenant_db_url(tmp_path: Path, tenant_db_prepare: Callable[[str], None]) -> str:
    """白名单（`own_db`）用例专用**独占**租户库：每用例一份 tmp 库 + 参数种子。

    Args:
        tmp_path: 用例级临时目录。
        tenant_db_prepare: 共享租户库准备集。

    Returns:
        str: 独占租户库连接串。
    """
    url = f"sqlite+aiosqlite:///{tmp_path / 'tenant_isolated.db'}"
    tenant_db_prepare(url)
    return url


@pytest.fixture
def isolated_tenant(tenant_db: None, isolated_tenant_db_url: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """`own_db` 用例的**独占**租户库接线（每用例一份 tmp 库 + 参数种子）。

    只给「整租户库口径即被测」的文件 / 用例用（如按租户批量撤销全部在线会话：共享库上会把
    并行 worker 的在线会话一并撤销）。用法：在用例签名里**排在 `client` 之前**声明，
    保证应用装配前环境已切库。

    Args:
        tenant_db: 共享租户库接线（保证顺序：先公共、后独占）。
        isolated_tenant_db_url: 独占租户库连接串（每用例一份 tmp 库 + 参数种子）。
        monkeypatch: pytest monkeypatch 夹具。
    """
    monkeypatch.setenv("BMS_DATABASE__TENANTS__URL", isolated_tenant_db_url)
    get_settings.cache_clear()


def pytest_collection_modifyitems(items: ConcurrentStableList[pytest.Item]) -> None:
    """身份服务异步用例统一使用模块级事件循环（装配常驻 B1）。"""
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
    app = assembled_system.app("identity")
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
            c.headers.update(auth_headers(tenant=DEMO_TENANT_ID))
            yield c
    finally:
        clear_tenant_cache(service_app)
