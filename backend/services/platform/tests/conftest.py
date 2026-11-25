"""平台服务 pytest 夹具：仅保留服务专属接线。

配置隔离 / 平台库隔离 / 请求上下文复位 / 插件注册表复位由测试公共基座
`bms_core.testing.fixtures` 提供（13_04）；本文件保留：

- `isolate_settings`：公共隔离之上追加 fakeredis 与测试令牌密钥；
- `platform_db_url`：会话级平台库——**已切到共享平台库**（04-6-2 单库化，播种由准备集负责）；
- `platform_db_prepare` / `tenant_db_prepare`：共享库准备集薄壳（子工程自成 rootdir 时兜底）；
- `fake_tenant_source` / `service_app` / `client`：服务专属（平台应用工厂 + 认证头）。
"""

from collections.abc import AsyncIterator, Callable, Iterator
from pathlib import Path

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from bms_core.collaboration.usage import register_capability_usages
from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.config import get_settings
from bms_core.datasource.registry import reset_data_source_records
from bms_core.permission.sources import reset_permission_data_sources
from bms_core.registry.products import load_product_manifests
from bms_core.services.module_registry import (
    reset_collaboration_records,
    reset_domain_services,
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
from bms_core.testing.system import AssembledSystem
from bms_platform.domains.permission_meta.permission.checker import register_platform_permission
from tests_support.auth import auth_headers, configure_token_env
from tests_support.tenant_source import install_fake_tenant_source

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

    07B `04_02`：`[registry].product_manifests` 已退役，清单取源固定为**本仓**
    `deploy/registry/*.toml` 自动发现（相对路径按后端工程根解析，与工作目录无关），
    故这里固定为空（由 `load_product_manifests` 内部补本仓清单）。

    Returns:
        ConcurrentStableList[str]: 额外清单路径（恒空）。
    """
    return ConcurrentStableList()


def _reload_catalog_views(pinned_product_manifests: ConcurrentStableList[str]) -> None:
    """按会话级清单重建进程内视图族（八类记录 + 业务域映射）并补登记消费方使用声明。

    **使用声明不能靠「复位 + 清单重载」恢复**：`platform` 的 `[[usages]]`（如
    `mdm.mdm.user-roles` 的 `degrade = "empty"`）在生产由注册表投影（`project_registry`）
    登记，而 `load_product_manifests` 只登记八类记录（`register_manifest` 的既定范围，不含使用
    声明）。装配常驻后声明只在装配期登记一次；每例把它复位掉，`call_capability` 就找不到消费方
    声明、于是不降级而是把取用失败原样上抛——平台主体链解析 `mdm` 角色时能力取用失败（40003）
    直接变成 500，帮助域等整片用例变红（2026-11-24 实测）。故这里按清单**补登记**（同值幂等），
    而非复位后放弃。

    Args:
        pinned_product_manifests: 会话级固定的清单路径（空清单表示只取本仓 `deploy/registry/*.toml`）。
    """
    reset_product_records()
    reset_service_records()
    reset_product_routes()
    reset_data_source_records()
    reset_collaboration_records()
    reset_seed_records()
    reset_error_code_records()
    reset_domain_services()
    for manifest in load_product_manifests(pinned_product_manifests):
        if manifest.usages:
            register_capability_usages(manifest.product_key, manifest.usages)


@pytest.fixture(autouse=True)
def isolate_catalog_records(
    pinned_product_manifests: ConcurrentStableList[str],
    isolate_settings: None,
    isolated_topology: None,
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

    另经 `isolated_topology` 留存并恢复进程级拓扑状态（快照 / 当前版本 / 实例上下文）：域归属判定
    直接读这些全局，用例改写后不恢复会让同 worker 后继用例报「业务域未在本实例启用」（403），
    且该状态不在库内，独占库隔离无效（2026-11-23 末批实测）。

    **消费方使用声明不在复位面内**：它是装配期由注册表投影登记的声明，清单重载补不回来，
    具体口径与踩坑见 `_reload_catalog_views`。

    Args:
        pinned_product_manifests: 会话级固定的清单路径。
        isolate_settings: 配置隔离夹具（保证环境变量覆盖先完成）。
        isolated_topology: 拓扑状态留存夹具（保证在装配前留存、用例后恢复）。
        monkeypatch: pytest monkeypatch 夹具。

    Yields:
        None: 用例运行期。
    """
    get_settings.cache_clear()
    _reload_catalog_views(pinned_product_manifests)
    yield
    # 用例结束同样复位：投影类用例写入的是「无来源」记录，留在进程里会让同一 worker 内
    # 后建的会话级装配快照与清单装载撞「同键异值」。
    #
    # 业务域承载映射同样是进程级全局表：用例装载的临时清单（如声明注册用例的 `[[domains]]`）
    # 若留在进程里，后续用例的启动自举会把临时域写进共享库默认拓扑（测试库为真自动提交，写完即生效）。
    # 这里**按会话级清单重载**而不是「恢复用例开始前的值」：后者会把上一例留下的残值当成基线，
    # 一旦某例把映射改成只含少数域且自身不复位，残值就被当成基线逐例传播，后继用例的域归属判定报
    # 「业务域未在本实例启用」（403，2026-11-23 末批实测）。
    _reload_catalog_views(pinned_product_manifests)


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
def platform_db_prepare() -> Callable[[str], None]:
    """共享平台库准备集回调（子工程自成 rootdir 时的薄壳，实现单源在 `tests_support.shared_db`）。

    Returns:
        Callable[[str], None]: 接受连接串的准备函数。
    """
    from tests_support.shared_db import prepare_platform

    return prepare_platform


@pytest.fixture(scope="session")
def tenant_db_prepare() -> Callable[[str], None]:
    """共享租户库准备集回调（同上，供 `shared_tenant_db_url` 解析）。

    Returns:
        Callable[[str], None]: 接受连接串的准备函数。
    """
    from tests_support.shared_db import prepare_tenant

    return prepare_tenant


@pytest.fixture(scope="session")
def platform_db_url(shared_platform_db_url: str) -> str:
    """会话级平台库：**共享平台库**（04-6-2 单库化；建库 / 播种由准备集一次性负责）。

    播种（种子租户 → 主键对齐 → 服务目录与产品档案）已并入 `tests_support.shared_db.prepare_platform`，
    本夹具只做转发——套件内既有用例经 `platform_db` 继续指向同一库，无需逐例改动。

    Args:
        shared_platform_db_url: 共享平台库连接串（会话级）。

    Returns:
        str: 会话级平台库连接串。
    """
    return shared_platform_db_url


@pytest.fixture
def tenant_db(shared_tenant_db_url: str, monkeypatch: pytest.MonkeyPatch) -> str:
    """把租户库连接串指向**共享租户库**（单库化默认路径；权限引擎 / 图标 / 角色等读租户库的用例用）。

    Args:
        shared_tenant_db_url: 共享租户库连接串（会话级；建表与参数种子由准备集负责）。
        monkeypatch: pytest monkeypatch 夹具。

    Returns:
        str: 共享租户库连接串。
    """
    monkeypatch.setenv("BMS_DATABASE__TENANTS__URL", shared_tenant_db_url)
    get_settings.cache_clear()
    return shared_tenant_db_url


@pytest.fixture
def archive_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    """归档库：每用例一份独立 SQLite 文件（只建归档行表），并指向应用配置。

    Args:
        tmp_path: 用例级临时目录。
        monkeypatch: pytest monkeypatch 夹具。

    Returns:
        str: 归档库连接串。
    """
    from typing import cast

    from sqlalchemy import Table, create_engine

    from bms_core.models.base import Base
    from bms_core.models.platform.archive import SysArchiveRecord

    url = f"sqlite+aiosqlite:///{tmp_path / 'archive.db'}"
    engine = create_engine(url.replace("+aiosqlite", ""))
    try:
        Base.metadata.create_all(engine, tables=[cast("Table", SysArchiveRecord.__table__)], checkfirst=True)
    finally:
        engine.dispose()
    monkeypatch.setenv("BMS_DATABASE__ARCHIVE__URL", url)
    get_settings.cache_clear()
    from bms_platform.domains.archive.jobs import reset_archive_registry

    reset_archive_registry()
    return url


@pytest.fixture(autouse=True)
def fake_tenant_source(monkeypatch: pytest.MonkeyPatch) -> None:
    """租户源替身：应用装配时改注入 `FakeTenantSource`（令牌主键经 `by_id` 可解析）。

    Args:
        monkeypatch: pytest monkeypatch 夹具。
    """
    install_fake_tenant_source(monkeypatch)


@pytest_asyncio.fixture(scope="session", loop_scope="session", autouse=True)
async def _bootstrap_capability_grants(assembled_system: AssembledSystem | None) -> None:
    """补跑能力分配的启动钩子（装配态不跑 lifespan，声明默认授权无从落库）。

    内部端点的鉴权有「按能力分配判定」这一路（`require_capability_or_service`），查的是库内
    授权；声明基线来自 `deploy/registry/*.toml` 的 `default_consumers`，由 lifespan 的
    `bootstrap_capability_grants` 落库。装配态为省时间不起 lifespan，故这里补一次
    （钩子先做只读比对，无差异不开写事务）。

    Args:
        assembled_system: 会话级全系统装配（未装配时跳过）。
    """
    if assembled_system is None:
        return
    app = assembled_system.app("platform")
    from bms_platform.domains.platform_registry.services.capability_grant_bootstrap import (
        bootstrap_capability_grants,
    )

    await bootstrap_capability_grants(app)


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def service_app(assembled_system: AssembledSystem | None) -> AsyncIterator[FastAPI]:
    """平台服务应用实例（取全系统装配的实例，**不再重建**）。

    Args:
        assembled_system: 会话级全系统装配（autouse）。

    Yields:
        FastAPI: 已装配的平台应用实例（每例前后清租户缓存）。

    Raises:
        RuntimeError: 全系统未装配（`BMS_TEST_ASSEMBLED=0`）。
    """
    if assembled_system is None:
        raise RuntimeError("全系统未装配（BMS_TEST_ASSEMBLED=0）：用例不得自建 app")
    app = assembled_system.app("platform")
    clear_tenant_cache(app)
    try:
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
        # 固定请求语言：用例断言「必填语言」时不应受库内默认语言（可被其它用例临时切换）影响
        c.headers.setdefault("Accept-Language", "zh-CN")
        yield c
