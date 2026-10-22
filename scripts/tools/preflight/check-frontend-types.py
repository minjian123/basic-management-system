#!/usr/bin/env python3
"""前端类型门禁（预检步骤，原 `check-preflight.py` 内联段抽出）：按变更逐个受影响工程跑类型检查。

缺口背景（2026-10-21）：`desktop-build` / `module-check` 的 `vue-tsc` 报错此前只在 CI 暴露——
本地定向档不跑前端类型检查，契约字段变可选、字段类型改名这类错误推送后才发现。本步按 git 变更
自动定向，只跑受影响工程。

用法::

    python3 scripts/tools/preflight/check-frontend-types.py [bms 仓库根]

退出码：0 全部通过（或无需检查）；1 有工程失败。
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

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


def _task_for(manifest: Path, name: str) -> str:
    """按 `package.json` 决定执行哪个脚本。

    Args:
        manifest: 工程的 `package.json`。
        name: 包名。

    Returns:
        str: 任务名（无可用任务时为空串）。
    """
    try:
        payload = json.loads(manifest.read_text(encoding="utf-8"))
    except OSError, ValueError:
        return ""
    scripts = payload.get("scripts") or {}
    if "typecheck" in scripts:
        return "typecheck"
    if name.endswith("desktop") and "build" in scripts:
        return "build"
    return ""


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
        print("\n[preflight] 前端类型检查：跳过（pnpm 或仓库根 node_modules 未就位）")
        return 0
    cfg = load(Path(config_path()))
    changed, _ = gitutil.changes(root, "origin/main")
    result = selection.build_frontend_selection(cfg, changed)
    if not result.packages:
        print("\n[preflight] 前端类型检查：跳过（本次无前端工程受影响）")
        return 0
    packages = {package.name: package for package in selection.discover_frontend_packages(cfg)}
    failures = 0
    for name in result.packages:
        package = packages.get(name)
        if package is None:
            continue
        manifest = root / package.path / "package.json"
        task = _task_for(manifest, name)
        if not task:
            continue
        print(f"\n[preflight] 前端类型：{name}（{task}）\n  $ pnpm --filter {name} run {task}")
        code = subprocess.run([pnpm, "--filter", name, "run", task], cwd=root, check=False).returncode
        if code != 0:
            print(f"  失败（退出码 {code}）")
            failures += 1
        else:
            print("  通过")
    if failures:
        print(f"\n[check-frontend-types] 失败 {failures} 项")
        return 1
    print("\n[check-frontend-types] 通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
