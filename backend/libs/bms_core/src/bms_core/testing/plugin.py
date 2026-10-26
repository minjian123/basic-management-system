"""测试基座插件（13_04）：夹具注册与并行 SQLite 隔离的公共实现。

加载方式有两种，按仓库形态选择：

- **bms 仓**：`addopts = "-p bms_testing_plugin"`（`backend/bms_testing_plugin.py`）——该启动插件
  在**最早**阶段启动覆盖率采集，再在 `pytest_configure` 里注册本模块；这样被测模块的「导入期执行行」
  也能被采集（13_02）。
- **产品仓**：可直接 `-p bms_core.testing.plugin`（本模块）复用夹具；覆盖率采集时机由产品仓自管。

为什么不用各 conftest 写 `pytest_plugins`：pytest 7+ 禁止**非顶层 conftest** 声明
`pytest_plugins`，而本项目有 10 个测试根（每个工程一个 conftest），故统一由 `-p` 加载。

注意：`pytest_plugins` 在「由 `-p` 加载的插件模块」中**不会**再被处理（该机制只对 conftest 生效），
故这里的夹具必须显式导入到本模块命名空间，pytest 才会收集注册。
"""

import os

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

    同时补齐 `--basetemp` 的父目录：`addopts` 里的 `--basetemp=.cache/pytest` 指向仓内
    缓存目录，而 pytest 的 `TmpPathFactory.getbasetemp()` 只 `mkdir` 末级目录、**不递归建父目录**
    （`tmpdir.py` 中 `basetemp.mkdir(mode=0o700)`），父目录 `.cache` 不存在时 xdist 起 worker
    即 `FileNotFoundError` 崩掉。此处在本钩子里 `makedirs(exist_ok=True)`——本钩子早于
    `pytest_sessionstart`（xdist 在后者里才取 basetemp），故能保证父目录就位。

    Args:
        config: pytest 配置对象。
    """
    basetemp = getattr(config.option, "basetemp", "") or ""
    if basetemp:
        # `abspath` 结果必然含父目录，无需再判空
        os.makedirs(os.path.dirname(os.path.abspath(os.fspath(basetemp))), exist_ok=True)
    fixtures.configure_sqlite_basetemp(str(basetemp))
