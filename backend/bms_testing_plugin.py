"""pytest 启动插件（13_02）：**最早**启动覆盖率采集，再注册测试基座夹具。

为什么放在 `backend/` 顶层而不是 `bms_core.testing` 包内：

- pytest 处理 `-p` 时先解析 `addopts`，插件模块的导入发生在 `pytest_load_initial_conftests` 之前；
- 若插件位于 `bms_core.testing` 包内，导入插件必然先执行父包（`bms_core` / `bms_core.testing`）
  与应用模块链，**这发生在覆盖率探针启动之前** —— 被测模块「导入期执行的行」永久漏计；
- 实测后果：全仓 10 包行覆盖率长期停在 93.36%（2261 行假缺口），而 `coverage run -m pytest`
  同一批用例为 100%。

本模块顶层**只依赖标准库与 coverage**：先启动探针（`BMS_COVERAGE_DATA` 驱动），再在
`pytest_configure` 里导入 `bms_core.testing.plugin` 注册夹具（此时探针已启动，导入行可被采集）。

环境变量（由预检 / CI / 选测执行器设置）：

- `BMS_COVERAGE_DATA`：覆盖率数据文件基址（xdist worker 各自写 `.coverage.<host>.<pid>.<rand>`，
  结束后由调用方 `coverage combine` 合并）；未设置则不采集；
- `BMS_COVERAGE_SOURCE`：采集范围（逗号分隔的包名 / 模块名，如 `bms_core,bms_platform`）。
"""

import atexit
import contextlib
import os
from typing import Any

_COVERAGE_DATA_ENV = "BMS_COVERAGE_DATA"
"""覆盖率数据文件基址（未设置则不采集）。"""

_COVERAGE_SOURCE_ENV = "BMS_COVERAGE_SOURCE"
"""采集范围（逗号分隔）。"""

_coverage: Any = None


def _start_coverage() -> Any:
    """按环境变量启动覆盖率采集（早于任何被测模块导入）。

    Returns:
        Any: coverage 实例；未启用或未安装 coverage 时返回 `None`。
    """
    data_file = os.environ.get(_COVERAGE_DATA_ENV, "")
    if not data_file:
        return None
    try:
        import coverage
    except ModuleNotFoundError:  # pragma: no cover - 产品仓未装覆盖率工具时的退化路径
        return None
    source = tuple(item.strip() for item in os.environ.get(_COVERAGE_SOURCE_ENV, "").split(",") if item.strip())
    # 后缀固定为进程号：xdist worker 各写一份 `.coverage.<pid>`，`coverage combine` 按文件名唯一合并
    # （`data_suffix=True` 的默认后缀在多个 worker 上会撞名，合并时被当作重复文件跳过）
    instance = coverage.Coverage(data_file=data_file, data_suffix=f"{os.getpid()}", branch=True, source=source or None)
    instance.start()
    return instance


def _stop_coverage() -> None:
    """停止并落盘覆盖率数据（幂等：`pytest_sessionfinish` 与 `atexit` 都会调用）。"""
    global _coverage
    if _coverage is not None:
        _coverage.stop()
        _coverage.save()
        _coverage = None


_coverage = _start_coverage()
atexit.register(_stop_coverage)


def pytest_sessionfinish(session: Any, exitstatus: int) -> None:
    """测试会话结束：落盘本进程的覆盖率数据（xdist worker 各自落一份）。

    Args:
        session: pytest 会话对象（未使用）。
        exitstatus: 退出码（未使用）。
    """
    with contextlib.suppress(Exception):
        _stop_coverage()


def pytest_configure(config: Any) -> None:
    """注册测试基座夹具（夹具模块此时才导入，导入行可被覆盖率采集）。

    Args:
        config: pytest 配置对象。
    """
    from bms_core.testing import plugin as base_plugin

    config.pluginmanager.register(base_plugin, "bms_testing_base_plugin")
    base_plugin.pytest_configure(config)
