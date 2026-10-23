"""pytest 启动插件：**最早**启动覆盖率采集与守卫，再注册测试基座夹具（13_02；13_05 起实现外置）。

实现位置：覆盖率采集（导入即启动、按 pid 落盘）与重命令 / 全量测试守卫的**唯一实现**在跨仓工程化
工具包 `engkit`（`engkit.coverage_plugin` / `engkit.guard`）。本模块只做三件事：

1. **顶层**定位 engkit（先 `import engkit`，失败按 `ENGKIT_HOME` → 同级 `../engkit` 注入 `sys.path`），
   再 `import engkit.coverage_plugin` —— 采集必须早于**任何被测模块**（含 `bms_core`）导入，
   否则「导入期执行的行」永久漏计（历史实测：全仓 10 包行覆盖率长期停在 93.36%）；
2. `pytest_addoption` / `pytest_configure` / `pytest_sessionfinish` 一律**转调** engkit 的钩子
   （重命令守卫 → 全量守卫 → 落盘），本模块不含判定逻辑；
3. `pytest_configure` 里再注册 `bms_core.testing` 夹具（此时探针已启动，夹具导入行可被采集）。

为什么不复用 `scripts/tools/preflight/engkit_boot.py`：它顶层就导入 `bms_core`（裸集合护栏要求用插入序
集合类），那会把被测包拉到探针启动之前——正是本模块要避免的问题。路径探测口径与它保持一致。

环境变量（由预检 / CI / 选测执行器设置，键位见仓根 `engkit.toml` 的 `[coverage]`）：

- `BMS_COVERAGE_DATA`：覆盖率数据文件基址（xdist worker 各自落 `<基址>.<pid>`，由 `engkit coverage` 合并）；
- `BMS_COVERAGE_SOURCE`：采集范围（逗号分隔的包名，如 `bms_core,bms_platform`）；
- `ENGKIT_ALLOW_UNWRAPPED` / `BMS_ALLOW_UNWRAPPED`：显式绕过包装检查（仅排查包装器自身问题时用）。
"""

from __future__ import annotations

import importlib
import importlib.util
import os
import sys
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[1]
"""bms 仓库根（本文件位于 `backend/` 下）。"""


def _ensure_engkit() -> None:
    """确保 `import engkit` 可用。

    Raises:
        SystemExit: 既未安装、也找不到可用的平级克隆（退出码 2，并给出安装指引）。
    """
    if importlib.util.find_spec("engkit") is not None:
        return
    candidates: list[Path] = []
    env = os.environ.get("ENGKIT_HOME", "").strip()
    if env:
        candidates.append(Path(env))
    candidates.append(_REPO_ROOT.parent / "engkit")
    for candidate in candidates:
        source = candidate / "src"
        if (source / "engkit" / "__init__.py").is_file():
            sys.path.insert(0, str(source))
            return
    sys.stderr.write(
        "[engkit] 未找到 engkit：请在工作区平级克隆 engkit，或 `pip install engkit`，"
        "或设置 ENGKIT_HOME 指向其克隆目录\n"
    )
    raise SystemExit(2)


_ensure_engkit()

_plugin: Any = importlib.import_module("engkit.coverage_plugin")
"""跨仓工程化工具包的 pytest 入口插件（采集 + 守卫的唯一实现）。"""


def pytest_addoption(parser: Any) -> None:
    """注册守卫的 `--full` 选项（须在 collection 前完成）。

    Args:
        parser: pytest 的 Parser 对象。
    """
    _plugin.pytest_addoption(parser)


def pytest_configure(config: Any) -> None:
    """守卫（重命令 → 全量测试）→ 注册测试基座夹具。

    Args:
        config: pytest 配置对象。
    """
    _plugin.pytest_configure(config)
    from bms_core.testing import plugin as base_plugin

    config.pluginmanager.register(base_plugin, "bms_testing_base_plugin")
    base_plugin.pytest_configure(config)


def pytest_sessionfinish(session: Any, exitstatus: int) -> None:
    """测试会话结束：转调 engkit 落盘本进程的采集数据（xdist worker 各自一份）。

    Args:
        session: pytest 会话对象。
        exitstatus: 退出码。
    """
    _plugin.pytest_sessionfinish(session, exitstatus)
