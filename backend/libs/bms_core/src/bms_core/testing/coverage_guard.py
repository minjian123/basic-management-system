"""覆盖率入口守卫（本仓专属，强制）：走错入口立即报错，不给"跑完再说"的机会。

为什么必须存在（《AI开发规范》「覆盖率要求」/《测试规范》§6）：

- **禁止手工采集**：门禁只认 `[coverage].data_file`（由 `engkit.coverage_plugin` 采集）。
  `pytest --cov` / `--cov-report` 采出的数据与门禁不可比，会得出假缺口（实测：同一份代码
  `pytest-cov` 报 4 行缺口、门禁报 0 行；反之手工数据喂门禁报 516 行假缺口）。
- **禁止换落点**：`COVERAGE_FILE` / `BMS_COVERAGE_DATA` 指向 `.cache/coverage/` 之外，
  等于让门禁读不到、或读到别人的数据。

拦截时机：`pytest_configure` 最早期（由 `bms_testing_plugin` 在转调 engkit 之前调用），
违规即 `pytest.exit(code=2)`——不执行任何用例。

**唯一合法出口**（查缺口，不重跑用例）::

    python3 scripts/tools/preflight/coverage_report.py --module <点分模块>     # 模块级
    git diff --cached --name-only | python3 scripts/tools/preflight/coverage_report.py --changed

逃生口只给「排查插件自身」用：`BMS_COVERAGE_ENTRY_BYPASS=1`。CI 环境（`CI` 已设置）放行，
因为 CI 需要 `--cov-json` 产出 `backend/coverage.json` 显式证据。
"""

from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Any

import pytest

from bms_core.core.concurrent import ConcurrentStableList

__all__ = ["assert_entrypoint", "expected_data_dir"]

_FORBIDDEN_PREFIXES = (
    "--cov",
    "--cov-report",
    "--cov-config",
    "--cov-fail-under",
    "--cov-json",
)
"""禁止的覆盖率参数前缀（`--cov` 覆盖 `--cov=` / `--cov-<pkg>` 等全部变体）。"""

_DATA_ENVS = ("COVERAGE_FILE", "BMS_COVERAGE_DATA")
"""必须落在同一目录的环境变量（采集落点 / pytest-cov 数据文件）。"""

_BYPASS_ENV = "BMS_COVERAGE_ENTRY_BYPASS"
"""排障逃生口（仅排查插件自身；代码与文档中不得常规使用）。"""

_REPO_ROOT = Path(__file__).resolve().parents[6]
"""仓库根（本文件位于 `backend/libs/bms_core/src/bms_core/testing/`）。"""


def expected_data_dir() -> Path | None:
    """读 `[coverage].data_file` 取合法落点目录。

    Returns:
        Path | None: 落点目录；配置缺失或不可读时 None（此时跳过落点校验，不误伤 CI 单仓）。
    """
    config_path = _REPO_ROOT / "engkit.toml"
    try:
        with config_path.open("rb") as stream:
            config = tomllib.load(stream)
    except OSError, tomllib.TOMLDecodeError:
        return None
    relative = str((config.get("coverage") or {}).get("data_file") or "")  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType]
    if not relative:
        return None
    return (_REPO_ROOT / relative).resolve().parent


def _args_of(config: Any) -> ConcurrentStableList[str]:
    """取本次 pytest 的原始命令行参数。

    Args:
        config: pytest 配置对象。

    Returns:
        ConcurrentStableList[str]: 参数字符串（无 `invocation_params` 时为空）。
    """
    params = getattr(config, "invocation_params", None)
    raw = getattr(params, "args", None)
    result: ConcurrentStableList[str] = ConcurrentStableList()
    if not raw:
        return result
    for item in raw:
        result.add(str(item))
    return result


def _forbidden_args(config: Any) -> ConcurrentStableList[str]:
    """挑出被禁止的覆盖率参数。

    Args:
        config: pytest 配置对象。

    Returns:
        ConcurrentStableList[str]: 命中的参数。
    """
    hits: ConcurrentStableList[str] = ConcurrentStableList()
    for arg in _args_of(config):
        if arg.startswith(_FORBIDDEN_PREFIXES):
            hits.add(arg)
    return hits


def _misplaced_envs() -> ConcurrentStableList[str]:
    """挑出落点不在 `[coverage].data_file` 目录的环境变量。

    Returns:
        ConcurrentStableList[str]: 形如 `NAME=值` 的违规项。
    """
    problems: ConcurrentStableList[str] = ConcurrentStableList()
    expected = expected_data_dir()
    if expected is None:
        return problems
    for name in _DATA_ENVS:
        raw = os.environ.get(name, "").strip()
        if not raw:
            continue
        if Path(raw).expanduser().resolve().parent != expected:
            problems.add(f"{name}={raw}")
    return problems


def assert_entrypoint(config: Any) -> None:
    """校验覆盖率入口；违规立即终止会话（退出码 2）。

    Args:
        config: pytest 配置对象。

    Raises:
        pytest.exit: 命中禁止的参数或落点错位（`code=2`）。
    """
    if os.getenv(_BYPASS_ENV) == "1" or os.getenv("CI"):
        return
    hits = _forbidden_args(config)
    if hits:
        pytest.exit(
            "[coverage-entry] 禁止手工采集覆盖率：命中了 "
            + "、".join(hits)
            + "。覆盖率由 bms_testing_plugin + engkit coverage 采集与判定；"
            "查缺口请用 python scripts/tools/preflight/coverage_report.py "
            "（--module 模块级 / --changed 改动行），不要用 pytest --cov。",
            returncode=2,
        )
    misplaced = _misplaced_envs()
    if misplaced:
        expected = expected_data_dir()
        pytest.exit(
            "[coverage-entry] 覆盖率落点错位："
            + "、".join(misplaced)
            + f"。唯一合法落点目录是 {expected}（[coverage].data_file）；"
            "换目录会让门禁读不到数据。",
            returncode=2,
        )
