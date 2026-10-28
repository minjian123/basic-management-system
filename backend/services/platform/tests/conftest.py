"""平台服务 pytest 夹具：仅保留服务专属接线。

配置隔离 / 平台库隔离 / 请求上下文复位 / 插件注册表复位由测试公共基座
`bms_core.testing.fixtures` 提供（13_04）；本文件保留：

- `isolate_settings`：公共隔离之上追加 fakeredis 与测试令牌密钥；
- `platform_db_url`：会话级平台库（额外播种服务目录）；
- `fake_tenant_source` / `service_app` / `client`：服务专属（平台应用工厂 + 认证头）。
"""

import asyncio
import json
import os
from collections.abc import AsyncIterator, Iterator

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from bms_core.collaboration.usage import reset_capability_usages
from bms_core.core.concurrent import ConcurrentStableFrozenDict, ConcurrentStableFrozenList, ConcurrentStableList
from bms_core.core.config import Settings, get_settings
from bms_core.datasource.registry import reset_data_source_records
from bms_core.permission.sources import reset_permission_data_sources
from bms_core.registry.products import load_product_manifests
from bms_core.services.module_registry import (
    CollaborationRecord,
    register_collaboration_records,
    register_domain_services,
    reset_collaboration_records,
    reset_error_code_records,
    reset_product_records,
    reset_product_routes,
    reset_seed_records,
    reset_service_records,
)
from bms_core.testing.fixtures import (
    clear_tenant_cache,
    platform_db,
    reset_plugin_registry,
    reset_request_context,
)
from bms_core.testing.fixtures import (
    isolate_settings as bms_isolate_settings,
)
from bms_platform.domains.permission_meta.permission.checker import register_platform_permission
from bms_platform.main import ApplicationFactory
from ops.seed_module import seed_modules
from ops.seed_tenant import seed_tenants
from tests_support.auth import auth_headers, configure_token_env
from tests_support.tenant_source import install_fake_tenant_source

MANIFESTS_ENV = "BMS_REGISTRY__PRODUCT_MANIFESTS"
"""产品登记清单环境变量名（与配置键位一致；播种与用例期共用同一份会话级清单）。"""

__all__ = ("bms_isolate_settings", "platform_db", "reset_plugin_registry", "reset_request_context")


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


@pytest.fixture(scope="session", autouse=True)
def pinned_product_manifests() -> ConcurrentStableList[str]:
    """会话级固定的产品登记清单集合（启动播种与用例断言同源，避免并行 / 顺序相关）。

    取会话启动时的配置原值（本地工作区指向产品仓清单；CI 无产品仓即空清单），
    相对路径由 `load_product_manifests` 按后端工程根解析，与被测进程工作目录无关。

    Returns:
        ConcurrentStableList[str]: 清单路径（配置原值，保序）。
    """
    return ConcurrentStableList(Settings().registry.product_manifests)


@pytest.fixture(autouse=True)
def isolate_catalog_records(
    pinned_product_manifests: ConcurrentStableList[str],
    isolate_settings: None,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[None]:
    """用例隔离：固定产品清单环境变量，复位视图族后重载平台注入清单。

    进程级注入表（服务行 / 产品档案 / 产品路由 / 数据源条目）会随同一 worker 内先前用例的装载累积；
    与「会话级播种库」不同源时清单接口的总数断言会随执行顺序漂移。这里每例先**复位**视图族、再按
    **同一份**会话级清单幂等重载，使「播种集合 ≡ 目录视图」恒成立。

    复位范围对齐 `registry.projection.project_registry` 的整体重建集合（八类）：声明注册 / 投影类
    用例会把自身造的 `demo` 服务行与产品路由投影进进程内视图，用例结束不恢复；不复位时同 worker 后
    续用例（如 `service_app` 装配）会带着这些行去核对库，报「目标服务未登记 / 库中缺登记行」
    （2026-10-28 单服务子流水线 `service-test` 实测）。

    Args:
        pinned_product_manifests: 会话级固定的清单路径。
        isolate_settings: 配置隔离夹具（保证环境变量覆盖先完成）。
        monkeypatch: pytest monkeypatch 夹具。

    Yields:
        None: 用例运行期。
    """
    monkeypatch.setenv(MANIFESTS_ENV, json.dumps(list(pinned_product_manifests)))
    get_settings.cache_clear()
    reset_product_records()
    reset_service_records()
    reset_product_routes()
    reset_data_source_records()
    reset_collaboration_records()
    reset_seed_records()
    reset_error_code_records()
    reset_capability_usages()
    load_product_manifests(pinned_product_manifests)
    yield


_MDM_PEER_CAPABILITIES: ConcurrentStableList[CollaborationRecord] = ConcurrentStableList(
    (
        CollaborationRecord(
            name="mdm.org.user-roles",
            domain="org",
            kind="read",
            contract_version="0.1.0",
            path="/api/v1/mdm/user-roles",
            product_key="mdm",
            frontend_prefix="mdm",
            default_consumers=ConcurrentStableFrozenList(("platform",)),
        ),
        CollaborationRecord(
            name="mdm.org.user-posts.assign",
            domain="org",
            kind="txn-branch",
            contract_version="0.1.0",
            path="/api/v1/mdm/internal/user-posts/{user_id}",
            product_key="mdm",
            branch_id="m",
            branch_op="mdm.user-posts.assign",
            frontend_prefix="mdm",
            default_consumers=ConcurrentStableFrozenList(("platform",)),
        ),
        CollaborationRecord(
            name="mdm.org.user-depts.assign",
            domain="org",
            kind="txn-branch",
            contract_version="0.1.0",
            path="/api/v1/mdm/internal/user-depts/{user_id}",
            product_key="mdm",
            branch_id="m",
            branch_op="mdm.user-depts.assign",
            frontend_prefix="mdm",
            default_consumers=ConcurrentStableFrozenList(("platform",)),
        ),
        CollaborationRecord(
            name="mdm.org.role-posts.assign",
            domain="org",
            kind="txn-branch",
            contract_version="0.1.0",
            path="/api/v1/mdm/internal/role-posts/{role_id}",
            product_key="mdm",
            branch_id="m",
            branch_op="mdm.role-posts.assign",
            frontend_prefix="mdm",
            default_consumers=ConcurrentStableFrozenList(("platform",)),
        ),
        CollaborationRecord(
            name="mdm.org.role-depts.assign",
            domain="org",
            kind="txn-branch",
            contract_version="0.1.0",
            path="/api/v1/mdm/internal/role-depts/{role_id}",
            product_key="mdm",
            branch_id="m",
            branch_op="mdm.role-depts.assign",
            frontend_prefix="mdm",
            default_consumers=ConcurrentStableFrozenList(("platform",)),
        ),
    )
)
"""对端（mdm）能力声明的**等价物**：平台用例以「对端声明已装载」为前提。

CI 单仓没有产品仓清单（`product_manifests` 为空），而平台的跨产品取用（`resolve_capability`）
依赖对端声明；此处给出与 mdm 仓 `deploy/registry/mdm.toml` 的 `[[collaborations]]` **逐字一致**的
记录（工作区已装载时同值幂等；声明改动后异值会被 `register_collaboration_records` 拒，属预期提醒）。
"""

_MDM_PEER_DOMAINS: ConcurrentStableFrozenDict[str, str] = ConcurrentStableFrozenDict({"org": "mdm"})
"""对端能力承载域（能力寻址第二段的域布局来源；工作区由 mdm 仓 `domain_layout.json` 提供）。"""


@pytest.fixture(autouse=True)
def install_peer_declarations(isolate_catalog_records: None) -> None:  # pyright: ignore[reportUnusedFunction]
    """用例前提：装载对端能力声明与承载域（本仓清单装载之后执行，同值幂等）。

    Args:
        isolate_catalog_records: 本仓清单装载夹具（保证顺序：先装本仓、再补对端）。
    """
    register_collaboration_records(_MDM_PEER_CAPABILITIES)
    register_domain_services(_MDM_PEER_DOMAINS)


@pytest.fixture(autouse=True)
def isolate_permission_data_sources(isolate_settings: None) -> Iterator[None]:  # pyright: ignore[reportUnusedFunction]
    """用例隔离：重置权限数据来源注册表并重登记平台侧工厂。

    `bms_core.permission.sources` 的实例 / 工厂注册表是**进程级全局表**且「最后登记者生效」，而 key
    不止一个（平台直查本库 / 身份经平台内部契约取数）。并发（xdist）下同一 worker 内若身份用例先建过
    应用，后续平台请求会走到身份侧实现（`10007`）。这里每个用例前重置并**只**登记本服务工厂，
    使平台用例与执行顺序无关（与身份侧 `test_identity_checker.py` 的 `reset_permission_data_sources()`
    隔离口径一致）。

    Args:
        isolate_settings: 配置隔离夹具（保证环境变量覆盖先完成）。

    Yields:
        None: 用例运行期。
    """
    reset_permission_data_sources()
    register_platform_permission(get_settings())
    yield


@pytest.fixture(scope="session")
def platform_db_url(
    tmp_path_factory: pytest.TempPathFactory,
    pinned_product_manifests: ConcurrentStableList[str],
) -> str:
    """会话级平台库：播种租户与服务目录（建库 / 播种整个测试会话只做一次）。

    服务目录播种使启动接库校验走「非空对账」路径、只读接口可查全量行（贴近生产形态）。
    播种前显式固定产品清单环境变量（与用例期同一份会话级清单）：服务目录播种与接口断言同源，
    避免「播种时装载了产品清单、断言时视图为空」的顺序相关错位（04_05 F6）。

    Args:
        tmp_path_factory: pytest 临时目录工厂。
        pinned_product_manifests: 会话级固定的产品清单路径。

    Returns:
        str: 会话级平台库连接串。
    """
    platform_url = f"sqlite+aiosqlite:///{tmp_path_factory.mktemp('platform') / 'app.db'}"
    previous = os.environ.get(MANIFESTS_ENV)
    os.environ[MANIFESTS_ENV] = json.dumps(list(pinned_product_manifests))
    get_settings.cache_clear()
    try:
        asyncio.run(seed_tenants(platform_url))
        asyncio.run(seed_modules(platform_url))
    finally:
        if previous is None:
            os.environ.pop(MANIFESTS_ENV, None)
        else:
            os.environ[MANIFESTS_ENV] = previous
        get_settings.cache_clear()
    return platform_url


@pytest.fixture(autouse=True)
def fake_tenant_source(monkeypatch: pytest.MonkeyPatch) -> None:
    """租户源替身：应用装配时改注入 `FakeTenantSource`（令牌主键经 `by_id` 可解析）。

    Args:
        monkeypatch: pytest monkeypatch 夹具。
    """
    install_fake_tenant_source(monkeypatch)


@pytest.fixture
async def service_app() -> AsyncIterator[FastAPI]:
    """平台服务应用实例夹具（经 lifespan 装配；供探针 / 应用级断言与 `client` 共用）。

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
    """ASGITransport 异步客户端夹具（复用 `service_app`，带认证头）。

    Args:
        service_app: 应用实例。

    Yields:
        AsyncClient: 测试客户端。
    """
    async with AsyncClient(transport=ASGITransport(app=service_app), base_url="http://test") as c:
        c.headers.update(auth_headers())
        yield c
