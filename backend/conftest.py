"""后端工程根 pytest 夹具入口（04-6-2）：共享测试库的**准备集接线**。

为什么必须在工程根提供：`shared_platform_db_url` / `shared_tenant_db_url` 是会话级夹具，
其准备回调（`{数据源}_db_prepare`）只有从**根级**可见才稳定——否则回调取自「哪个套件先
跑到」，同一会话换一个 worker 先到就换一套种子，违背「并行与串行结果一致」。

各服务子工程自成 rootdir 时（`services/*/pyproject.toml`）本文件不参与，由该套件 conftest
的同名薄壳兜底（同一实现，见 `tests_support.shared_db`，不复制逻辑）。

准备集内容与口径见《[测试规范]「测试数据」节》与任务 04-6-2 详细设计 §4。
"""

from collections.abc import Callable, Iterator
from typing import Any

import pytest
import pytest_asyncio


def pytest_configure(config: pytest.Config) -> None:
    """覆盖率入口守卫（工程根最早执行）：`pytest --cov` 或换落点立即退出（code=2）。

    本仓**禁止手工采集覆盖率**：门禁只认 `[coverage].data_file`（engkit 采集）。
    走错入口不报错会让「假缺口」反复误导排障，故在跑用例前直接终止；查缺口的唯一出口是
    `scripts/tools/preflight/coverage_report.py`（`--module` 模块级 / `--changed` 改动行）。
    口径见 `bms_core.testing.coverage_guard` 与《AI开发规范》「覆盖率要求」节。

    Args:
        config: pytest 配置对象。
    """
    from bms_core.testing.coverage_guard import assert_entrypoint

    assert_entrypoint(config)


@pytest.fixture(autouse=True)
def _disable_topology_distribution(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """测试环境关闭拓扑分发（单进程测试没有「平台已就绪」的对端）。

    分发失败现在是拒启（部署顺序问题）；测试环境没有真实对端，属于「本来就该关」的配置，
    不是降级。需要验证分发本身的用例直接构造 `Settings(distribute=True)`，不受本开关影响。

    Args:
        monkeypatch: pytest 替换器。

    Yields:
        None: 用例运行期。
    """
    from bms_core.core.config import get_settings

    monkeypatch.setenv("BMS_TOPOLOGY__DISTRIBUTE", "false")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture(scope="session")
def platform_db_prepare() -> Callable[[str], None]:
    """平台库准备集回调（种子租户 → 主键对齐 → 服务目录与产品档案）。

    Returns:
        Callable[[str], None]: 接受连接串的准备函数。
    """
    from tests_support.shared_db import prepare_platform

    return prepare_platform


@pytest.fixture(scope="session")
def tenant_db_prepare() -> Callable[[str], None]:
    """租户库准备集回调（租户侧建表集 → 系统参数种子）。

    Returns:
        Callable[[str], None]: 接受连接串的准备函数。
    """
    from tests_support.shared_db import prepare_tenant

    return prepare_tenant


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def assembled_system(shared_platform_db_url: str, shared_tenant_db_url: str):
    """全系统装配（13_10）：初始化之后、用例之前，把本仓全部后端服务装配一次。

    默认关闭（`BMS_TEST_ASSEMBLED != "1"` 时返回 `None`），避免影响存量用例；
    探针与迁移期用例显式请求本夹具即可。

    Args:
        shared_platform_db_url: 会话级共享平台库连接串（保证初始化先完成）。
        shared_tenant_db_url: 会话级共享租户库连接串。

    Yields:
        object: `AssembledSystem` 或 `None`（未启用）。
    """
    import os

    if os.environ.get("BMS_TEST_ASSEMBLED") != "1":
        yield None
        return

    from bms_core.core.config import Settings, get_settings
    from bms_core.registry.products import load_product_manifests
    from bms_core.testing import fixtures as base_fixtures
    from bms_core.testing.system import AssembledSystem, reset_assembled_system, set_assembled_system
    from tests_support.assembled_services import peer_manifest_paths, service_factories
    from tests_support.auth import configure_token_env
    from tests_support.redis import install_process_fake_redis_client
    from tests_support.tenant_source import installed_fake_tenant_source

    snapshot = dict(os.environ)
    previous_env_file = Settings.model_config.get("env_file")
    for key in [item for item in os.environ if item.startswith("BMS_") and not item.startswith("BMS_TEST_")]:
        del os.environ[key]
    Settings.model_config["env_file"] = None
    os.environ["BMS_DATABASE__PLATFORM__URL"] = shared_platform_db_url
    os.environ["BMS_DATABASE__TENANTS__URL"] = shared_tenant_db_url
    os.environ["BMS_IDP_STATE_STORE__PROVIDER"] = ""
    os.environ["BMS_PLATFORM_TENANT__AUTO_BOOTSTRAP"] = "false"
    base_fixtures._reset_isolated_runtime(base_fixtures._apply_isolated_env(os.environ.__setitem__))  # pyright: ignore[reportPrivateUsage]
    install_process_fake_redis_client()
    configure_token_env(set_env=os.environ.__setitem__)
    from ops.contract_smoke import smoke_service_token_keys

    service_keys, service_kid = smoke_service_token_keys()
    os.environ["BMS_SERVICE_TOKEN__KEYS"] = service_keys
    os.environ["BMS_SERVICE_TOKEN__ACTIVE_KID"] = service_kid
    os.environ["BMS_SERVICE_CLIENT__OPTIONS"] = '{"attach_service_token": true}'
    os.environ["BMS_SERVICE_CLIENT__PROVIDER"] = "http"
    get_settings.cache_clear()

    peer_paths = peer_manifest_paths()

    def _prepare(key: str, app: Any) -> None:
        client = getattr(app.state, "service_client", None)
        if client is not None:
            client._caller = key  # pyright: ignore[reportPrivateUsage,reportAttributeAccessIssue]
        load_product_manifests(peer_paths)

    system = AssembledSystem(service_factories(), before_start=_prepare)
    from bms_core.testing.system import in_process_service_calls

    calls = in_process_service_calls(system)
    try:
        with installed_fake_tenant_source():
            async with calls:
                await system.assemble()
                set_assembled_system(system)
                yield system
    finally:
        reset_assembled_system()
        await system.aclose()
        for key in [item for item in os.environ if item not in snapshot]:
            del os.environ[key]
        os.environ.update(snapshot)
        Settings.model_config["env_file"] = previous_env_file
        get_settings.cache_clear()
