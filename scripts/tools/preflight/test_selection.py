#!/usr/bin/env python3
"""变更影响分析选测器（test selection）：把「改了哪些文件」推导成「该跑哪些测试 / 哪些前端包」。

口径（阶段二需求 13-1 / 任务 13_01，见《测试执行粒度与影响分析评估》）：

1. **单一来源**：本地预检（`check-preflight.py`）与 CI（`.gitlab-ci.yml` 四个 job）共用本模块，
   禁止两侧各自维护推导规则（口径分叉是「一处改动即全量重跑」复发的根源）。
2. **双重收敛（后端）**：先按**目录同构**取候选（源包目录 ↔ 同构测试目录），再用 **AST 导入图**收敛到
   真实引用者（测试文件对变更模块的直接 / 传递引用，含跨目录引用与反向依赖闭包）。
3. **基础模块退化**：受影响测试文件数超过绝对阈值或工程占比的模块不做「假精细」——退化为该工程全量，
   并**显式**给出原因与命中工程（不静默）。
4. **前端同构**：按 `workspace:*` 依赖做反向闭包推导受影响包（改 `@bms/core` ⇒ 依赖它的包全部受影响），
   根级配置 / 共享脚本变更退化为全部包。
5. **覆盖率目标不降级**：仍只对变更的**包内源文件**开 100% 覆盖率门禁（`ops` / `scripts` 不入）；
   选测不足由调用方扩圈重跑（见 `run-selected.py`），本模块只回答「该跑谁」。

用法::

    python3 scripts/tools/preflight/test_selection.py --changed-from origin/main --format json
    python3 scripts/tools/preflight/test_selection.py --changed-file backend/libs/... --format pytest-args
    python3 scripts/tools/preflight/test_selection.py --changed-from origin/main --format cov-args
    python3 scripts/tools/preflight/test_selection.py --scope frontend --changed-from origin/main --format packages
    python3 scripts/tools/preflight/test_selection.py --force-full --format json

退出码：``0`` 正常（含「无受影响用例」）；``1`` 推导异常（工程发现为空等）。

用例：Kiwi **2316**（`backend/libs/bms_core/tests/boundary/test_test_selection_guard.py`）。
"""

import argparse
import ast
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
"""bms 仓库根（本脚本位于 `scripts/tools/preflight/`）。"""

_SRC_ROOT = _REPO_ROOT / "backend" / "libs" / "bms_core" / "src"
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))

from bms_core.core.concurrent import (  # noqa: E402
    ConcurrentStableDict,
    ConcurrentStableList,
    ConcurrentStableSet,
)

_BASE_TEST_THRESHOLD = 100
"""基础模块绝对阈值：单工程受影响测试文件数超过即退化为工程级全量。"""

_BASE_TEST_RATIO = 0.6
"""基础模块占比阈值：受影响测试文件占工程全量之比超过即退化。"""

_GLOBAL_EXACT: tuple[str, ...] = (
    "backend/pyproject.toml",
    "backend/uv.lock",
    ".gitlab-ci.yml",
)
"""全局变更（精确匹配）：影响全部后端工程 ⇒ 直接退化全量。"""

_GLOBAL_PREFIXES: tuple[str, ...] = (
    "backend/alembic/",
    "deploy/",
)
"""全局变更（前缀匹配）：迁移脚本 / 部署与 CI 配置影响全部后端工程。"""

_GLOBAL_CONFIG_PREFIX = "backend/config"
"""全局变更（`backend/config*.toml` 形态）：数据库 / 缓存 / 安全等公共配置影响全部工程。"""

_OPS_PREFIX = "backend/ops/"
"""`ops` 脚本变更：用例落在基座 `tests/ops`（与预检原口径一致，不入覆盖率门禁）。"""

_PREFLIGHT_PREFIX = "scripts/tools/preflight/"
"""预检 / 选测器脚本变更：其护栏用例落在基座 `tests/boundary`。"""

_PREFLIGHT_TESTS: tuple[str, ...] = (
    "libs/bms_core/tests/boundary/test_test_selection_guard.py",
    "libs/bms_core/tests/boundary/test_preflight_scoping_guard.py",
    "libs/bms_core/tests/boundary/test_run_once_guard.py",
)
"""预检脚本目录变更时必须一并执行的护栏用例（相对 `backend`；单一来源）。"""

_FRONTEND_GROUPS: tuple[str, ...] = ("packages", "apps", "modules")
"""前端 pnpm 工程所在分组目录（`frontend/<分组>/<工程>`）。"""

_FRONTEND_GLOBAL_EXACT: tuple[str, ...] = (
    "package.json",
    "pnpm-lock.yaml",
    "pnpm-workspace.yaml",
    "tsconfig.base.json",
    ".npmrc",
)
"""前端根级配置：变更影响全部包 ⇒ 退化全量。"""

_FRONTEND_GLOBAL_PREFIXES: tuple[str, ...] = ("scripts/",)
"""前端共享脚本（desktop / modules 的 budget / guard 脚本位于仓根 `scripts/`）⇒ 全部包。"""


@dataclass(frozen=True)
class Project:
    """一个后端工程（库或服务）：源码根、测试根与包名。

    Attributes:
        name: 工程名（如 `bms_core` / `bms_platform`）。
        src: 源码根（相对仓库根，posix 形态，如 `backend/libs/bms_core/src`）。
        tests: 测试根（相对 `backend`，如 `libs/bms_core/tests`）。
        packages: 源码根下的顶层包名（通常 1 个）。
    """

    name: str
    src: str
    tests: str
    packages: tuple[str, ...]


@dataclass(frozen=True)
class ProjectMetrics:
    """逐工程选测度量。

    Attributes:
        name: 工程名。
        picked: 选中测试文件数。
        total: 工程测试文件总数。
        degraded: 是否退化为该工程全量。
    """

    name: str
    picked: int
    total: int
    degraded: bool


@dataclass(frozen=True)
class Selection:
    """后端选测结果。

    Attributes:
        test_paths: 选中的测试文件（相对 `backend`，posix 形态）。
        cov_modules: 覆盖率目标模块（只含变更的包内源文件）。
        degraded: 是否发生工程级全量退化。
        reason: 退化 / 说明主因（空串表示未退化）。
        picked: 选中测试文件数。
        total: 全部工程测试文件总数。
        projects: 逐工程度量。
        notes: 逐条说明（退化工程、ops / 预检用例并入等），供输出与复盘。
    """

    test_paths: tuple[str, ...] = ()
    cov_modules: tuple[str, ...] = ()
    degraded: bool = False
    reason: str = ""
    picked: int = 0
    total: int = 0
    projects: tuple[ProjectMetrics, ...] = ()
    notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class FrontendPackage:
    """一个前端 pnpm 工程。

    Attributes:
        name: 包名（`package.json` 的 `name`，如 `@bms/core`）。
        path: 工程根（相对仓库根，posix 形态）。
        workspace_deps: 依赖的工作区包名（`workspace:*` 协议）。
    """

    name: str
    path: str
    workspace_deps: tuple[str, ...]


@dataclass(frozen=True)
class FrontendSelection:
    """前端选测结果。

    Attributes:
        packages: 受影响包名（按 workspace 声明序）。
        degraded: 是否退化为全部包。
        reason: 退化主因（空串表示未退化）。
        notes: 逐条说明。
    """

    packages: tuple[str, ...] = ()
    degraded: bool = False
    reason: str = ""
    notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class Graph:
    """后端导入图（供选测与扩圈共用，避免重复扫描）。

    Attributes:
        projects: 工程清单。
        test_files: 工程名 → 测试文件（相对 `backend`，排序）。
        test_deps: 测试文件 → 依赖闭包（直接导入 + 传递依赖）。
    """

    projects: tuple[Project, ...]
    test_files: ConcurrentStableDict[str, tuple[str, ...]]
    test_deps: ConcurrentStableDict[str, ConcurrentStableSet[str]]


def _norm(rel: str) -> str:
    """统一路径形态（反斜杠转正斜杠、去首尾空白）。

    Args:
        rel: 路径文本。

    Returns:
        str: posix 形态路径。
    """
    return rel.strip().replace("\\", "/")


def _is_test_file(path: Path) -> bool:
    """是否为 pytest 测试文件（`test_*.py`；排除 `conftest.py` / `support_*.py` 等支持模块）。

    Args:
        path: 文件路径。

    Returns:
        bool: 是否测试文件。
    """
    return path.suffix == ".py" and path.name.startswith("test_")


def _iter_py(root: Path) -> tuple[Path, ...]:
    """列出目录下全部 `.py`（跳过 `__pycache__` / 虚拟环境 / node_modules）。

    Args:
        root: 起始目录。

    Returns:
        tuple[Path, ...]: 文件路径（按路径排序，稳定）。
    """
    found: ConcurrentStableList[Path] = ConcurrentStableList()
    if not root.is_dir():
        return ()
    for path in sorted(root.rglob("*.py")):
        parts = set(path.parts)
        if "__pycache__" in parts or ".venv" in parts or "node_modules" in parts:
            continue
        found.add(path)
    return tuple(found)


def discover_projects(backend: Path) -> tuple[Project, ...]:
    """发现后端工程：`backend/libs/*` 与 `backend/services/*`（有 `src` 与 `tests` 才算）。

    不维护工程白名单——目录到位即被发现（13_03「新增工程必登记」护栏的前提）。

    Args:
        backend: `backend` 目录。

    Returns:
        tuple[Project, ...]: 工程清单（库在前、服务按名排序）。
    """
    projects: ConcurrentStableList[Project] = ConcurrentStableList()
    for group in ("libs", "services"):
        group_dir = backend / group
        if not group_dir.is_dir():
            continue
        for item in sorted(group_dir.iterdir()):
            if not (item.is_dir() and (item / "src").is_dir() and (item / "tests").is_dir()):
                continue
            packages: ConcurrentStableList[str] = ConcurrentStableList()
            for child in sorted((item / "src").iterdir()):
                if child.is_dir() and (child / "__init__.py").is_file():
                    packages.add(child.name)
            if not packages:
                continue
            projects.add(
                Project(
                    name=packages[0],
                    src=(item / "src").relative_to(backend.parent).as_posix(),
                    tests=(item / "tests").relative_to(backend).as_posix(),
                    packages=tuple(packages),
                )
            )
    return tuple(projects)


def _module_of_source(rel: str, project: Project) -> str:
    """源文件（相对仓库根）→ 模块名；非包内文件返回空串。

    Args:
        rel: 变更路径（相对仓库根，posix 形态）。
        project: 所属工程。

    Returns:
        str: 模块名（如 `bms_core.core.exceptions`）；不在包内则空串。
    """
    prefix = f"{project.src}/"
    if not rel.startswith(prefix) or not rel.endswith(".py"):
        return ""
    tail = rel[len(prefix) : -3].replace("/", ".")
    if tail.endswith(".__init__"):
        tail = tail[: -len(".__init__")]
    for package in project.packages:
        if tail == package or tail.startswith(f"{package}."):
            return tail
    return ""


def _resolve_relative(module: str, node: ast.ImportFrom) -> str:
    """把相对导入（`from .x import y`）解析为绝对模块名。

    Args:
        module: 当前模块名。
        node: `ImportFrom` 节点。

    Returns:
        str: 绝对模块名前缀（无法解析时返回空串）。
    """
    if node.level <= 0:
        return node.module or ""
    parts = module.split(".")
    keep = len(parts) - node.level
    if keep <= 0:
        return node.module or ""
    base = parts[:keep]
    if node.module:
        base = [*base, *node.module.split(".")]
    return ".".join(base)


def parse_imports(path: Path, module: str) -> ConcurrentStableSet[str]:
    """解析单文件的绝对导入模块名集合（含 `from A import b` 的 `A.b` 形态）。

    Args:
        path: Python 文件路径。
        module: 该文件对应的模块名（相对导入解析需要；测试文件传空串）。

    Returns:
        ConcurrentStableSet[str]: 导入的模块名集合（可能含不存在的名字，闭包计算时自然忽略）。
    """
    found: ConcurrentStableSet[str] = ConcurrentStableSet()
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except OSError:
        return found
    except SyntaxError:
        return found
    except UnicodeDecodeError:
        return found
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                found.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            base = _resolve_relative(module, node)
            if not base:
                continue
            found.add(base)
            for alias in node.names:
                if alias.name != "*":
                    found.add(f"{base}.{alias.name}")
    return found


def _test_relative(backend: Path, path: Path) -> str:
    """测试文件 → 相对 `backend` 的 posix 路径。

    Args:
        backend: `backend` 目录。
        path: 测试文件路径。

    Returns:
        str: 相对路径（posix 形态）。
    """
    return path.relative_to(backend).as_posix()


def _transitive_deps(
    modules: ConcurrentStableDict[str, ConcurrentStableSet[str]],
) -> ConcurrentStableDict[str, ConcurrentStableSet[str]]:
    """把「模块 → 直接导入」补成「模块 → 传递依赖闭包」（记忆化 DFS，环上截断）。

    Args:
        modules: 模块 → 直接导入集合。

    Returns:
        ConcurrentStableDict[str, ConcurrentStableSet[str]]: 模块 → 传递依赖闭包（可能含环内自身，无害）。
    """
    resolved: ConcurrentStableDict[str, ConcurrentStableSet[str]] = ConcurrentStableDict()

    def walk(module: str, stack: ConcurrentStableSet[str]) -> ConcurrentStableSet[str]:
        cached = resolved.get(module)
        if cached is not None:
            return cached
        if module in stack:
            return ConcurrentStableSet()
        stack.add(module)
        closure: ConcurrentStableSet[str] = ConcurrentStableSet()
        for dep in modules.get(module) or ConcurrentStableSet():
            if dep in modules:
                closure.add(dep)
                closure.update(walk(dep, stack))
        stack.discard(module)
        resolved.set(module, closure)
        return closure

    for module in modules:
        walk(module, ConcurrentStableSet())
    return resolved


def build_graph(backend: Path) -> Graph:
    """构建后端导入图（源模块依赖 + 测试依赖闭包）。

    Args:
        backend: `backend` 目录。

    Returns:
        Graph: 导入图。

    Raises:
        RuntimeError: 未发现任何后端工程。
    """
    projects = discover_projects(backend)
    if not projects:
        raise RuntimeError(f"未发现任何后端工程（{backend}）")

    test_files: ConcurrentStableDict[str, tuple[str, ...]] = ConcurrentStableDict()
    for project in projects:
        files: ConcurrentStableList[str] = ConcurrentStableList()
        for path in _iter_py(backend / project.tests):
            if not _is_test_file(path):
                continue
            files.add(_test_relative(backend, path))
        test_files.set(project.name, tuple(files))

    modules: ConcurrentStableDict[str, ConcurrentStableSet[str]] = ConcurrentStableDict()
    for project in projects:
        for path in _iter_py(backend.parent / project.src):
            module = _module_of_source(path.relative_to(backend.parent).as_posix(), project)
            if module:
                modules.set(module, parse_imports(path, module))
    closures = _transitive_deps(modules)

    test_deps: ConcurrentStableDict[str, ConcurrentStableSet[str]] = ConcurrentStableDict()
    for project in projects:
        for rel in test_files.get(project.name) or ():
            closure: ConcurrentStableSet[str] = ConcurrentStableSet()
            for dep in parse_imports(backend / rel, ""):
                if dep in modules:
                    closure.add(dep)
                    closure.update(closures.get(dep) or ConcurrentStableSet())
            test_deps.set(rel, closure)

    return Graph(projects=projects, test_files=test_files, test_deps=test_deps)


def _isomorphic_candidates(backend: Path, rel: str, project: Project) -> tuple[str, ...]:
    """目录同构候选：源包目录 ↔ 同构测试目录下的全部测试文件。

    Args:
        backend: `backend` 目录。
        rel: 变更源文件（相对仓库根）。
        project: 所属工程。

    Returns:
        tuple[str, ...]: 候选测试文件（相对 `backend`；无同构目录时为空）。
    """
    prefix = f"{project.src}/"
    if not rel.startswith(prefix) or not rel.endswith(".py"):
        return ()
    parts = rel[len(prefix) : -3].split("/")
    sub = parts[1:-1]
    test_dir = backend / project.tests
    if sub:
        test_dir = test_dir.joinpath(*sub)
    if not test_dir.is_dir():
        return ()
    pattern = "**/*.py" if sub else "*.py"
    found: ConcurrentStableList[str] = ConcurrentStableList()
    for path in sorted(test_dir.glob(pattern)):
        if not _is_test_file(path) or "__pycache__" in path.parts:
            continue
        found.add(_test_relative(backend, path))
    return tuple(found)


def _classify_change(rel: str) -> str:
    """判定变更类别：`global` / `ops` / `preflight` / `other`。

    Args:
        rel: 变更路径（相对仓库根）。

    Returns:
        str: 类别。
    """
    if rel in _GLOBAL_EXACT or rel.startswith(_GLOBAL_PREFIXES):
        return "global"
    if rel.startswith(_GLOBAL_CONFIG_PREFIX) and rel.endswith(".toml"):
        return "global"
    if rel.startswith(_OPS_PREFIX):
        return "ops"
    if rel.startswith(_PREFLIGHT_PREFIX):
        return "preflight"
    return "other"


def all_test_paths(backend: Path) -> tuple[str, ...]:
    """全部后端测试文件（相对 `backend`，按工程顺序）。

    Args:
        backend: `backend` 目录。

    Returns:
        tuple[str, ...]: 测试文件清单。
    """
    graph = build_graph(backend)
    paths: ConcurrentStableList[str] = ConcurrentStableList()
    for project in graph.projects:
        paths.update(graph.test_files.get(project.name) or ())
    return tuple(paths)


def tests_for_modules(backend: Path, modules: tuple[str, ...]) -> tuple[str, ...]:
    """扩圈用：返回直接 / 传递引用给定模块的测试文件。

    Args:
        backend: `backend` 目录。
        modules: 目标模块名。

    Returns:
        tuple[str, ...]: 引用这些模块的测试文件（相对 `backend`，按工程顺序）。
    """
    graph = build_graph(backend)
    wanted: ConcurrentStableSet[str] = ConcurrentStableSet()
    wanted.update(modules)
    matched: ConcurrentStableSet[str] = ConcurrentStableSet()
    for rel, deps in graph.test_deps.items():
        for module in wanted:
            if module in deps:
                matched.add(rel)
                break
    ordered: ConcurrentStableList[str] = ConcurrentStableList()
    for project in graph.projects:
        for rel in graph.test_files.get(project.name) or ():
            if rel in matched:
                ordered.add(rel)
    return tuple(ordered)


def build_selection(
    backend: Path,
    changed: tuple[str, ...] | ConcurrentStableList[str],
    *,
    base_threshold: int = _BASE_TEST_THRESHOLD,
    base_ratio: float = _BASE_TEST_RATIO,
    force_full: bool = False,
) -> Selection:
    """按变更路径推导后端选测结果（目录同构 + AST 导入图双重收敛 + 基础模块退化）。

    Args:
        backend: `backend` 目录。
        changed: 变更路径（相对仓库根，posix 形态）。
        base_threshold: 基础模块绝对阈值（单工程受影响测试文件数）。
        base_ratio: 基础模块占比阈值（受影响测试文件 / 工程全量）。
        force_full: 强制退化全量（CI 变更基准不可解析时）。

    Returns:
        Selection: 选测结果。

    Raises:
        RuntimeError: 未发现任何后端工程。
    """
    graph = build_graph(backend)

    changed_set: ConcurrentStableSet[str] = ConcurrentStableSet()
    for item in changed:
        rel = _norm(item)
        if rel:
            changed_set.add(rel)

    global_change = force_full
    ops_changed = False
    preflight_changed = False
    changed_modules: ConcurrentStableDict[str, ConcurrentStableSet[str]] = ConcurrentStableDict()
    for project in graph.projects:
        changed_modules.set(project.name, ConcurrentStableSet())

    for rel in changed_set:
        category = _classify_change(rel)
        if category == "global":
            global_change = True
        elif category == "ops":
            ops_changed = True
        elif category == "preflight":
            preflight_changed = True
        else:
            for project in graph.projects:
                module = _module_of_source(rel, project)
                bucket = changed_modules.get(project.name)
                if module and bucket is not None:
                    bucket.add(module)

    selected_by_project: ConcurrentStableDict[str, ConcurrentStableSet[str]] = ConcurrentStableDict()
    reasons: ConcurrentStableList[str] = ConcurrentStableList()
    notes: ConcurrentStableList[str] = ConcurrentStableList()
    degraded = False
    if force_full:
        reasons.add("变更基准不可解析 ⇒ 强制退化全量")

    for project in graph.projects:
        files = graph.test_files.get(project.name) or ()
        total = len(files)
        selected: ConcurrentStableSet[str] = ConcurrentStableSet()
        modules = changed_modules.get(project.name) or ConcurrentStableSet()

        # 测试文件自身变更必须选中（changed 相对仓库根，测试文件相对 backend）
        for rel in files:
            if f"backend/{rel}" in changed_set:
                selected.add(rel)

        if global_change:
            selected.update(files)
            if total:
                degraded = True
                # 原因按工程循环触发，同一原因只登记一次（否则 10 个工程会打印 10 遍）
                if "全局配置 / 迁移 / 部署变更 ⇒ 全量" not in reasons:
                    reasons.add("全局配置 / 迁移 / 部署变更 ⇒ 全量")
        else:
            for rel in changed_set:
                for candidate in _isomorphic_candidates(backend, rel, project):
                    selected.add(candidate)
            if modules:
                for test_rel in files:
                    if test_rel in selected:
                        continue
                    deps = graph.test_deps.get(test_rel) or ConcurrentStableSet()
                    if any(module in deps for module in modules):
                        selected.add(test_rel)

            project_degraded = False
            if modules and not selected:
                project_degraded = True
                notes.add(f"{project.name}：变更模块无测试引用者 ⇒ 退化工程级全量")
            if len(selected) > base_threshold or (total and len(selected) / total > base_ratio):
                project_degraded = True
                notes.add(
                    f"{project.name}：受影响测试 {len(selected)}/{total} 超过基础模块阈值"
                    f"（{base_threshold} 个或 {base_ratio:.0%}）⇒ 退化工程级全量"
                )
            if project_degraded:
                selected.update(files)
                degraded = True
                reasons.add(f"{project.name} 退化工程级全量")

        selected_by_project.set(project.name, selected)

    if ops_changed:
        core = graph.test_files.get("bms_core") or ()
        core_selected = selected_by_project.get("bms_core")
        if core_selected is not None:
            added = 0
            for rel in core:
                if "/tests/ops/" in f"/{rel}" and rel not in core_selected:
                    core_selected.add(rel)
                    added += 1
            if added:
                notes.add(f"ops 变更 ⇒ 并入基座 tests/ops 用例 {added} 个")

    if preflight_changed:
        core_selected = selected_by_project.get("bms_core")
        if core_selected is not None:
            added = 0
            for rel in _PREFLIGHT_TESTS:
                if (backend / rel).is_file() and rel not in core_selected:
                    core_selected.add(rel)
                    added += 1
            if added:
                notes.add(f"预检脚本变更 ⇒ 并入护栏用例 {added} 个")

    test_paths: ConcurrentStableList[str] = ConcurrentStableList()
    metrics: ConcurrentStableList[ProjectMetrics] = ConcurrentStableList()
    for project in graph.projects:
        files = graph.test_files.get(project.name) or ()
        selected = selected_by_project.get(project.name) or ConcurrentStableSet()
        ordered: ConcurrentStableList[str] = ConcurrentStableList()
        for rel in files:
            if rel in selected:
                ordered.add(rel)
        test_paths.update(ordered)
        metrics.add(
            ProjectMetrics(
                name=project.name,
                picked=len(ordered),
                total=len(files),
                degraded=bool(files) and len(ordered) == len(files),
            )
        )

    cov_modules: ConcurrentStableSet[str] = ConcurrentStableSet()
    for rel in changed_set:
        for project in graph.projects:
            module = _module_of_source(rel, project)
            if module:
                cov_modules.add(module)

    return Selection(
        test_paths=tuple(test_paths),
        cov_modules=tuple(sorted(cov_modules)),
        degraded=degraded,
        reason="；".join(reasons),
        picked=len(test_paths),
        total=sum(metric.total for metric in metrics),
        projects=tuple(metrics),
        notes=tuple(notes),
    )


def expand_from_coverage(coverage_path: Path, modules: tuple[str, ...]) -> tuple[str, ...]:
    """扩圈：读覆盖率报告，返回「有缺行」的目标模块（供调用方并入测试集）。

    Args:
        coverage_path: `coverage.json` 路径。
        modules: 覆盖率目标模块（门禁范围）。

    Returns:
        tuple[str, ...]: 存在未覆盖行的模块（空表示已达标或报告不可读）。
    """
    try:
        data = json.loads(coverage_path.read_text(encoding="utf-8"))
    except OSError:
        return ()
    except ValueError:
        return ()
    files = data.get("files") or {}
    missing: ConcurrentStableSet[str] = ConcurrentStableSet()
    for module in modules:
        suffix = module.replace(".", "/")
        candidates = (f"{suffix}.py", f"{suffix}/__init__.py")
        for key, entry in files.items():
            norm = str(key).replace("\\", "/")
            if not any(norm.endswith(candidate) for candidate in candidates):
                continue
            lines = entry.get("missing_lines") or ()
            if lines:
                missing.add(module)
            break
    return tuple(missing)


def discover_frontend_packages(frontend: Path) -> tuple[FrontendPackage, ...]:
    """发现前端 pnpm 工程（`frontend/{packages,apps,modules}/*`）。

    Args:
        frontend: `frontend` 目录。

    Returns:
        tuple[FrontendPackage, ...]: 工程清单（按分组与目录名排序）。
    """
    packages: ConcurrentStableList[FrontendPackage] = ConcurrentStableList()
    for group in _FRONTEND_GROUPS:
        group_dir = frontend / group
        if not group_dir.is_dir():
            continue
        for item in sorted(group_dir.iterdir()):
            manifest = item / "package.json"
            if not item.is_dir() or not manifest.is_file():
                continue
            try:
                data = json.loads(manifest.read_text(encoding="utf-8"))
            except OSError:
                continue
            except ValueError:
                continue
            name = str(data.get("name") or "")
            if not name:
                continue
            merged: ConcurrentStableDict[str, object] = ConcurrentStableDict()
            for section in ("dependencies", "devDependencies", "peerDependencies"):
                block = data.get(section)
                if isinstance(block, dict):
                    for dep_name, spec in block.items():
                        merged.set(str(dep_name), spec)
            deps: ConcurrentStableList[str] = ConcurrentStableList()
            for dep_name, spec in merged.items():
                if isinstance(spec, str) and spec.startswith("workspace:"):
                    deps.add(dep_name)
            packages.add(
                FrontendPackage(
                    name=name,
                    path=item.relative_to(frontend.parent).as_posix(),
                    workspace_deps=tuple(deps),
                )
            )
    return tuple(packages)


def build_frontend_selection(
    frontend: Path,
    changed: tuple[str, ...] | ConcurrentStableList[str],
    *,
    force_full: bool = False,
) -> FrontendSelection:
    """按变更路径推导受影响前端包（workspace 依赖反向闭包 + 根配置退化）。

    Args:
        frontend: `frontend` 目录。
        changed: 变更路径（相对仓库根，posix 形态）。
        force_full: 强制退化为全部包。

    Returns:
        FrontendSelection: 前端选测结果。
    """
    packages = discover_frontend_packages(frontend)
    names: ConcurrentStableList[str] = ConcurrentStableList()
    for package in packages:
        names.add(package.name)

    direct: ConcurrentStableSet[str] = ConcurrentStableSet()
    global_change = force_full
    notes: ConcurrentStableList[str] = ConcurrentStableList()
    for item in changed:
        rel = _norm(item)
        if not rel:
            continue
        if rel in _FRONTEND_GLOBAL_EXACT or rel.startswith(_FRONTEND_GLOBAL_PREFIXES):
            global_change = True
            continue
        if not rel.startswith("frontend/"):
            continue
        matched = False
        for package in packages:
            if rel == package.path or rel.startswith(f"{package.path}/"):
                direct.add(package.name)
                matched = True
                break
        if not matched:
            # `frontend/` 下但不属于任何 pnpm 工程（如前端根 tsconfig）⇒ 无法定位影响面，保守退化
            global_change = True

    reason = ""
    if global_change:
        affected = set(names)
        if force_full:
            reason = "变更基准不可解析 ⇒ 强制退化全部前端包"
        else:
            reason = "根级配置 / 共享脚本 / 未归属文件变更 ⇒ 全部前端包"
        notes.add(reason)
    else:
        affected = set(direct)
        grew = True
        while grew:
            grew = False
            for package in packages:
                if package.name in affected:
                    continue
                if any(dep in affected for dep in package.workspace_deps):
                    affected.add(package.name)
                    grew = True
        if direct:
            notes.add(f"{'、'.join(sorted(direct))} 变更 ⇒ workspace 反向闭包 {len(affected)} 个包")

    ordered: ConcurrentStableList[str] = ConcurrentStableList()
    for name in names:
        if name in affected:
            ordered.add(name)
    return FrontendSelection(
        packages=tuple(ordered),
        degraded=global_change,
        reason=reason,
        notes=tuple(notes),
    )


def _ref_exists(root: Path, ref: str) -> bool:
    """git 引用是否可解析（浅克隆 / 新分支下 `CI_MERGE_REQUEST_DIFF_BASE_SHA` 可能不在本地）。

    Args:
        root: 仓库根。
        ref: 提交号 / 分支。

    Returns:
        bool: 是否可解析。
    """
    result = subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", ref],
        cwd=root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return result.returncode == 0


def _git_changed(root: Path, since: str) -> tuple[str, ...]:
    """取自 `since` 以来的改动路径（含未跟踪文件）。

    Args:
        root: 仓库根。
        since: 对比基准（提交号 / 分支）。

    Returns:
        tuple[str, ...]: 改动路径（相对仓库根，posix 形态）。
    """
    paths: ConcurrentStableList[str] = ConcurrentStableList()
    for args in (["diff", "--name-only", since], ["ls-files", "--others", "--exclude-standard"]):
        result = subprocess.run(
            ["git", *args], cwd=root, capture_output=True, text=True, encoding="utf-8", errors="replace"
        )
        if result.returncode != 0:
            continue
        for line in result.stdout.splitlines():
            rel = _norm(line)
            if rel and rel not in paths:
                paths.add(rel)
    return tuple(paths)


def read_changed(
    root: Path,
    *,
    changed_from: str,
    changed_files: tuple[str, ...] | ConcurrentStableList[str],
    changed_file_list: str,
) -> tuple[str, ...]:
    """汇总变更路径（显式文件 ∪ 清单文件 ∪ git diff）。

    Args:
        root: 仓库根。
        changed_from: git 基准。
        changed_files: 显式变更文件（可重复）。
        changed_file_list: 变更清单文件路径。

    Returns:
        tuple[str, ...]: 去重后的变更路径（相对仓库根，posix 形态）。

    Raises:
        RuntimeError: `changed_from` 不可解析（浅克隆 / 基准分支不存在）——调用方应显式退化全量。
    """
    if changed_from and not _ref_exists(root, changed_from):
        raise RuntimeError(f"变更基准不可解析：{changed_from}")
    changed: ConcurrentStableList[str] = ConcurrentStableList()
    for item in changed_files:
        rel = _norm(item)
        if rel and rel not in changed:
            changed.add(rel)
    if changed_file_list:
        path = Path(changed_file_list)
        if path.is_file():
            for line in path.read_text(encoding="utf-8").splitlines():
                rel = _norm(line)
                if rel and rel not in changed:
                    changed.add(rel)
    if changed_from:
        for rel in _git_changed(root, changed_from):
            if rel not in changed:
                changed.add(rel)
    return tuple(changed)


def _format(selection: Selection, fmt: str) -> str:
    """按格式输出后端选测结果。

    Args:
        selection: 后端选测结果。
        fmt: `json` / `pytest-args` / `cov-args` / `projects`。

    Returns:
        str: 输出文本。
    """
    if fmt == "pytest-args":
        return " ".join(selection.test_paths)
    if fmt == "cov-args":
        return " ".join(f"--cov={module}" for module in selection.cov_modules)
    if fmt == "projects":
        return " ".join(metric.name for metric in selection.projects)
    payload = {
        "test_paths": list(selection.test_paths),
        "cov_modules": list(selection.cov_modules),
        "degraded": selection.degraded,
        "reason": selection.reason,
        "picked": selection.picked,
        "total": selection.total,
        "projects": {
            metric.name: {"picked": metric.picked, "total": metric.total, "degraded": metric.degraded}
            for metric in selection.projects
        },
        "notes": list(selection.notes),
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _format_frontend(selection: FrontendSelection, fmt: str) -> str:
    """按格式输出前端选测结果。

    Args:
        selection: 前端选测结果。
        fmt: `json` / `packages`。

    Returns:
        str: 输出文本。
    """
    if fmt == "packages":
        return " ".join(selection.packages)
    payload = {
        "packages": list(selection.packages),
        "degraded": selection.degraded,
        "reason": selection.reason,
        "notes": list(selection.notes),
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def main(argv: tuple[str, ...] | None = None) -> int:
    """命令行入口。

    Args:
        argv: 参数（缺省取 `sys.argv[1:]`）。

    Returns:
        int: 退出码（0 正常 / 1 推导异常）。
    """
    parser = argparse.ArgumentParser(description="变更影响分析选测器（后端测试 / 前端包）")
    parser.add_argument("--root", default=str(_REPO_ROOT), help="bms 仓库根（缺省按脚本位置定位）")
    parser.add_argument("--scope", default="backend", choices=("backend", "frontend"), help="推导范围")
    parser.add_argument("--changed-from", default="", help="对比基准（git 引用，如 origin/main）")
    parser.add_argument("--changed-file", action="append", default=[], help="显式指定变更文件（可重复）")
    parser.add_argument("--changed-file-list", default="", help="变更清单文件（一行一个路径）")
    parser.add_argument("--force-full", action="store_true", help="强制退化全量（基准不可解析时）")
    parser.add_argument(
        "--format",
        default="json",
        choices=("json", "pytest-args", "cov-args", "projects", "packages"),
        help="输出格式（packages 仅 --scope frontend）",
    )
    parser.add_argument("--base-threshold", type=int, default=_BASE_TEST_THRESHOLD, help="基础模块绝对阈值")
    parser.add_argument("--base-ratio", type=float, default=_BASE_TEST_RATIO, help="基础模块占比阈值")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    try:
        changed = read_changed(
            root,
            changed_from=args.changed_from,
            changed_files=tuple(args.changed_file),
            changed_file_list=args.changed_file_list,
        )
    except RuntimeError as error:
        print(f"[test-selection] {error}（确需全量请加 --force-full）", file=sys.stderr)
        return 1

    if args.scope == "frontend":
        selection = build_frontend_selection(root / "frontend", changed, force_full=args.force_full)
        print(_format_frontend(selection, args.format))
        return 0

    try:
        selection = build_selection(
            root / "backend",
            changed,
            base_threshold=args.base_threshold,
            base_ratio=args.base_ratio,
            force_full=args.force_full,
        )
    except RuntimeError as error:
        print(f"[test-selection] {error}", file=sys.stderr)
        return 1
    print(_format(selection, args.format))
    return 0


if __name__ == "__main__":
    sys.exit(main())
