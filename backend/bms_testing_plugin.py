"""pytest 启动插件（13_02）：**最早**启动覆盖率采集，再注册测试基座夹具。

为什么放在 `backend/` 顶层而不是 `bms_core.testing` 包内：

- pytest 处理 `-p` 时先解析 `addopts`，插件模块的导入发生在 `pytest_load_initial_conftests` 之前；
- 若插件位于 `bms_core.testing` 包内，导入插件必然先执行父包（`bms_core` / `bms_core.testing`）
  与应用模块链，**这发生在覆盖率探针启动之前** —— 被测模块「导入期执行的行」永久漏计；
- 实测后果：全仓 10 包行覆盖率长期停在 93.36%（2261 行假缺口），而 `coverage run -m pytest`
  同一批用例为 100%。

本模块顶层**只依赖标准库与 coverage**：先启动探针（`BMS_COVERAGE_DATA` 驱动），再在
`pytest_configure` 里导入 `bms_core.testing.plugin` 注册夹具（此时探针已启动，导入行可被采集）。

**全量测试守卫（08_05 起）**：`pytest_configure` 最早期先加载
`scripts/tools/preflight/full_test_guard.py`——本地非 CI 环境既未显式声明全量（`--full` /
`BMS_ALLOW_FULL_TESTS=1`）又未指定测试范围（无位置参数 / `-k` / `-m` / `--changed-file-list` 等）时
**立即报错退出、零用例执行**，并打印应改用的 `run-selected.py` 定向命令。口径见《测试规范》§2.1
「变更驱动、不全量重跑」；CI 环境变量天然放行。

环境变量（由预检 / CI / 选测执行器设置）：

- `BMS_COVERAGE_DATA`：覆盖率数据文件基址（xdist worker 各自写 `.coverage.<host>.<pid>.<rand>`，
  结束后由调用方 `coverage combine` 合并）；未设置则不采集；
- `BMS_COVERAGE_SOURCE`：采集范围（逗号分隔的包名 / 模块名，如 `bms_core,bms_platform`）；
- `BMS_ALLOW_FULL_TESTS`：显式允许本地全量（`1` / `true` 等；临时排查用）。
"""

import atexit
import contextlib
import importlib.util
import os
import sys
from pathlib import Path
from typing import Any

_COVERAGE_DATA_ENV = "BMS_COVERAGE_DATA"
"""覆盖率数据文件基址（未设置则不采集）。"""

_COVERAGE_SOURCE_ENV = "BMS_COVERAGE_SOURCE"
"""采集范围（逗号分隔）。"""

_GUARD_PATH = Path(__file__).resolve().parents[1] / "scripts" / "tools" / "preflight" / "full_test_guard.py"
"""全量测试守卫模块路径（`scripts/tools/preflight/full_test_guard.py`）。"""

_HEAVY_GUARD_PATH = Path(__file__).resolve().parents[1] / "scripts" / "tools" / "preflight" / "heavy_command_guard.py"
"""重命令包装守卫模块路径（`scripts/tools/preflight/heavy_command_guard.py`）。"""

_coverage: Any = None


def _load_guard_module(path: Path, name: str) -> Any:
    """按路径加载守卫模块（不依赖 `scripts` 可导入性）。

    Args:
        path: 模块文件路径。
        name: 模块名（供 `spec_from_file_location` 使用）。

    Returns:
        Any: 守卫模块；文件缺失时返回 `None`。
    """
    if not path.is_file():  # pragma: no cover - 守卫文件缺失时的退化路径
        return None
    if str(path.parent) not in sys.path:
        sys.path.insert(0, str(path.parent))
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:  # pragma: no cover - 极端异常
        return None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_guard() -> Any:
    """按路径加载全量测试守卫模块。

    Returns:
        Any: 守卫模块；文件缺失时返回 `None`。
    """
    return _load_guard_module(_GUARD_PATH, "bms_full_test_guard")


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


def pytest_addoption(parser: Any) -> None:
    """注册守卫的 `--full` 选项（须在 collection 前完成注册）。

    Args:
        parser: pytest 的 Parser 对象。
    """
    guard = _load_guard()
    if guard is not None:
        guard.pytest_addoption(parser)


def pytest_configure(config: Any) -> None:
    """重命令守卫 → 全量守卫 → 注册测试基座夹具（夹具模块此时才导入，导入行可被覆盖率采集）。

    两道守卫均**先于**夹具注册执行：命中拦截条件时抛 `UsageError`，用例零执行。
    重命令守卫在前（判定更宽：多目录 pytest 已属重命令，须先拦下）。

    Args:
        config: pytest 配置对象。
    """
    heavy = _load_guard_module(_HEAVY_GUARD_PATH, "bms_heavy_command_guard")
    if heavy is not None:
        heavy.pytest_configure(config)
    guard = _load_guard()
    if guard is not None:
        guard.pytest_configure(config)
    from bms_core.testing import plugin as base_plugin

    config.pluginmanager.register(base_plugin, "bms_testing_base_plugin")
    base_plugin.pytest_configure(config)
