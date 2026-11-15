#!/usr/bin/env python3
"""前端用例门禁（预检步骤）：按变更跑受影响前端工程的 vitest（有覆盖率脚本时一并判定）。

缺口背景（2026-11-15，bms#1679 / #1680）：前端用例与覆盖率此前**只在 CI 跑**，推送环只有
typecheck / build，连续两轮 CI 往返才发现问题——

- #1679：状态标签改从选项集快照取，用例还断言硬编码「启用」→ 用例红；
- #1680：用例修好后，同一分支的覆盖率缺口（`?? []` 与 catch 降级）才暴露 → 覆盖率红。

本步按 git 变更推导受影响工程（依赖反向闭包，改共享包会带上依赖它的应用），有 `test:cov`
的工程连覆盖率一起判，与 CI 的 `test:cov` 同口径。

用法::

    python3 scripts/tools/preflight/check_frontend_tests.py [bms 仓库根]

退出码：0 全部通过（或无需检查）；1 有工程失败。
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import cast

_SRC_ROOT = Path(__file__).resolve().parents[3] / "backend" / "libs" / "bms_core" / "src"
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))

from bms_core.core.concurrent import ConcurrentStableList  # noqa: E402

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from engkit_boot import config_path, ensure_engkit  # noqa: E402

_ROOT = _SCRIPT_DIR.parents[2]
"""bms 仓库根（本文件位于 `scripts/tools/preflight/`）。"""


def _task_for(manifest: Path) -> str:
    """按 `package.json` 决定执行哪个用例脚本。

    有覆盖率脚本时优先 `test:cov`（与 CI 同口径，能挡住分支缺口）；否则退回 `test`。

    Args:
        manifest: 工程的 `package.json`。

    Returns:
        str: 任务名（无可用任务时为空串）。
    """
    try:
        payload = json.loads(manifest.read_text(encoding="utf-8"))
    except OSError, ValueError:
        return ""
    scripts = cast("dict[str, object]", payload.get("scripts") or {})
    if "test:cov" in scripts:
        return "test:cov"
    if "test" in scripts:
        return "test"
    return ""


def _has_specs(package_dir: Path) -> bool:
    """工程内是否存在用例文件（无用例的包直接跳过，不算失败）。

    Args:
        package_dir: 工程根目录。

    Returns:
        bool: 存在 `*.spec.ts`（排除 `node_modules`）返回 True。
    """
    return any("node_modules" not in path.parts for path in package_dir.rglob("*.spec.ts"))


def main(argv: ConcurrentStableList[str] | None = None) -> int:
    """入口。

    Args:
        argv: 命令行参数（缺省取 `sys.argv[1:]`）。

    Returns:
        int: 退出码（0 通过 / 1 有失败）。
    """
    args = ConcurrentStableList(sys.argv[1:] if argv is None else argv)
    paths = [item for item in args if not item.startswith("-")]
    root = Path(paths[0]).resolve() if paths else _ROOT
    ensure_engkit()
    from engkit import gitutil, selection
    from engkit.config import load

    pnpm = shutil.which("pnpm")
    if pnpm is None or not (root / "node_modules").exists():
        print("\n[preflight] 前端用例：跳过（pnpm 或仓库根 node_modules 未就位）")
        return 0
    cfg = load(Path(config_path()))
    changed, _ = gitutil.changes(root, "origin/main")
    result = selection.build_frontend_selection(cfg, changed)
    if not result.packages:
        print("\n[preflight] 前端用例：跳过（本次无前端工程受影响）")
        return 0
    packages = {package.name: package for package in selection.discover_frontend_packages(cfg)}
    failures = 0
    ran = 0
    for name in result.packages:
        package = packages.get(name)
        if package is None:
            continue
        package_dir = root / package.path
        manifest = package_dir / "package.json"
        task = _task_for(manifest)
        if not task:
            print(f"[preflight] 前端用例：{name} 无 test 脚本，跳过")
            continue
        if not _has_specs(package_dir):
            print(f"[preflight] 前端用例：{name} 无用例文件，跳过")
            continue
        ran += 1
        print(f"\n[preflight] 前端用例：{name}（{task}）\n  $ pnpm --filter {name} run {task}")
        # 推送环是「按变更已选包」的内部授权场景，与开发环同口径注入选包标记
        # （`vitest_guard` 据此放行；全量测试仍只由 CI 执行）。
        env = {**os.environ, "ENGKIT_VITEST_SELECTED": name}
        code = subprocess.run([pnpm, "--filter", name, "run", task], cwd=root, check=False, env=env).returncode
        if code != 0:
            print(f"  失败（退出码 {code}）")
            failures += 1
        else:
            print("  通过")
    if failures:
        print(f"\n[check_frontend_tests] 失败 {failures} 项（共跑 {ran} 个工程）")
        return 1
    print(f"\n[check_frontend_tests] 通过（共跑 {ran} 个工程）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
