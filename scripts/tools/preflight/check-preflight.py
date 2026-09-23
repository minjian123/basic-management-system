#!/usr/bin/env python3
"""本地预检（preflight）：推送前在本地快速跑 CI 关键门禁，避免「改一点、等整条流水线」的慢循环。

覆盖（按序执行，失败汇总、末尾给结论）：

1. **CI 配置自检**：`.gitlab-ci.yml` YAML 解析；`backend-test` 里 `uv run pytest` 的长选项逐项用本地
   `pytest --help` 校验（防 `--kiwicms` 之类拼错）；可选 GitLab CI Lint（有 token 时）。
2. **后端静态**：`ruff check` / `ruff format --check` / `pyright`。
3. **后端测试**：聚合全量（含覆盖率门禁）+ **工程级范围**（`bms_core` 与各服务目录各跑一次，验证
   「每工程只跑本工程」不落根全量）。
4. **基座与边界**：`check-base` / `check-backend-base(+--self-test)` /
   `check-service-boundaries(+--self-test)` / `check-status` / 网关 `gateway_config check` /
   公开契约 `contract_snapshot check`。

用法::

    python3 scripts/tools/preflight/check-preflight.py [bms 仓库根] [--fast] [--no-scope] [--no-cov]

    --fast       只跑静态与基座/边界检查（跳过 pytest）
    --no-scope   跳过工程级范围测试（只跑聚合全量）
    --no-cov     跳过覆盖率门禁（`--no-cov` 需已装 pytest-cov 时用 `-p no:cov`）
"""

import os
import re
import subprocess
import sys
from pathlib import Path

_ROOTS = ("libs/bms_core", "services/platform", "services/identity", "services/tenant", "services/org",
          "services/file", "services/notification", "services/search", "services/ai", "services/report")


def _run(label: str, cmd: list[str], cwd: Path, failures: list[str]) -> bool:
    """执行一条命令并打印结果。

    Args:
        label: 步骤标签。
        cmd: 命令与参数。
        cwd: 工作目录。
        failures: 失败收集列表。

    Returns:
        bool: 是否成功。
    """
    print(f"\n[preflight] {label}\n  $ {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    tail = "\n".join((result.stdout + result.stderr).splitlines()[-12:])
    if result.returncode != 0:
        print(tail)
        failures.append(label)
        return False
    print("  通过" + (f"（{tail.splitlines()[-1]}）" if tail.strip() else ""))
    return True


def _yaml_parse(root: Path, failures: list[str]) -> None:
    """解析 `.gitlab-ci.yml`（结构自检）。

    Args:
        root: bms 仓库根。
        failures: 失败收集列表。
    """
    try:
        import yaml  # type: ignore[import-not-found]
    except ModuleNotFoundError:
        print("\n[preflight] CI 配置自检：跳过（本机无 pyyaml）")
        return
    print("\n[preflight] CI 配置自检：.gitlab-ci.yml 解析")
    try:
        yaml.safe_load((root / ".gitlab-ci.yml").read_text(encoding="utf-8"))
        print("  通过")
    except Exception as exc:  # noqa: BLE001
        print(f"  失败：{exc}")
        failures.append("CI YAML 解析")


def _pytest_flags_from_ci(root: Path, backend: Path, failures: list[str]) -> None:
    """校验 `backend-test` 里 `uv run pytest` 的长选项均被本地 pytest 接受（防拼错）。

    Args:
        root: bms 仓库根。
        backend: backend 目录。
        failures: 失败收集列表。
    """
    print("\n[preflight] CI 配置自检：backend-test 的 pytest 长选项校验")
    try:
        import yaml  # type: ignore[import-not-found]
    except ModuleNotFoundError:
        print("  跳过（本机无 pyyaml）")
        return
    data = yaml.safe_load((root / ".gitlab-ci.yml").read_text(encoding="utf-8"))
    script = [str(line) for line in data.get("backend-test", {}).get("script", [])]
    joined = "\n".join(script)
    # 仅取 `uv run pytest` 命令自身（含反斜杠续行）的选项，避免把 `uv sync --frozen` 等误算
    lines = joined.splitlines()
    flags: list[str] = []
    collecting = False
    for line in lines:
        if not collecting and "uv run pytest" in line:
            collecting = True
        if collecting:
            flags.extend(re.findall(r"--[a-z][a-z0-9-]*", line))
            if not line.rstrip().endswith("\\"):
                collecting = False
    flags = sorted(set(flags))
    help_out = subprocess.run(
        ["uv", "run", "python", "-m", "pytest", "--help"], cwd=backend, capture_output=True, text=True
    ).stdout
    unknown = [flag for flag in flags if flag not in help_out]
    if unknown:
        print(f"  失败：backend-test 使用但本地 pytest 未识别的选项：{unknown}")
        failures.append("CI pytest 选项校验")
    else:
        print(f"  通过（校验 {len(flags)} 个选项：{'、'.join(flags)}）")


def _gitlab_ci_lint(root: Path, failures: list[str]) -> None:
    """可选：经 GitLab CI Lint API 校验流水线配置（有 token 时）。

    Args:
        root: bms 仓库根。
        failures: 失败收集列表。
    """
    env = root / "deploy" / ".env"
    if not env.is_file():
        return
    values: dict[str, str] = {}
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
        f"{api}/projects/2/ci/lint", data=body, headers={"PRIVATE-TOKEN": token, "Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as resp:  # noqa: S310
            payload = json.load(resp)
        if payload.get("valid"):
            print("  通过")
        else:
            print(f"  失败：{payload.get('errors')}")
            failures.append("CI Lint API")
    except Exception as exc:  # noqa: BLE001
        print(f"  跳过（不可达：{exc}）")


def main() -> int:
    """入口：执行本地预检。

    Returns:
        int: 退出码（0 全通过 / 1 有失败项）。
    """
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    root = Path(args[0] if args else ".").resolve()
    backend = root / "backend"
    fast = "--fast" in sys.argv
    no_scope = "--no-scope" in sys.argv
    no_cov = "--no-cov" in sys.argv
    failures: list[str] = []

    _yaml_parse(root, failures)
    _pytest_flags_from_ci(root, backend, failures)
    _gitlab_ci_lint(root, failures)

    if not fast:
        _run("后端静态：ruff check", ["uv", "run", "ruff", "check", "."], backend, failures)
        _run("后端静态：ruff format --check", ["uv", "run", "ruff", "format", "--check", "."], backend, failures)
        _run("后端静态：pyright", ["uv", "run", "pyright"], backend, failures)

        cov_args = [] if no_cov else [
            "--cov=bms_core", "--cov=bms_platform", "--cov=bms_identity", "--cov=bms_tenant", "--cov=bms_org",
            "--cov=bms_file", "--cov=bms_notification", "--cov=bms_search", "--cov=bms_ai", "--cov=bms_report",
            "--cov-branch", "--cov-fail-under=70",
        ]
        _run("后端测试：聚合全量", ["uv", "run", "pytest", "-q", *cov_args], backend, failures)
        if not no_scope:
            for rel in _ROOTS:
                _run(f"后端测试：工程级范围（{rel}）", ["uv", "run", "pytest", "-q"], backend / rel, failures)

    _run("基座：check-base", [sys.executable, "scripts/tools/base-check/check-base.py", str(root)], root, failures)
    _run(
        "基座：check-backend-base",
        [sys.executable, "scripts/tools/base-check/check-backend-base.py", str(root)],
        root,
        failures,
    )
    _run(
        "基座：check-backend-base --self-test",
        [sys.executable, "scripts/tools/base-check/check-backend-base.py", "--self-test"],
        root,
        failures,
    )
    _run(
        "边界：check-service-boundaries",
        [sys.executable, "scripts/tools/base-check/check-service-boundaries.py", str(root)],
        root,
        failures,
    )
    _run(
        "边界：check-service-boundaries --self-test",
        [sys.executable, "scripts/tools/base-check/check-service-boundaries.py", "--self-test"],
        root,
        failures,
    )
    _run(
        "文档：check-status",
        [sys.executable, "scripts/tools/check-docs/check-status.py", "--root", str(root)],
        root,
        failures,
    )
    _run(
        "网关：gateway_config check（服务目录零漂移）",
        [sys.executable, "backend/ops/gateway_config.py", "check", "--root", str(root)],
        root,
        failures,
    )
    _run(
        "契约：contract_snapshot check（公开契约零漂移）",
        ["uv", "run", "python", "-m", "ops.contract_snapshot", "check", "--root", str(root)],
        backend,
        failures,
    )

    print("\n================ preflight 结论 ================")
    if failures:
        print(f"失败 {len(failures)} 项：")
        for item in failures:
            print(f"  - {item}")
        return 1
    print("全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
