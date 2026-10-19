"""pytest 插件入口（13_04）：经 `addopts = "-p bms_core.testing.plugin"` 全局加载。

为什么不用各 conftest 写 `pytest_plugins`：pytest 7+ 禁止**非顶层 conftest** 声明
`pytest_plugins`，而本项目有 10 个测试根（每个工程一个 conftest），故统一由 `-p` 加载。

注意：`pytest_plugins` 在「由 `-p` 加载的插件模块」中**不会**再被处理（该机制只对 conftest 生效），
故这里的夹具必须显式导入到本模块命名空间，pytest 才会收集注册。
"""

import importlib

import pytest

from bms_core.testing import fixtures
from bms_core.testing.fixtures import (
    clear_tenant_cache,
    configure_sqlite_basetemp,
    isolate_settings,
    platform_db,
    reset_plugin_registry,
    reset_request_context,
)

__all__ = (
    "clear_tenant_cache",
    "configure_sqlite_basetemp",
    "isolate_settings",
    "platform_db",
    "reset_plugin_registry",
    "reset_request_context",
)


def pytest_configure(config: pytest.Config) -> None:
    """把 pytest basetemp 交给测试基座（并行执行按 worker 派生独立 SQLite 目录；13_02）。

    xdist worker 的 basetemp 形如 `<根>/popen-gwN`，天然按 worker 隔离；交由
    `fixtures.worker_sqlite_dir` 派生 `<basetemp>/sqlite-gwN` 作为该 worker 的 `sqlite_dir`。

    说明：本插件（`-p bms_core.testing.plugin`）在 `pytest_configure` 之前被导入，而并行 worker 的
    覆盖率探针更晚启动——`fixtures` 的模块顶层行会漏计（表现为 `bms_core.testing` 覆盖率不达标）。
    这里在 configure 期重载一次，使顶层行落入覆盖率统计（夹具对象身份不变：模块字典复用）。

    Args:
        config: pytest 配置对象。
    """
    importlib.reload(fixtures)
    basetemp = getattr(config.option, "basetemp", "") or ""
    fixtures.configure_sqlite_basetemp(str(basetemp))
