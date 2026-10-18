#!/usr/bin/env python3
"""本地预检（preflight）：推送前在本地跑 CI 关键门禁，**默认走快路径**、全量须显式申请。

档位（**默认绝不全量**——全量与集成交 CI 按需触发，见《测试规范》「执行方式」节与
《AI开发规范》「覆盖率要求」节）：

1. **缺省＝定向档**（约 1~2 分钟）：静态 + 基座 / 边界 + **按 git 变更自动定向**的用例与覆盖率门禁
   （只跑受影响工程的测试目录，只对变更源文件开 100% 覆盖率门禁；无后端变更则跳过 pytest）。
2. `--fast`：只跑静态与基座 / 边界（跳过 pytest；秒级日常自检）。
3. `--full`：**全量档**（聚合全量 + 工程级范围；约 5~6 分钟）——只用于收口 / 跨域大改动的显式申请。

覆盖（按序执行，失败汇总、末尾给结论）：

- **CI 配置自检**：`.gitlab-ci.yml` 与 `deploy/ci/templates/*.yml`（服务子流水线模板）YAML 解析；
  `backend-test` 里 `uv run pytest` 的长选项逐项用本地 `pytest --help` 校验（防 `--kiwicms` 之类拼错）；
  可选 GitLab CI Lint（有 token 时）。
- **后端静态**：`ruff check` / `ruff format --check` / `pyright`。
- **后端测试**：定向档＝受影响工程的测试目录 + 变更源文件覆盖率门禁；全量档＝聚合全量（含覆盖率门禁）
  + **工程级范围**（`bms_core` 与各服务目录各跑一次，验证「每工程只跑本工程」不落根全量）。
- **基座与边界**：`check-base` / `check-backend-base(+--self-test)` /
  `check-service-boundaries(+--self-test)` / `boundary_metrics`（越界 / 跨库 / 例外计数） /
  `check-status` / 网关 `gateway_config check` / 公开契约 `contract_snapshot check`。
- **预算护栏**：单步与总体耗时双上限，超时**立即中止**并给出「全量交 CI」提示（防误跑长命令）。

用法::

    python3 scripts/tools/preflight/check-preflight.py [bms 仓库根] [--fast|--full]
                                                    [--no-scope] [--no-cov]
                                                    [--budget-seconds N] [--step-seconds N]
                                                    [--self-test]

    --fast            只跑静态与基座/边界检查（跳过 pytest）
    --full            全量档（聚合全量 + 工程级范围）；缺省为定向档，全量必须显式申请
    --no-scope        （全量档）跳过工程级范围测试
    --no-cov          跳过覆盖率门禁（`--no-cov` 需已装 pytest-cov 时用 `-p no:cov`）
    --budget-seconds  总体耗时上限（定向档默认 180s；全量档默认 1200s）
    --step-seconds    单步耗时上限（定向档默认 120s；全量档默认 600s）
    --self-test       只跑本脚本的定向推导与预算护栏自测（不触网、不跑测试）
"""

import contextlib
import re
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

# bms_core 源码根：脚本在仓库内运行，集合声明统一落插入序集合类（ConcurrentStable*）。
_SRC_ROOT = Path(__file__).resolve().parents[3] / "backend" / "libs" / "bms_core" / "src"
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))

# 同目录选测器（变更 → 受影响测试的单一来源；见 13_01 详细设计）
_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

import test_selection  # noqa: E402

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList  # noqa: E402

_ROOTS = (
    "libs/bms_core",
    "services/txn",
    "services/platform",
    "services/identity",
    "services/tenant",
    "services/file",
    "services/notification",
    "services/search",
    "services/ai",
    "services/report",
)


def configure_stdio():
    """输出统一 UTF-8（Windows 管道 / 重定向下同样稳妥）。"""
    for stream in (sys.stdout, sys.stderr):
        with contextlib.suppress(Exception):
            stream.reconfigure(encoding="utf-8")


@dataclass
class _Budget:
    """预算护栏：单步 / 总体耗时双上限，超限即中止后续步骤（防误跑长命令）。

    Attributes:
        step_seconds: 单步耗时上限（秒）。
        total_seconds: 总体耗时上限（秒）。
        started: 起始时刻（`time.monotonic`）。
        exhausted: 总体预算是否已耗尽（耗尽即跳过剩余步骤）。
    """

    step_seconds: float
    total_seconds: float
    started: float = field(default_factory=time.monotonic)
    exhausted: bool = False

    def remaining(self) -> float:
        """总体剩余预算（秒；可为负）。"""
        return self.total_seconds - (time.monotonic() - self.started)


_GUARD: _Budget | None = None
"""当前预算护栏（`main` 装配；`None` 表示不设限）。"""


def _run(
    label: str,
    cmd: ConcurrentStableList[str],
    cwd: Path,
    failures: ConcurrentStableList[str],
    *,
    timeout: float | None = None,
) -> bool:
    """执行一条命令并打印结果（受预算护栏约束）。

    Args:
        label: 步骤标签。
        cmd: 命令与参数。
        cwd: 工作目录。
        failures: 失败收集列表。
        timeout: 本步显式超时（秒）；缺省取护栏的单步上限。

    Returns:
        bool: 是否成功。
    """
    if _GUARD is not None and _GUARD.exhausted:
        return False
    limit = timeout
    if _GUARD is not None:
        remaining = _GUARD.remaining()
        if remaining <= 0:
            print(
                f"\n[preflight] {label}\n"
                f"  中止（总体预算 {_GUARD.total_seconds:.0f}s 已耗尽；全量与集成交 CI，"
                "确需本地全量请显式 --full）"
            )
            _GUARD.exhausted = True
            failures.add(f"预算护栏（总体超时）：{label}")
            return False
        limit = min(limit, remaining) if limit is not None else min(_GUARD.step_seconds, remaining)
    print(f"\n[preflight] {label}\n  $ {' '.join(cmd)}")
    try:
        result = subprocess.run(
            cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=limit
        )
    except subprocess.TimeoutExpired:
        print(
            f"  中止（单步超时 {limit:.0f}s；全量与集成交 CI，确需本地全量请显式 --full）\n"
            "  提示：`uv` 拉起的长任务可能残留子进程，必要时手工结束。"
        )
        failures.add(f"预算护栏（单步超时）：{label}")
        return False
    tail = "\n".join((result.stdout + result.stderr).splitlines()[-12:])
    if result.returncode != 0:
        print(tail)
        failures.add(label)
        return False
    print("  通过" + (f"（{tail.splitlines()[-1]}）" if tail.strip() else ""))
    return True


def _yaml_parse(root: Path, failures: ConcurrentStableList[str]) -> None:
    """解析 CI / 编排配置（`.gitlab-ci.yml` + `deploy/ci/templates/*.yml` + `deploy/compose/*.yml`）。

    Args:
        root: bms 仓库根。
        failures: 失败收集列表。
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
    print("\n[preflight] CI 配置自检：CI / 编排 YAML 解析")
    for path in targets:
        rel = path.relative_to(root)
        try:
            yaml.safe_load(path.read_text(encoding="utf-8"))
            print(f"  通过（{rel}）")
        except Exception as exc:
            print(f"  失败（{rel}）：{exc}")
            failures.add(f"CI YAML 解析（{rel}）")
    # 部署 / 回滚 / 门禁 CLI 结构层存在性（09_02；行为由 Kiwi 2185 护栏用例覆盖）
    cli = root / "scripts" / "tools" / "deploy" / "release.py"
    if cli.is_file():
        print("  通过（scripts/tools/deploy/release.py 就位）")
    else:
        print("  失败：scripts/tools/deploy/release.py 缺失")
        failures.add("部署 CLI 缺失")
    # 契约门禁结构层存在性（09_03；行为由 Kiwi 2186 护栏用例覆盖）
    gate_assets = [
        root / "deploy" / "ci" / "verify" / "contract-gate",
        root / "deploy" / "contracts" / "baseline",
        root / "backend" / "ops" / "contract_gate.py",
        root / "backend" / "ops" / "contract_smoke.py",
    ]
    for asset in gate_assets:
        rel = asset.relative_to(root)
        if asset.exists():
            print(f"  通过（{rel} 就位）")
        else:
            print(f"  失败：{rel} 缺失")
            failures.add(f"契约门禁资产缺失（{rel}）")


def _pytest_flags_from_ci(root: Path, backend: Path, failures: ConcurrentStableList[str]) -> None:
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
    # 口径（13_01 起）：`backend-test` 不再写裸 `uv run pytest`，改由 `run-selected.py` 统一构造 pytest
    # 选项；CI 只经 `--pytest-cmd` 指定执行器、经 `--pytest-arg` 透传额外选项。故：
    #   - `--pytest-cmd` 行不参与校验（其值 `uv run pytest` 不是选项）；
    #   - `--pytest-arg` 的取值逐个校验（防 `--kiwicms` 类拼错）；
    #   - 两者都没有时视为「选项全由执行器构造」，通过并说明。
    lines = joined.splitlines()
    flags: ConcurrentStableList[str] = ConcurrentStableList()
    collecting = False
    for line in lines:
        if "--pytest-cmd" in line or "--pytest-arg" in line:
            for match in re.finditer(r"--pytest-arg[= ]+(\S+)", line):
                flags.update(re.findall(r"--[a-z][a-z0-9-]*", match.group(1)))
            continue
        if not collecting and "uv run pytest" in line:
            collecting = True
        if collecting:
            flags.update(re.findall(r"--[a-z][a-z0-9-]*", line))
            if not line.rstrip().endswith("\\"):
                collecting = False
    flags = sorted(set(flags))
    if not flags:
        if "run-selected.py" in joined:
            print("  通过（pytest 选项由 run-selected.py 统一构造；CI 未透传额外 --pytest-arg）")
        else:
            print("  跳过（backend-test 未使用裸 pytest）")
        return
    help_out = subprocess.run(
        ["uv", "run", "python", "-m", "pytest", "--help"],
        cwd=backend,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    ).stdout
    unknown = [flag for flag in flags if flag not in help_out]
    if unknown:
        print(f"  失败：backend-test 使用但本地 pytest 未识别的选项：{unknown}")
        failures.add("CI pytest 选项校验")
    else:
        print(f"  通过（校验 {len(flags)} 个选项：{'、'.join(flags)}）")


def _gitlab_ci_lint(root: Path, failures: ConcurrentStableList[str]) -> None:
    """可选：经 GitLab CI Lint API 校验流水线配置（有 token 时）。

    Args:
        root: bms 仓库根。
        failures: 失败收集列表。
    """
    env = root / "deploy" / ".env"
    if not env.is_file():
        return
    values: ConcurrentStableDict[str, str] = ConcurrentStableDict()
    for line in env.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.strip().startswith("#"):
            key, _, value = line.partition("=")
            values.set(key.strip(), value.strip())
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
        with urllib.request.urlopen(request, timeout=15) as resp:
            payload = json.load(resp)
        if payload.get("valid"):
            print("  通过")
        else:
            print(f"  失败：{payload.get('errors')}")
            failures.add("CI Lint API")
    except Exception as exc:
        print(f"  跳过（不可达：{exc}）")


def _frontend_api_types(root: Path, failures: ConcurrentStableList[str]) -> None:
    """前端契约类型零漂移（04-1-1）：node 直接跑生成器 `--check`，与仓库产物比对。

    不走 pnpm（避免触发依赖重装）；node 或依赖未就位时跳过并提示。

    Args:
        root: bms 仓库根。
        failures: 失败收集列表。
    """
    pkg_dir = root / "frontend" / "packages" / "api-types"
    script = pkg_dir / "scripts" / "generate.mjs"
    node = shutil.which("node")
    if not script.is_file() or node is None or not (pkg_dir / "node_modules").exists():
        print("\n[preflight] 前端契约类型：跳过（@bms/api-types / node 依赖未就位）")
        return
    _run(
        "前端：api-types 契约类型零漂移",
        ConcurrentStableList([node, "scripts/generate.mjs", "--check"]),
        pkg_dir,
        failures,
    )


_DEFAULT_SCOPED_BUDGET = (120.0, 180.0)
"""定向档预算（单步秒数, 总体秒数）——默认快路径的护栏。"""
_DEFAULT_FULL_BUDGET = (600.0, 1200.0)
"""全量档预算（单步秒数, 总体秒数）——`--full` 显式申请时放宽。"""


def _numeric_flag(name: str, default: float) -> float:
    """取 `--name N` 形式的数值参数。

    Args:
        name: 选项名（含前缀 `--`）。
        default: 缺省值（缺选项 / 非数值时回退）。

    Returns:
        float: 数值参数。
    """
    if name in sys.argv:
        index = sys.argv.index(name)
        if index + 1 < len(sys.argv):
            with contextlib.suppress(ValueError):
                return float(sys.argv[index + 1])
    return default


def _positional_root() -> str:
    """取位置参数（仓库根）；跳过选项与选项值（`--budget-seconds 180` 的 `180` 不算根）。"""
    skip_next = False
    for token in sys.argv[1:]:
        if skip_next:
            skip_next = False
            continue
        if token in ("--budget-seconds", "--step-seconds"):
            skip_next = True
            continue
        if not token.startswith("-"):
            return token
    return "."


def _changed_paths(root: Path) -> ConcurrentStableList[str]:
    """取本次改动路径（相对仓库根）：工作区 + 未跟踪（相对 `origin/main`）。

    Args:
        root: bms 仓库根。

    Returns:
        ConcurrentStableList[str]: 去重后的改动路径（相对仓库根，posix 形态）。
    """
    paths: ConcurrentStableList[str] = ConcurrentStableList()
    for args in (["diff", "--name-only", "origin/main"], ["ls-files", "--others", "--exclude-standard"]):
        result = subprocess.run(
            ["git", *args], cwd=root, capture_output=True, text=True, encoding="utf-8", errors="replace"
        )
        if result.returncode != 0:
            continue
        for line in result.stdout.splitlines():
            rel = line.strip().replace("\\", "/")
            if rel and rel not in paths:
                paths.add(rel)
    return paths


def _scope_targets(
    backend: Path, changes: ConcurrentStableList[str]
) -> tuple[ConcurrentStableList[str], ConcurrentStableList[str]]:
    """按变更路径推导定向范围：（测试文件, 覆盖率目标模块）——委托选测器（单一来源）。

    推导规则（目录同构 + AST 导入图 + 基础模块退化 + ops / 预检脚本特殊路径）只在
    `test_selection.py` 维护一处，预检与 CI 共用；本函数仅做返回类型适配。

    Args:
        backend: `backend` 目录。
        changes: 改动路径（相对仓库根）。

    Returns:
        tuple[ConcurrentStableList[str], ConcurrentStableList[str]]: （测试文件, 覆盖率目标模块）。
    """
    selection = test_selection.build_selection(backend, changes)
    return ConcurrentStableList(selection.test_paths), ConcurrentStableList(selection.cov_modules)


def _run_scoped(root: Path, backend: Path, failures: ConcurrentStableList[str], *, no_cov: bool) -> None:
    """定向档：按 git 变更跑受影响测试文件 + 变更源文件覆盖率门禁（含扩圈）。

    Args:
        root: bms 仓库根。
        backend: `backend` 目录。
        failures: 失败收集列表。
        no_cov: 是否跳过覆盖率门禁。
    """
    changes = _changed_paths(root)
    selection = test_selection.build_selection(backend, changes)
    print(f"\n[preflight] 定向：按 git 变更（{len(changes)} 个文件）推导受影响范围")
    if selection.reason:
        print(f"  退化：{selection.reason}")
    for note in selection.notes:
        print(f"  说明：{note}")
    if not selection.test_paths:
        print("  无后端变更 ⇒ 跳过 pytest（静态与基座 / 边界段已执行；全量交 CI）")
        return
    ratio = selection.picked / selection.total if selection.total else 0.0
    print(f"  测试文件：{selection.picked}/{selection.total}（{ratio:.1%}）")
    if selection.cov_modules and not no_cov:
        print(f"  覆盖率门禁（行 + 分支 100%）：{'、'.join(selection.cov_modules)}")
    else:
        print("  覆盖率门禁：跳过（无变更源文件或 --no-cov）")

    # 变更清单落临时文件交给执行器：与本地推导同一输入，避免二次 git diff 口径漂移
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".txt", delete=False) as handle:
        handle.write("\n".join(changes))
        list_path = handle.name
    cmd: ConcurrentStableList[str] = ConcurrentStableList(
        [
            sys.executable,
            "scripts/tools/preflight/run-selected.py",
            "--root",
            str(root),
            "--changed-file-list",
            list_path,
            "--pytest-cwd",
            "backend",
            "--pytest-cmd",
            "uv run pytest",
            "--max-rounds",
            "2",
            "--cov-json",
            "backend/coverage.json",
        ]
    )
    if no_cov:
        cmd.add("--no-cov")
    else:
        cmd.update(["--cov-fail-under", "100"])
    try:
        _run("后端测试：定向（选测 + 覆盖率门禁 + 扩圈）", cmd, root, failures)
    finally:
        Path(list_path).unlink(missing_ok=True)


def _self_test() -> int:
    """自测：定向推导与预算护栏（不触网、不跑测试）。

    Returns:
        int: 退出码（0 通过 / 1 失败）。
    """
    print("[self-test] preflight 定向推导与预算护栏")
    backend = Path(__file__).resolve().parents[3] / "backend"
    selection = test_selection.build_selection(
        backend,
        ConcurrentStableList(
            [
                "backend/libs/bms_core/src/bms_core/db/bootstrap.py",
                "backend/libs/bms_core/tests/alembic/test_auto_create_tables.py",
                "backend/services/txn/src/bms_txn/services/recovery.py",
                "backend/ops/test_db.py",
                "bms文档/规范/AI开发规范.md",
                "frontend/apps/portal/src/main.ts",
            ]
        ),
    )
    docs_selection = test_selection.build_selection(
        backend, ConcurrentStableList(["bms文档/规范/AI开发规范.md", "frontend/apps/portal/src/main.ts"])
    )
    guard = _Budget(step_seconds=0.0, total_seconds=0.0)
    prefixes = ("libs/bms_core/tests/", "services/txn/tests/")
    checks = ConcurrentStableList[tuple[str, bool]](
        [
            (
                "定向只选受影响工程的测试文件",
                bool(selection.test_paths) and all(p.startswith(prefixes) for p in selection.test_paths),
            ),
            ("定向含基座测试文件", any(p.startswith("libs/bms_core/tests/") for p in selection.test_paths)),
            ("定向含服务测试文件", any(p.startswith("services/txn/tests/") for p in selection.test_paths)),
            ("ops 变更并入基座 ops 用例", any("/tests/ops/" in f"/{p}" for p in selection.test_paths)),
            (
                "覆盖率只取包内源文件（基座 + 服务）",
                selection.cov_modules == ("bms_core.db.bootstrap", "bms_txn.services.recovery"),
            ),
            (
                "纯文档 / 前端变更不引测试与覆盖率",
                not docs_selection.test_paths and not docs_selection.cov_modules,
            ),
            ("零预算即判耗尽", guard.remaining() <= 0),
        ]
    )
    failures = ConcurrentStableList[str]([name for name, ok in checks if not ok])
    for name, ok in checks:
        print(f"  {'通过' if ok else '失败'}（{name}）")
    if failures:
        print(f"[self-test] 失败 {len(failures)} 项：{'、'.join(failures)}")
        return 1
    print("[self-test] 全部通过")
    return 0


def main() -> int:
    """入口：执行本地预检。

    Returns:
        int: 退出码（0 全通过 / 1 有失败项）。
    """
    configure_stdio()
    if "--self-test" in sys.argv:
        return _self_test()
    root = Path(_positional_root()).resolve()
    backend = root / "backend"
    fast = "--fast" in sys.argv
    full = "--full" in sys.argv
    no_scope = "--no-scope" in sys.argv
    no_cov = "--no-cov" in sys.argv
    step_default, total_default = _DEFAULT_FULL_BUDGET if full else _DEFAULT_SCOPED_BUDGET
    global _GUARD
    _GUARD = _Budget(
        step_seconds=_numeric_flag("--step-seconds", step_default),
        total_seconds=_numeric_flag("--budget-seconds", total_default),
    )
    failures: ConcurrentStableList[str] = ConcurrentStableList()
    mode = "全量（显式 --full）" if full else ("快速（只静态）" if fast else "定向（快路径；全量请显式 --full）")
    guard_line = (
        f"[preflight] 预算护栏：单步 {_GUARD.step_seconds:.0f}s / 总体 {_GUARD.total_seconds:.0f}s"
        "（超时即中止，全量交 CI）"
    )
    print(f"[preflight] 档位：{mode}\n{guard_line}")

    _yaml_parse(root, failures)
    _pytest_flags_from_ci(root, backend, failures)
    _gitlab_ci_lint(root, failures)

    _run("后端静态：ruff check", ConcurrentStableList(["uv", "run", "ruff", "check", "."]), backend, failures)
    _run(
        "后端静态：ruff format --check",
        ConcurrentStableList(["uv", "run", "ruff", "format", "--check", "."]),
        backend,
        failures,
    )
    _run("后端静态：pyright", ConcurrentStableList(["uv", "run", "pyright"]), backend, failures)
    # 工具脚本静态（scripts/tools；08_01 遗留纳入 CI lint，本地同口径；从 backend/ 取 ruff 配置）
    _run(
        "工具静态：ruff check（scripts/tools）",
        ConcurrentStableList(["uv", "run", "ruff", "check", "../scripts/tools"]),
        backend,
        failures,
    )
    _run(
        "工具静态：ruff format --check（scripts/tools）",
        ConcurrentStableList(["uv", "run", "ruff", "format", "--check", "../scripts/tools"]),
        backend,
        failures,
    )

    if full:
        cov_args = (
            []
            if no_cov
            else [
                "--cov=bms_core",
                "--cov=bms_platform",
                "--cov=bms_txn",
                "--cov=bms_identity",
                "--cov=bms_tenant",
                "--cov=bms_file",
                "--cov=bms_notification",
                "--cov=bms_search",
                "--cov=bms_ai",
                "--cov=bms_report",
                "--cov-branch",
                "--cov-report=json:coverage.json",
                "--cov-fail-under=100",
            ]
        )
        _run(
            "后端测试：聚合全量（--full）",
            ConcurrentStableList(["uv", "run", "pytest", "-q", *cov_args]),
            backend,
            failures,
        )
        if not no_scope:
            for rel in _ROOTS:
                _run(
                    f"后端测试：工程级范围（{rel}）",
                    ConcurrentStableList(["uv", "run", "pytest", "-q"]),
                    backend / rel,
                    failures,
                )
    elif not fast:
        _run_scoped(root, backend, failures, no_cov=no_cov)

    _run(
        "基座：check-base",
        ConcurrentStableList([sys.executable, "scripts/tools/base-check/check-base.py", str(root)]),
        root,
        failures,
    )
    _run(
        "基座：check-system-fields",
        ConcurrentStableList([sys.executable, "scripts/tools/base-check/check-system-fields.py", str(root)]),
        root,
        failures,
    )
    _run(
        "基座：check-system-fields --self-test",
        ConcurrentStableList([sys.executable, "scripts/tools/base-check/check-system-fields.py", "--self-test"]),
        root,
        failures,
    )
    _run(
        "基座：check-env-example（环境变量模板键位）",
        ConcurrentStableList([sys.executable, "scripts/tools/base-check/check-env-example.py", str(root)]),
        root,
        failures,
    )
    _run(
        "基座：check-env-example --self-test",
        ConcurrentStableList([sys.executable, "scripts/tools/base-check/check-env-example.py", "--self-test"]),
        root,
        failures,
    )
    _run(
        "基座：check-backend-base",
        ConcurrentStableList([sys.executable, "scripts/tools/base-check/check-backend-base.py", str(root)]),
        root,
        failures,
    )
    _run(
        "基座：check-backend-base --self-test",
        ConcurrentStableList([sys.executable, "scripts/tools/base-check/check-backend-base.py", "--self-test"]),
        root,
        failures,
    )
    _run(
        "边界：check-service-boundaries",
        ConcurrentStableList([sys.executable, "scripts/tools/base-check/check-service-boundaries.py", str(root)]),
        root,
        failures,
    )
    _run(
        "边界：check-service-boundaries --self-test",
        ConcurrentStableList([sys.executable, "scripts/tools/base-check/check-service-boundaries.py", "--self-test"]),
        root,
        failures,
    )
    _run(
        "基座：check-bare-collections（裸无序集合护栏）",
        ConcurrentStableList([sys.executable, "scripts/tools/base-check/check-bare-collections.py", str(root)]),
        root,
        failures,
    )
    _run(
        "基座：check-bare-collections --self-test",
        ConcurrentStableList([sys.executable, "scripts/tools/base-check/check-bare-collections.py", "--self-test"]),
        root,
        failures,
    )
    _run(
        "文档：check-docs-scope（排期与工时落点护栏）",
        ConcurrentStableList([sys.executable, "scripts/tools/base-check/check-docs-scope.py", str(root)]),
        root,
        failures,
    )
    _run(
        "文档：check-docs-scope --self-test",
        ConcurrentStableList([sys.executable, "scripts/tools/base-check/check-docs-scope.py", "--self-test"]),
        root,
        failures,
    )
    _run(
        "界面：check-prototype-review（本次改动含界面源码须有原型对照；《原型审查规范》§4.9）",
        ConcurrentStableList(
            [
                sys.executable,
                "scripts/tools/base-check/check-prototype-review.py",
                str(root),
                "--changed",
                "origin/main",
            ]
        ),
        root,
        failures,
    )
    _run(
        "界面：check-prototype-review --self-test",
        ConcurrentStableList([sys.executable, "scripts/tools/base-check/check-prototype-review.py", "--self-test"]),
        root,
        failures,
    )
    _run(
        "边界：boundary_metrics（越界 / 跨库 / 例外计数）",
        ConcurrentStableList([sys.executable, "scripts/tools/governance/boundary_metrics.py", "--root", str(root)]),
        root,
        failures,
    )
    _run(
        "文档：check-status",
        ConcurrentStableList([sys.executable, "scripts/tools/check-docs/check-status.py", "--root", str(root)]),
        root,
        failures,
    )
    _run(
        "网关：gateway_config check（服务目录零漂移）",
        ConcurrentStableList([sys.executable, "backend/ops/gateway_config.py", "check", "--root", str(root)]),
        root,
        failures,
    )
    _run(
        "契约：contract_snapshot check（公开契约零漂移）",
        ConcurrentStableList(["uv", "run", "python", "-m", "ops.contract_snapshot", "check", "--root", str(root)]),
        backend,
        failures,
    )
    _run(
        "契约：check_contracts（实现路由 ⊆ 公开契约 paths + 不可见白名单）",
        ConcurrentStableList(["uv", "run", "python", "-m", "ops.check_contracts"]),
        backend,
        failures,
    )
    _run(
        "契约：event_contracts check（事件契约零漂移 + 兼容）",
        ConcurrentStableList(["uv", "run", "python", "-m", "ops.event_contracts", "check", "--root", str(root)]),
        backend,
        failures,
    )
    _frontend_api_types(root, failures)

    if _GUARD.exhausted:
        print("\n[preflight] 提示：预算护栏已中止剩余步骤 —— 全量与集成交 CI（推送后按需触发流水线）。")
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
