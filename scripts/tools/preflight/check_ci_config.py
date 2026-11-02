#!/usr/bin/env python3
"""CI 配置自检（预检步骤，原预检脚本内联段抽出）：本仓专属检查留在本仓。

检查三项：

1. CI / 编排 YAML 可解析（`.gitlab-ci.yml` + `deploy/ci/templates/*.yml` + `deploy/compose/*.yml`）；
2. `backend-test` 里透传的 pytest 长选项均被本地 pytest 接受（防 `--kiwicms` 类拼错）；
3. 部署 CLI / 契约门禁关键资产就位。

用法::

    python3 scripts/tools/preflight/check_ci_config.py [bms 仓库根]

退出码：0 通过；1 有问题。
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path
from typing import cast

_SRC_ROOT = Path(__file__).resolve().parents[3] / "backend" / "libs" / "bms_core" / "src"
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))

from bms_core.core.concurrent import (  # noqa: E402
    ConcurrentStableDict,
    ConcurrentStableFrozenSet,
    ConcurrentStableList,
)

_ROOT = Path(__file__).resolve().parents[3]
"""bms 仓库根（本文件位于 `scripts/tools/preflight/`）。"""

STDIN_LIST = "-"
"""`--files-from` 取标准输入的标记（门禁通过管道传清单，不落临时文件）。"""

CI_ENTRY = ".gitlab-ci.yml"
"""CI 主配置：pytest 选项校验与 GitLab Lint 只对它生效。"""


def read_listed(source: str) -> ConcurrentStableFrozenSet[str] | None:
    """读取改动清单（一行一个仓根相对路径）。

    Args:
        source: 清单来源（文件路径或 `-`）；空串表示全量模式。

    Returns:
        ConcurrentStableFrozenSet[str] | None: 改动文件集合；全量模式返回 None。
    """
    if not source:
        return None
    text = sys.stdin.read() if source == STDIN_LIST else Path(source).read_text(encoding="utf-8")
    return ConcurrentStableFrozenSet(
        {
            line.strip().replace("\\", "/")
            for line in text.splitlines()
            if line.strip() and not line.strip().startswith("#")
        }
    )


def _yaml_parse(
    root: Path,
    failures: ConcurrentStableList[str],
    listed: ConcurrentStableFrozenSet[str] | None = None,
) -> None:
    """解析 CI / 编排 YAML 并核对关键资产。

    Args:
        root: 仓库根。
        failures: 失败收集列表。
        listed: 改动文件集合；None 表示全量模式。
    """
    try:
        import yaml  # type: ignore[import-not-found]
    except ModuleNotFoundError:
        print("\n[preflight] CI 配置自检：跳过（本机无 pyyaml）")
        return
    targets = [
        root / ".gitlab-ci.yml",
        *sorted((root / "deploy" / "ci" / "templates").glob("*.yml")),
        *sorted((root / "deploy" / "compose").glob("*.yml")),
    ]
    if listed is not None:
        targets = [path for path in targets if path.relative_to(root).as_posix() in listed]
    if not targets:
        return
    print("\n[preflight] CI 配置自检：CI / 编排 YAML 解析")
    for path in targets:
        rel = path.relative_to(root)
        try:
            yaml.safe_load(path.read_text(encoding="utf-8"))
            print(f"  通过（{rel}）")
        except Exception as exc:
            print(f"  失败（{rel}）：{exc}")
            failures.append(f"CI YAML 解析（{rel}）")
    if listed is not None:
        # 增量模式只解析改动的 YAML；「门禁资产就位」是全仓口径，交推送环与 CI
        return
    assets = [
        root / "scripts" / "tools" / "deploy" / "release.py",
        root / "deploy" / "ci" / "verify" / "contract-gate",
        root / "deploy" / "contracts" / "baseline",
        root / "backend" / "ops" / "contract_gate.py",
        root / "backend" / "ops" / "contract_smoke.py",
    ]
    for asset in assets:
        rel = asset.relative_to(root)
        if asset.exists():
            print(f"  通过（{rel} 就位）")
        else:
            print(f"  失败：{rel} 缺失")
            failures.append(f"门禁资产缺失（{rel}）")


def _pytest_flags(root: Path, backend: Path, failures: ConcurrentStableList[str]) -> None:
    """校验 `backend-test` 透传的 pytest 长选项。

    Args:
        root: 仓库根。
        backend: backend 目录。
        failures: 失败收集列表。
    """
    print("\n[preflight] CI 配置自检：backend-test 的 pytest 长选项校验")
    try:
        import yaml  # type: ignore[import-not-found]
    except ModuleNotFoundError:
        print("  跳过（本机无 pyyaml）")
        return
    loaded = yaml.safe_load((root / ".gitlab-ci.yml").read_text(encoding="utf-8"))
    stages = cast("dict[str, object]", loaded) if isinstance(loaded, dict) else {}
    backend_test = stages.get("backend-test", {})
    jobs = cast("dict[str, object]", backend_test) if isinstance(backend_test, dict) else {}
    raw_script = jobs.get("script", [])
    script = [str(line) for line in cast("list[object]", raw_script)] if isinstance(raw_script, list) else []
    joined = "\n".join(script)
    flags: ConcurrentStableList[str] = ConcurrentStableList()
    collecting = False
    for line in joined.splitlines():
        if "--pytest-cmd" in line or "--pytest-arg" in line:
            for match in re.finditer(r"--pytest-arg[= ]+(\S+)", line):
                flags.extend(re.findall(r"--[a-z][a-z0-9-]*", match.group(1)))
            continue
        if not collecting and "uv run pytest" in line:
            collecting = True
        if collecting:
            flags.extend(re.findall(r"--[a-z][a-z0-9-]*", line))
            if not line.rstrip().endswith("\\"):
                collecting = False
    unique = sorted(set(flags))
    if not unique:
        hint = "由选测执行器统一构造" if "run_selected.py" in joined else "未使用裸 pytest"
        print(f"  通过（pytest 选项{hint}；CI 未透传额外 --pytest-arg）")
        return
    help_out = subprocess.run(
        ["uv", "run", "python", "-m", "pytest", "--help"],
        cwd=backend,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    ).stdout
    unknown = [flag for flag in unique if flag not in help_out]
    if unknown:
        print(f"  失败：backend-test 使用但本地 pytest 未识别的选项：{unknown}")
        failures.append("CI pytest 选项校验")
    else:
        print(f"  通过（校验 {len(unique)} 个选项：{'、'.join(unique)}）")


def _gitlab_lint(root: Path, failures: ConcurrentStableList[str]) -> None:
    """可选：经 GitLab CI Lint API 校验流水线配置（有 token 时）。

    Args:
        root: 仓库根。
        failures: 失败收集列表。
    """
    env = root / "deploy" / ".env"
    if not env.is_file():
        return
    values: ConcurrentStableDict[str, str] = ConcurrentStableDict()
    for line in env.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.strip().startswith("#"):
            key, _, value = line.partition("=")
            values[key.strip()] = value.strip()
    token = values.get("GITLAB_API_TOKEN")
    api = values.get("GITLAB_API_URL")
    if not token or not api:
        return
    import json
    import urllib.request

    print("\n[preflight] CI 配置自检：GitLab CI Lint API")
    body = json.dumps({"content": (root / ".gitlab-ci.yml").read_text(encoding="utf-8")}).encode()
    request = urllib.request.Request(
        f"{api}/projects/2/ci/lint",
        data=body,
        headers={"PRIVATE-TOKEN": token, "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as resp:
            payload = json.load(resp)
        if payload.get("valid"):
            print("  通过")
        else:
            print(f"  失败：{payload.get('errors')}")
            failures.append("CI Lint API")
    except Exception as exc:
        print(f"  跳过（不可达：{exc}）")


def main(argv: ConcurrentStableList[str] | None = None) -> int:
    """入口。

    Args:
        argv: 命令行参数（缺省取 `sys.argv[1:]`）。

    Returns:
        int: 退出码（0 通过 / 1 有问题）。
    """
    parser = argparse.ArgumentParser(prog="check_ci_config", description="CI 配置自检（只判改动的配置文件）")
    parser.add_argument("root", nargs="?", default=str(_ROOT), help="仓库根（缺省为脚本所在仓）")
    parser.add_argument(
        "--files-from",
        default="",
        help="改动清单（一行一个相对仓根路径；`-` 读标准输入；缺省全量）",
    )
    args = parser.parse_args(None if argv is None else list(argv))
    root = Path(str(args.root)).resolve()
    listed = read_listed(str(args.files_from))
    failures: ConcurrentStableList[str] = ConcurrentStableList()
    _yaml_parse(root, failures, listed)
    # pytest 选项校验与 GitLab Lint 都以 `.gitlab-ci.yml` 为输入：它没改就一次都不该发
    if listed is None or CI_ENTRY in listed:
        _pytest_flags(root, root / "backend", failures)
        _gitlab_lint(root, failures)
    if failures:
        print(f"\n[check_ci_config] 失败 {len(failures)} 项：{'、'.join(failures)}")
        return 1
    print("\n[check_ci_config] 通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
