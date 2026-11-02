#!/usr/bin/env python3
"""提交前门禁（pre-commit）：跑**推送预检的全部检查项**，范围收敛到本次改动文件。

步骤表不在本脚本维护——直接读仓根 `engkit.toml` 的 `[[preflight.steps]]`（推送预检的同一份声明），
因此**预检加了什么，这里就跟着查什么，一项不漏**；`[[preflight.self_tests]]` 按 `deps` 命中才跑。

范围按「能增量就增量、不能增量按原样」：

- `scoped_tests` → 定向执行器（选测 + 覆盖率门禁 100% + 扩圈），只跑改动触及的用例；
- `ruff` / `pyright` → 只跑改动文件（按步骤作用域筛 `backend/` 与 `scripts/`）；
- 支持 `--files-from` 的护栏（集合声明 / 雪花 ID / 测试库隔离 / 产品字面量 / 服务边界）→ 追加改动清单，
  由 `[[devloop.steps]]` 自动识别（零白名单维护）；
- 其余步骤（基座完整性、契约快照、域布局、跨仓对账、前端类型等**零漂移 / 一致性判定**）→ 原样执行：
  这类判定的语义是「全仓口径一致」，无法只判改动文件，但都是秒级；
- `full_tests` / `project_tests`（仅 CI）→ 跳过并注明。

用法::

    python scripts/tools/preflight/提交前预检.py              # 由 .git/hooks/pre-commit 调用（判暂存区）
    python scripts/tools/preflight/提交前预检.py --dry-run     # 只打印步骤计划，不执行
    python scripts/tools/preflight/提交前预检.py --jobs 4      # 指定选测并行档位（缺省 auto）
    python scripts/tools/preflight/提交前预检.py --only-lint   # 只跑静态与护栏（不含选测 / 覆盖率）

**逃逸口**：`git commit --no-verify` 跳过本钩子，仅限紧急回滚；推送环仍会完整复判，不构成绕过。
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from engkit_boot import REPO_ROOT, config_path, ensure_engkit  # noqa: E402

ensure_engkit()

from engkit.config import Config, load_for  # noqa: E402

from bms_core.core.concurrent import (  # noqa: E402
    ConcurrentStableFrozenDict,
    ConcurrentStableFrozenList,
    ConcurrentStableFrozenSet,
    ConcurrentStableList,
)

GATED_PREFIXES = ("backend/", "scripts/", "deploy/")
"""需要门禁的代码 / 配置路径前缀。"""

GATED_SUFFIXES = (".py", ".toml", ".yml", ".yaml")
"""需要门禁的代码 / 配置后缀。"""

DOC_PREFIXES = ("bms文档/",)
"""需要门禁的文档路径前缀（文档也过门禁：check_base / docs_scope / docs_status 均按改动文件增量判）。"""

DOC_SUFFIXES = (".md",)
"""需要门禁的文档后缀。"""

CHANGED_LIST_PATH = Path(".cache") / "precommit" / "changed.txt"
"""暂存变更清单落点（仓内缓存目录，已忽略）。"""

CI_ONLY_TYPES = ConcurrentStableFrozenSet(("full_tests", "project_tests"))
"""仅 CI 执行的步骤类型。"""

RUNNABLE_STEPS: ConcurrentStableFrozenSet[str] = ConcurrentStableFrozenSet(
    (
        "check_workspace_hygiene.py",
        "check_base.py",
        "check_system_fields.py",
        "check_backend_base.py",
        "check_env_example.py",
        "boundary_metrics.py",
        "check_docs_scope.py",
        "check_status.py",
        "engkit eol",
        "check_ci_config.py",
        "check_test_db_isolation.py",
        "check_bare_collections.py",
        "check_snowflake_ids.py",
        "check_product_literals.py",
        "check_service_boundaries.py",
        "ruff",
        "pyright",
        "run_selected",
    )
)
"""提交前**允许执行**的步骤：命令能限定到改动文件（逐文件或 `--files-from`）。

新增预检步骤若不在本集合、也不在 `PUSH_ONLY_STEPS`，门禁**立即报错**（fail-closed）——
不允许出现「新加一步、提交前悄悄扫全仓」的情况。
"""

FULL_SCAN_STEPS: ConcurrentStableFrozenSet[str] = ConcurrentStableFrozenSet(
    (
        "ops.gateway_config",
        "ops.check_modules",
        "ops.contract_snapshot",
        "ops.check_contracts",
        "ops.event_contracts",
        "check_prototype_review.py",
        "check_frontend_types.py",
        "api-types",
    )
)
"""语义为「全仓口径一致 / 零漂移」的步骤：默认命令只能全仓判定，无法只判改动文件。

这类步骤**不会被跳过**：本次改动触及它时必须执行；若执行前校验发现命令无法限定到改动文件，
门禁**立即报错**（提示该步需改造为文件级判据），只有显式 `--allow-full-steps` 才放行全仓执行。
"""

STEP_SCOPES: ConcurrentStableFrozenDict[str, ConcurrentStableFrozenList[str]] = ConcurrentStableFrozenDict(
    {
        # —— 轻量全局项（秒级）：总跑 ——
        "check_workspace_hygiene.py": ConcurrentStableFrozenList(),
        "engkit eol": ConcurrentStableFrozenList(),
        "check_ci_config.py": ConcurrentStableFrozenList(),
        "check_test_db_isolation.py": ConcurrentStableFrozenList(),
        "check_bare_collections.py": ConcurrentStableFrozenList(),
        "check_snowflake_ids.py": ConcurrentStableFrozenList(),
        "check_product_literals.py": ConcurrentStableFrozenList(),
        "check_service_boundaries.py": ConcurrentStableFrozenList(),
        # —— 后端源码相关 ——
        "check_base.py": ConcurrentStableFrozenList(("backend/", "bms文档/")),
        "check_system_fields.py": ConcurrentStableFrozenList(("backend/",)),
        "check_env_example.py": ConcurrentStableFrozenList(("backend/", "deploy/")),
        "check_backend_base.py": ConcurrentStableFrozenList(("backend/",)),
        "boundary_metrics.py": ConcurrentStableFrozenList(("backend/", "deploy/")),
        "ops.gateway_config": ConcurrentStableFrozenList(("backend/", "deploy/")),
        "ops.check_modules": ConcurrentStableFrozenList(("backend/", "deploy/")),
        "ops.contract_snapshot": ConcurrentStableFrozenList(("backend/",)),
        "ops.check_contracts": ConcurrentStableFrozenList(("backend/",)),
        "ops.event_contracts": ConcurrentStableFrozenList(("backend/", "deploy/")),
        # —— 文档相关 ——
        "check_docs_scope.py": ConcurrentStableFrozenList(("bms文档/",)),
        "check_status.py": ConcurrentStableFrozenList(("bms文档/",)),
        # —— 前端相关（typecheck / build 分钟级，只在真改前端或契约时才跑）——
        "check_prototype_review.py": ConcurrentStableFrozenList(("frontend/",)),
        "check_frontend_types.py": ConcurrentStableFrozenList(("frontend/", "backend/")),
        "api-types": ConcurrentStableFrozenList(("frontend/", "backend/")),
        # —— 静态（步骤内部再按改动文件筛，无对应改动文件即跳过）——
        "ruff": ConcurrentStableFrozenList(("backend/", "scripts/")),
        "pyright": ConcurrentStableFrozenList(("backend/", "scripts/")),
        # —— 选测 + 覆盖率（覆盖率源只在 backend 的 libs / services，脚本改动不触发）——
        "run_selected": ConcurrentStableFrozenList(("backend/",)),
    }
)
"""步骤作用域：命令特征 → 触发路径前缀（空表示总跑）。

键取「脚本文件名 / `-m` 模块名 / 命令特征」，值是该步骤有意义的改动前缀；未登记的步骤按总跑处理
（宁可多跑一项，不漏一项）。判定用 `前缀命中即跑`，所以改 `scripts/` 时前端 typecheck 这类分钟级
步骤不会白跑。
"""


class StepScopeError(Exception):
    """预检步骤未登记提交前执行范围（fail-closed，拒绝执行）。"""


@dataclass(frozen=True)
class PlannedStep:
    """一条待执行的检查步骤。

    Attributes:
        label: 步骤标签。
        cmd: 渲染完成、可直接执行的命令。
        cwd: 工作目录（相对仓根；空串取仓根）。
    """

    label: str
    cmd: ConcurrentStableList[str]
    cwd: str


def _git(root: Path, *args: str) -> str:
    """执行 git 命令并取标准输出。

    Args:
        root: 仓库根。
        args: git 参数。

    Returns:
        str: 标准输出（失败为空串）。
    """
    completed = subprocess.run(
        # `core.quotepath=false`：中文路径原样输出，否则被转义成 `"\\346..."` 导致前缀判定失效
        ["git", "-c", "core.quotepath=false", *args],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    return completed.stdout if completed.returncode == 0 else ""


def staged_files(root: Path, changed_from: str) -> ConcurrentStableList[str]:
    """取本次要提交的变更文件（缺省只取暂存区）。

    Args:
        root: 仓库根。
        changed_from: git 基准（非空时改为「基准以来的改动」）。

    Returns:
        ConcurrentStableList[str]: 相对仓库根的路径（去重保序）。
    """
    args = ("diff", "--name-only", "--diff-filter=ACMR") + ((changed_from,) if changed_from else ("--cached",))
    files: ConcurrentStableList[str] = ConcurrentStableList()
    for line in _git(root, *args).splitlines():
        rel = line.strip().replace("\\", "/")
        if rel and rel not in set(files):
            files.add(rel)
    return files


def gated_files(files: ConcurrentStableList[str]) -> ConcurrentStableList[str]:
    """筛出需要门禁的改动文件。

    Args:
        files: 本次变更文件。

    Returns:
        ConcurrentStableList[str]: 需门禁的子集（空表示可直接放行）。
    """
    picked: ConcurrentStableList[str] = ConcurrentStableList()
    for rel in files:
        if (rel.startswith(GATED_PREFIXES) and rel.endswith(GATED_SUFFIXES)) or (
            rel.startswith(DOC_PREFIXES) and rel.endswith(DOC_SUFFIXES)
        ):
            picked.add(rel)
    return picked


def changed_py(files: ConcurrentStableList[str]) -> ConcurrentStableList[str]:
    """取改动中的 Python 文件（静态检查的作用域）。

    Args:
        files: 本次变更文件。

    Returns:
        ConcurrentStableList[str]: `.py` 改动文件。
    """
    return ConcurrentStableList(rel for rel in files if rel.endswith(".py"))


def write_changed_list(root: Path, files: ConcurrentStableList[str]) -> Path:
    """把改动文件写成各步骤认的清单（一行一个相对路径）。

    Args:
        root: 仓库根。
        files: 改动文件。

    Returns:
        Path: 清单文件绝对路径。
    """
    target = root / CHANGED_LIST_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("\n".join(files) + "\n", encoding="utf-8")
    return target


def incremental_scripts(cfg: Config) -> ConcurrentStableFrozenSet[str]:
    """从开发环步骤识别「支持按文件清单裁剪」的脚本（零白名单维护）。

    Args:
        cfg: 仓配置。

    Returns:
        ConcurrentStableFrozenSet[str]: 脚本文件名集合（如 `check_bare_collections.py`）。
    """
    names: ConcurrentStableList[str] = ConcurrentStableList()
    for step in cfg.devloop_steps:
        if "--files-from" not in step.cmd:
            continue
        name = _script_name(ConcurrentStableFrozenList(step.cmd))
        if name:
            names.add(name)
    return ConcurrentStableFrozenSet(names)


def _step_key(cmd: ConcurrentStableFrozenList[str], label: str) -> str:
    """取步骤的作用域键（脚本名 / `-m` 模块名 / 命令特征 / 标签）。

    Args:
        cmd: 命令模板。
        label: 步骤标签。

    Returns:
        str: 作用域键。
    """
    name = _script_name(cmd)
    if name:
        return name
    if "-m" in cmd:
        index = cmd.index("-m")
        if index + 1 < len(cmd):
            return str(cmd[index + 1])
    if "eol" in cmd:
        return "engkit eol"
    joined = " ".join(cmd)
    if "generate.mjs" in joined:
        return "api-types"
    if "ruff" in cmd:
        return "ruff"
    if "pyright" in cmd:
        return "pyright"
    if "run_selected.py" in joined:
        return "run_selected"
    return label


def _step_applies(key: str, files: ConcurrentStableList[str], *, force_all: bool) -> bool:
    """判断步骤在本次改动下是否需要执行。

    Args:
        key: 作用域键。
        files: 改动文件。
        force_all: 强制全跑（`--all-steps`）。

    Returns:
        bool: 需要执行。
    """
    if force_all:
        return True
    scopes = STEP_SCOPES.get(key)
    if scopes is None:
        return True
    if not scopes:
        return True
    return any(rel.startswith(tuple(scopes)) for rel in files)


def _script_name(cmd: ConcurrentStableFrozenList[str]) -> str:
    """取命令里第一个 `.py` 脚本的文件名。

    Args:
        cmd: 命令模板。

    Returns:
        str: 脚本文件名（无则空串）。
    """
    for part in cmd:
        if part.endswith(".py"):
            return Path(part).name
    return ""


def _render(
    cmd: ConcurrentStableFrozenList[str], *, root: Path, python: str, changed: Path
) -> ConcurrentStableList[str]:
    """渲染命令占位符。

    Args:
        cmd: 命令模板。
        root: 仓库根。
        python: 解释器路径。
        changed: 变更清单文件。

    Returns:
        ConcurrentStableList[str]: 渲染后的命令。
    """
    rendered: ConcurrentStableList[str] = ConcurrentStableList()
    for part in cmd:
        rendered.add(
            part.replace("{python}", python)
            .replace("{root}", str(root))
            .replace("{config}", config_path())
            .replace("{changed}", str(changed))
        )
    return rendered


def _rel_to(root: Path, cwd: str, files: ConcurrentStableList[str], *, prefix: str) -> ConcurrentStableList[str]:
    """把改动文件转成相对某工作目录的路径（只取指定前缀下的）。

    Args:
        root: 仓库根。
        cwd: 工作目录（相对仓根）。
        files: 改动文件。
        prefix: 路径前缀（`backend/` 或 `scripts/`）。

    Returns:
        ConcurrentStableList[str]: 相对路径列表。
    """
    base = root / cwd
    paths: ConcurrentStableList[str] = ConcurrentStableList()
    for rel in files:
        if rel.startswith(prefix):
            paths.add(os.path.relpath(root / rel, base).replace("\\", "/"))
    return paths


def _adapt_lint(
    cmd: ConcurrentStableFrozenList[str],
    *,
    root: Path,
    python: str,
    cwd: str,
    files: ConcurrentStableList[str],
) -> ConcurrentStableList[str] | None:
    """把全仓 ruff / pyright 步骤改成「只查改动文件」。

    Args:
        cmd: 原始命令。
        root: 仓库根。
        python: 解释器路径。
        cwd: 工作目录。
        files: 改动文件。

    Returns:
        ConcurrentStableList[str] | None: 渲染后的命令；无改动文件时 None（跳过）。
    """
    tool_scope = "scripts" if any("scripts/tools" in part for part in cmd) else "backend"
    targets = _rel_to(root, cwd, files, prefix=f"{tool_scope}/")
    if not targets:
        return None
    if "pyright" in cmd:
        adapted: ConcurrentStableList[str] = ConcurrentStableList(
            (python, "-m", "pyright", "--project", "backend", "--pythonpath", python)
        )
        adapted.extend(targets)
        return adapted
    # 只保留子命令（`check` / `format`）与选项，丢弃原目标路径（换成改动文件）
    index = cmd.index("ruff")
    verb: ConcurrentStableList[str] = ConcurrentStableList((cmd[index + 1],))
    verb.extend(part for part in cmd[index + 2 :] if part.startswith("-"))
    adapted: ConcurrentStableList[str] = ConcurrentStableList((python, "-m", "ruff"))
    adapted.extend(verb)
    adapted.extend(targets)
    return adapted


def plan_steps(
    cfg: Config,
    *,
    root: Path,
    python: str,
    changed: Path,
    files: ConcurrentStableList[str],
    jobs: str,
    only_lint: bool,
    all_steps: bool,
    allow_full: bool,
) -> tuple[
    ConcurrentStableList[PlannedStep],
    ConcurrentStableList[str],
    ConcurrentStableList[str],
]:
    """把预检步骤表换算成本次可执行的计划。

    Args:
        cfg: 仓配置。
        root: 仓库根。
        python: 解释器路径。
        changed: 变更清单文件。
        files: 改动文件。
        jobs: 选测并行档位。
        only_lint: 只跑静态与护栏（不含选测 / 覆盖率）。
        all_steps: 强制跑全部步骤（不按改动面裁剪）。
        allow_full: 放行「只能全仓判定」的步骤（默认遇到即报错）。

    Returns:
        tuple[ConcurrentStableList[PlannedStep], ConcurrentStableList[str], ConcurrentStableList[str]]:
        （计划, 跳过说明, 仅推送环项）。

    Raises:
        StepScopeError: 步骤未登记提交前执行范围。
    """
    incremental = incremental_scripts(cfg)
    planned: ConcurrentStableList[PlannedStep] = ConcurrentStableList()
    skipped: ConcurrentStableList[str] = ConcurrentStableList(
        f"{step.label}（仅 CI）" for step in cfg.preflight.steps if step.type in CI_ONLY_TYPES
    )
    deferred: ConcurrentStableList[str] = ConcurrentStableList()
    slow: ConcurrentStableList[PlannedStep] = ConcurrentStableList()

    for step in cfg.preflight.steps:
        if step.type in CI_ONLY_TYPES:
            continue
        if step.type == "scoped_tests":
            key = "run_selected"
        else:
            key = _step_key(ConcurrentStableFrozenList(step.cmd), step.label) if step.cmd else step.label
        if not _step_applies(key, files, force_all=all_steps):
            skipped.add(f"{step.label}（本次改动不触及）")
            continue
        if key in FULL_SCAN_STEPS and not (all_steps or allow_full):
            deferred.add(f"{step.label}（命令只能全仓判定，需改造为文件级判据）")
            continue
        if key not in RUNNABLE_STEPS and not all_steps:
            raise StepScopeError(
                f"步骤「{step.label}」（键 {key}）未登记提交前执行方式："
                "请在 RUNNABLE_STEPS / FULL_SCAN_STEPS 中明确登记"
            )
        cwd = step.cwd or cfg.preflight.cwd
        if step.type == "scoped_tests":
            if only_lint:
                skipped.add(f"{step.label}（--only-lint）")
                continue
            slow.add(
                PlannedStep(
                    label=step.label,
                    cmd=ConcurrentStableList(
                        (
                            python,
                            str(_SCRIPT_DIR / "run_selected.py"),
                            str(root),
                            "--changed-file-list",
                            str(changed),
                            "--jobs",
                            jobs,
                        )
                    ),
                    cwd="",
                )
            )
            continue

        cmd = _render(
            ConcurrentStableFrozenList(step.cmd),
            root=root,
            python=python,
            changed=changed,
        )
        if any("ruff" in part or "pyright" in part for part in step.cmd):
            adapted = _adapt_lint(
                ConcurrentStableFrozenList(step.cmd),
                root=root,
                python=python,
                cwd=cwd,
                files=files,
            )
            if adapted is None:
                skipped.add(f"{step.label}（无对应改动文件）")
                continue
            planned.add(PlannedStep(label=step.label, cmd=adapted, cwd=cwd))
            continue
        if _script_name(ConcurrentStableFrozenList(step.cmd)) in incremental and "--files-from" not in cmd:
            cmd.add("--files-from")
            cmd.add(str(changed))
        planned.add(PlannedStep(label=step.label, cmd=cmd, cwd=cwd))

    planned.extend(slow)

    for self_test in cfg.preflight.self_tests:
        if any(rel.startswith(tuple(self_test.deps)) for rel in files) and self_test.deps:
            planned.add(
                PlannedStep(
                    label=f"自测：{self_test.label}",
                    cmd=_render(
                        ConcurrentStableFrozenList(self_test.cmd),
                        root=root,
                        python=python,
                        changed=changed,
                    ),
                    cwd="",
                )
            )
    return planned, skipped, deferred


def run_step(step: PlannedStep, *, root: Path) -> tuple[bool, float]:
    """执行一条步骤并打印结论与耗时。

    Args:
        step: 待执行步骤。
        root: 仓库根。

    Returns:
        tuple[bool, float]: （是否通过, 耗时秒）。
    """
    print(f"[precommit] ▶ {step.label}", flush=True)
    started = time.perf_counter()
    completed = subprocess.run(
        list(step.cmd),
        cwd=(root / step.cwd) if step.cwd else root,
        check=False,
    )
    elapsed = time.perf_counter() - started
    if completed.returncode != 0:
        print(
            f"[precommit] ✗ {step.label}（{elapsed:.1f}s，退出码 {completed.returncode}）",
            file=sys.stderr,
        )
        return False, elapsed
    print(f"[precommit] ✓ {step.label}（{elapsed:.1f}s）")
    return True, elapsed


def main(argv: ConcurrentStableList[str] | None = None) -> int:
    """入口。

    Args:
        argv: 命令行参数（None 取 `sys.argv`）。

    Returns:
        int: 退出码（0 放行 / 1 有失败项）。
    """
    parser = argparse.ArgumentParser(
        prog="提交前预检",
        description="提交前门禁（跑推送预检的全部检查项，范围到改动文件）",
    )
    parser.add_argument("--root", default=str(REPO_ROOT), help="仓库根（缺省为脚本所在仓）")
    parser.add_argument("--jobs", default="auto", help="选测并行档位：auto / 正整数 / off")
    parser.add_argument("--changed-from", default="", help="改为对比 git 基准（缺省只判暂存区）")
    parser.add_argument("--only-lint", action="store_true", help="只跑静态与护栏（不含选测 / 覆盖率）")
    parser.add_argument("--dry-run", action="store_true", help="只打印步骤计划，不执行")
    parser.add_argument("--all-steps", action="store_true", help="强制跑全部预检步骤（不按改动面裁剪）")
    parser.add_argument(
        "--allow-full-steps",
        action="store_true",
        help="放行「只能全仓判定」的步骤（默认遇到即报错，要求改造为文件级判据）",
    )
    args = parser.parse_args(None if argv is None else list(argv))

    root = Path(args.root).resolve()
    all_files = staged_files(root, str(args.changed_from))
    files = gated_files(all_files)
    if not files:
        print(f"[precommit] 本次变更 {len(all_files)} 个文件，无需门禁（无后端源码 / 脚本 / 部署配置 / 文档），放行。")
        return 0

    changed = write_changed_list(root, files)
    cfg = load_for(root, config_path())
    try:
        planned, skipped, deferred = plan_steps(
            cfg,
            root=root,
            python=sys.executable,
            changed=changed,
            files=files,
            jobs=str(args.jobs),
            only_lint=bool(args.only_lint),
            all_steps=bool(args.all_steps),
            allow_full=bool(args.allow_full_steps),
        )
    except StepScopeError as exc:
        print(f"[precommit] 拒绝执行：{exc}", file=sys.stderr)
        return 1

    if deferred:
        print(
            f"[precommit] 拒绝提交：{len(deferred)} 个步骤只能全仓判定，无法限定到改动文件：",
            file=sys.stderr,
        )
        for note in deferred:
            print(f"[precommit]   - {note}", file=sys.stderr)
        print(
            "[precommit] 这几项必须改造为文件级判据（支持 --files-from）后才能进提交前门禁；"
            "确认本次可由推送环兜底时用 --allow-full-steps 显式放行。",
            file=sys.stderr,
        )
        return 1
    print(f"[precommit] 改动 {len(files)} 个文件（需门禁），提交前执行 {len(planned)} 项：")
    for item in files:
        print(f"[precommit]   · {item}")
    for note in skipped:
        print(f"[precommit]   跳过 {note}")
    if args.dry_run:
        for step in planned:
            print(f"[precommit]   ▷ {step.label}｜{' '.join(step.cmd)}")
        print("[precommit] --dry-run：跳过执行。")
        return 0

    failed: ConcurrentStableList[str] = ConcurrentStableList()
    started = time.perf_counter()
    for step in planned:
        passed, _ = run_step(step, root=root)
        if not passed:
            failed.add(step.label)
    total = time.perf_counter() - started
    if failed:
        print(f"[precommit] 未通过 {len(failed)} 项：", file=sys.stderr)
        for label in failed:
            print(f"[precommit]   - {label}", file=sys.stderr)
        print(
            "[precommit] 修完重新 `git add` 再提交（紧急回滚可用 `git commit --no-verify`）。",
            file=sys.stderr,
        )
        return 1
    print(f"[precommit] 全部通过（{len(planned)} 项，共 {total:.1f}s），允许提交。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
