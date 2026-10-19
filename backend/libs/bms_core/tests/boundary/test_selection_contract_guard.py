"""选测口径固化与机器护栏用例（Kiwi 2319）。

锁定 `13_03` 详细设计（`bms文档/项目/02_后端基座与服务化地基/任务/13_测试执行粒度与工程效能/
13_测试执行粒度与工程效能_03_口径固化与机器护栏/设计/01_详细设计_03_口径固化与机器护栏.md`）：

- **同一来源**：预检与 CI 都只经共享推导（选测器）与共享执行（执行器）入口，两侧不各写映射规则；
- **新增工程必登记**：自动发现的工程必须同时登记到全量档工程级范围与覆盖率采集范围；
- **退化显式**：四类退化触发都给出原因，且预检 / 执行器都打印（不静默）；
- **扩圈不静默**：扩圈有轮次上限，无增长 / 轮次用尽都打印原因并退化全量重跑；
- **规范↔实现零漂移**：《测试规范》§2.1 六子节存在、各有实现锚点，且正文不写脚本文件名；
- **基座校验脚本映射**：改 `scripts/tools/base-check/<脚本>` 必跑其护栏用例，映射表须覆盖全部脚本。

本文件同时被加入选测器的预检护栏清单（`_PREFLIGHT_TESTS`）：改选测器 / 预检脚本时必跑本文件。
"""

import importlib.util
import json
import re
import sys
from pathlib import Path
from typing import Any

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[5]
_PREFLIGHT_DIR = _REPO_ROOT / "scripts" / "tools" / "preflight"
if str(_PREFLIGHT_DIR) not in sys.path:
    sys.path.insert(0, str(_PREFLIGHT_DIR))

_BACKEND = _REPO_ROOT / "backend"
_SPEC = _REPO_ROOT / "bms文档" / "规范" / "测试规范.md"


def _load_script(name: str, path: Path) -> Any:
    """按路径加载预检脚本模块（文件名可能带连字符，不能直接 `import`）。

    Args:
        name: 注册到 `sys.modules` 的模块名。
        path: 脚本路径。

    Returns:
        Any: 模块对象。
    """
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


test_selection: Any = _load_script("test_selection", _PREFLIGHT_DIR / "test_selection.py")
_PREFLIGHT: Any = _load_script("preflight_contract_guard", _PREFLIGHT_DIR / "check-preflight.py")


def _spec_text() -> str:
    """《测试规范》全文（供规范条款断言）。"""
    return _SPEC.read_text(encoding="utf-8")


def _spec_section_21() -> str:
    """《测试规范》§2.1 正文（到 §3 标题前；供「不写脚本名」断言）。"""
    text = _spec_text()
    start = text.index("### 2.1 被测物与执行范围")
    end = text.index("## 3. 命名规范")
    return text[start:end]


# ===== A 同一来源 =====


@pytest.mark.kiwi_id(2319)
def test_preflight_delegates_to_selector() -> None:
    """预检的定向推导委托选测器，且预检源码不另写路径映射规则（工程级目录映射）。"""
    source = (_PREFLIGHT_DIR / "check-preflight.py").read_text(encoding="utf-8")
    body = source.split("def _scope_targets(", 1)[1].split("def ", 1)[0]
    assert "test_selection.build_selection(" in body
    # 反向断言：旧的「工程级目录映射」写法不得复活（改回工程级即失去细粒度选测）
    assert "_add_test_dir" not in source
    assert "_add_cov_target" not in source


@pytest.mark.kiwi_id(2319)
def test_ci_uses_shared_entries_only() -> None:
    """CI 后端只经执行器入口、前端三个 job 只经选测器入口；不出现旧的「四包全量」写法。"""
    ci = (_REPO_ROOT / ".gitlab-ci.yml").read_text(encoding="utf-8")
    assert "scripts/tools/preflight/run-selected.py" in ci
    assert "scripts/tools/preflight/test_selection.py" in ci
    # 旧口径：core-check 以 `pnpm run check` 串四包全量（13_01 已替换为按包执行）。
    # 只看可执行命令行（缩进 `- ` 开头），注释里提及旧写法属说明性文字、不算回退。
    commands = [line.strip()[2:] for line in ci.splitlines() if line.strip().startswith("- ")]
    assert not any(command.startswith("pnpm run check") for command in commands)
    # 前端三个 job 共用同一选测片段（.test-selection 隐藏 job）
    assert ".test-selection:" in ci
    assert ci.count("extends: .test-selection") == 3


@pytest.mark.kiwi_id(2319)
def test_cli_matches_library_on_same_change(capsys: pytest.CaptureFixture[str]) -> None:
    """同一变更集合：选测器 CLI 输出与库函数结果字段级全等（预检与 CI 消费同一实现）。"""
    rel = "backend/libs/bms_core/src/bms_core/db/bootstrap.py"
    library = json.loads(test_selection._format(test_selection.build_selection(_BACKEND, (rel,)), "json"))

    code = test_selection.main(("--root", str(_REPO_ROOT), "--changed-file", rel, "--format", "json"))

    assert code == 0
    assert json.loads(capsys.readouterr().out) == library


# ===== B 新增工程必登记 =====


@pytest.mark.kiwi_id(2319)
def test_discovered_projects_registered_in_preflight_roots() -> None:
    """自动发现的每个工程目录都登记在全量档工程级范围（`_ROOTS`）内。"""
    discovered = _PREFLIGHT.discovered_projects(_BACKEND)
    roots = set(_PREFLIGHT._ROOTS)  # pyright: ignore[reportPrivateUsage]

    assert len(discovered) == len(roots) == 10
    assert {directory for directory, _ in discovered} == roots


@pytest.mark.kiwi_id(2319)
def test_discovered_projects_registered_in_coverage_packages() -> None:
    """自动发现的每个顶层包都登记在覆盖率采集范围（`_COVERAGE_PACKAGES`）内。"""
    discovered = _PREFLIGHT.discovered_projects(_BACKEND)
    packages = set(_PREFLIGHT._COVERAGE_PACKAGES)  # pyright: ignore[reportPrivateUsage]

    assert {package for _, package in discovered} == packages


@pytest.mark.kiwi_id(2319)
def test_unregistered_project_detected() -> None:
    """对账纯函数：登记齐备返回空；「目录有、登记无」返回未登记项（新增工程不会静默漏跑）。"""
    registered = (("libs/demo", "demo"),)
    assert _PREFLIGHT.unregistered_projects(registered, ("libs/demo",), ("demo",)) == ()

    unregistered = _PREFLIGHT.unregistered_projects(
        (("libs/demo", "demo"), ("services/new", "bms_new")), ("libs/demo",), ("demo",)
    )
    assert any("services/new" in item for item in unregistered)
    assert any("bms_new" in item for item in unregistered)


# ===== C 退化显式 =====


@pytest.mark.kiwi_id(2319)
def test_degrade_reason_non_empty_for_all_triggers() -> None:
    """四类退化触发（全局变更 / 绝对阈值 / 无引用者 / 强制全量）`reason` 均非空。"""
    global_change = test_selection.build_selection(_BACKEND, ("deploy/compose/gateway.yml",))
    assert global_change.degraded and global_change.reason

    over_threshold = test_selection.build_selection(
        _BACKEND, ("backend/libs/bms_core/src/bms_core/db/bootstrap.py",), base_threshold=1
    )
    assert over_threshold.degraded and over_threshold.reason

    base_module = test_selection.build_selection(_BACKEND, ("backend/libs/bms_core/src/bms_core/core/exceptions.py",))
    assert base_module.degraded and base_module.reason

    forced = test_selection.build_selection(_BACKEND, (), force_full=True)
    assert forced.degraded
    assert "强制退化全量" in forced.reason


@pytest.mark.kiwi_id(2319)
def test_degrade_notes_name_project() -> None:
    """逐工程退化时 `notes` 含工程名与原因文本（可定位是哪个工程跑了全量）。"""
    selection = test_selection.build_selection(
        _BACKEND, ("backend/libs/bms_core/src/bms_core/db/bootstrap.py",), base_threshold=1
    )

    assert any("bms_core" in note and "退化工程级全量" in note for note in selection.notes)


@pytest.mark.kiwi_id(2319)
def test_degrade_printed_by_preflight_and_runner() -> None:
    """预检与执行器都打印退化原因与逐条说明（不静默退化）。"""
    preflight = (_PREFLIGHT_DIR / "check-preflight.py").read_text(encoding="utf-8")
    runner = (_PREFLIGHT_DIR / "run-selected.py").read_text(encoding="utf-8")

    assert "退化：" in preflight
    assert "说明：" in preflight
    assert "退化：" in runner
    assert "说明：" in runner


# ===== D 扩圈不静默 =====


@pytest.mark.kiwi_id(2319)
def test_expand_loop_has_bound_and_fallback() -> None:
    """执行器：扩圈有轮次上限，无增长 / 轮次用尽都打印原因并退化全量重跑一次。"""
    runner = (_PREFLIGHT_DIR / "run-selected.py").read_text(encoding="utf-8")

    assert "--max-rounds" in runner
    assert "扩圈无新增测试" in runner
    assert "扩圈轮次用尽" in runner
    assert "退化工程级全量重跑" in runner
    # 不静默放弃：两条失败路径都打印原因后才返回非零
    assert runner.count("_print_metrics(") >= 6


@pytest.mark.kiwi_id(2319)
def test_metrics_line_reports_rounds() -> None:
    """度量行含 picked / total / degraded / rounds / cov 五项（复盘可取数）。"""
    runner = (_PREFLIGHT_DIR / "run-selected.py").read_text(encoding="utf-8")

    for field in ("picked=", "degraded=", "rounds=", "cov="):
        assert field in runner, field
    assert "[test-selection] picked=" in runner


@pytest.mark.kiwi_id(2319)
def test_expand_returns_missing_modules_only() -> None:
    """扩圈只对缺口模块扩：已覆盖模块返回空（不重复重跑）。"""
    selection = test_selection.build_selection(_BACKEND, ("backend/libs/bms_core/src/bms_core/db/bootstrap.py",))
    assert selection.cov_modules

    covered = _REPO_ROOT / "backend" / "coverage.contract-guard.json"
    covered.write_text(
        json.dumps({"files": {f"{_BACKEND}/libs/bms_core/src/bms_core/db/bootstrap.py": {"missing_lines": []}}}),
        encoding="utf-8",
    )
    try:
        assert test_selection.expand_from_coverage(covered, selection.cov_modules) == ()
    finally:
        covered.unlink(missing_ok=True)


# ===== E 规范↔实现零漂移 =====


@pytest.mark.kiwi_id(2319)
def test_spec_has_six_subsection_titles() -> None:
    """《测试规范》§2.1 含 2.1.1~2.1.6 六个执行细则子节（口径已固化）。"""
    section = _spec_section_21()

    for index, title in enumerate(
        (
            "2.1.1 变更影响分析：推导依据",
            "2.1.2 双重收敛与差集口径",
            "2.1.3 退化条件与显式输出",
            "2.1.4 覆盖率扩圈",
            "2.1.5 预检与 CI 两侧一致性",
            "2.1.6 执行侧配套口径",
        ),
        start=1,
    ):
        assert title in section, f"{index}. {title}"


@pytest.mark.kiwi_id(2319)
def test_spec_clauses_have_implementation_anchors() -> None:
    """五条细则各有实现侧锚点（规范写了的能力，实现里确实存在）。"""
    selector = (_PREFLIGHT_DIR / "test_selection.py").read_text(encoding="utf-8")

    # 2.1.1 推导依据：工程 / 包按目录自动发现（不维护白名单）
    assert "def discover_projects(" in selector
    assert "def discover_frontend_packages(" in selector
    # 2.1.2 双重收敛与差集：目录同构 + 导入闭包
    assert "def _isomorphic_candidates(" in selector
    assert "def _transitive_deps(" in selector
    # 2.1.3 退化：三类触发常量 + 强制全量
    assert "_BASE_TEST_THRESHOLD" in selector
    assert "_GLOBAL_EXACT" in selector
    assert "force_full" in selector
    # 2.1.4 扩圈：缺口反查
    assert "def expand_from_coverage(" in selector
    assert "def tests_for_modules(" in selector
    # 2.1.5 两侧一致性：预检与 CI 同一入口（CLI + 执行器）
    assert "def main(" in selector
    assert "run-selected.py" in (_PREFLIGHT_DIR / "README.md").read_text(encoding="utf-8")


@pytest.mark.kiwi_id(2319)
def test_spec_section_has_no_script_names() -> None:
    """§2.1 正文不写脚本文件名（改名不产生规范漂移；落点由工程说明承载）。"""
    section = _spec_section_21()

    assert not re.search(r"[A-Za-z0-9_-]+\.py", section), re.findall(r"[A-Za-z0-9_-]+\.py", section)


# ===== F 基座校验脚本映射 =====


@pytest.mark.kiwi_id(2319)
def test_base_check_change_selects_its_guard() -> None:
    """改基座校验脚本 ⇒ 选中其护栏用例；未登记脚本 ⇒ 并入 boundary 全部护栏。"""
    mapped = test_selection.build_selection(_BACKEND, ("scripts/tools/base-check/check-bare-collections.py",))
    assert "libs/bms_core/tests/boundary/test_bare_collections_guard.py" in mapped.test_paths
    assert any("基座校验脚本变更" in note for note in mapped.notes)

    unmapped = test_selection.build_selection(_BACKEND, ("scripts/tools/base-check/check-base.py",))
    boundary = {
        path.relative_to(_BACKEND).as_posix() for path in (_BACKEND / "libs/bms_core/tests/boundary").glob("test_*.py")
    }
    assert boundary <= set(unmapped.test_paths)
    assert unmapped.cov_modules == ()


@pytest.mark.kiwi_id(2319)
def test_base_check_map_covers_every_script() -> None:
    """映射表覆盖 `scripts/tools/base-check/` 下全部脚本（新增脚本未登记即失败）。"""
    scripts = {path.name for path in (_PREFLIGHT_DIR.parent / "base-check").glob("*.py")}
    mapped = {script for script, _ in test_selection._BASE_CHECK_TESTS}

    assert mapped <= scripts
    assert scripts - mapped == {
        "check-base.py",
        "check-docs-scope.py",
        "check-links.py",
        "check-prototype-review.py",
        "check-system-fields.py",
    }
    for script, test in test_selection._BASE_CHECK_TESTS:
        assert (_BACKEND / test).is_file(), f"{script} → {test} 不存在"


# ===== G 前端选测 job 的执行环境 =====


@pytest.mark.kiwi_id(2319)
def test_ci_backend_image_node_satisfies_pnpm_requirement() -> None:
    """前端选测 job 所用镜像的 Node 版本必须满足仓根 `packageManager` 的 pnpm 版本要求。

    背景（流水线 #1089 实测）：13_01 把三个前端选测 job 从 `ci-frontend:node22` 迁到
    `ci-backend:py314`（后者 python3 为 3.14，能解析 bms_core 的 PEP 695），但该镜像原预装
    Node 22.12.0，而 `pnpm@11.7.0` 要求 Node ≥ 22.13 ⇒ 三个 job 在 `pnpm install --frozen-lockfile`
    处直接失败。本用例把「镜像 Node 版本 ≥ pnpm 要求的最低 Node」变成机器断言，防止再次漂移。
    """
    dockerfile = (_REPO_ROOT / "deploy" / "ci" / "Dockerfile.backend").read_text(encoding="utf-8")
    match = re.search(r"^ARG NODE_VERSION=(\d+)\.(\d+)\.(\d+)", dockerfile, re.MULTILINE)
    assert match is not None, "Dockerfile.backend 未声明 NODE_VERSION"
    node_version = tuple(int(part) for part in match.groups())

    manifest = json.loads((_REPO_ROOT / "package.json").read_text(encoding="utf-8"))
    manager = str(manifest.get("packageManager") or "")
    assert manager.startswith("pnpm@"), manager
    pnpm_major = int(manager.removeprefix("pnpm@").split(".")[0])

    # pnpm 11 要求 Node ≥ 22.13；pnpm 10 及以下对 Node 22 无此下限（留出主版本分档，避免硬编码未来值）
    minimum = (22, 13, 0) if pnpm_major >= 11 else (22, 0, 0)
    assert node_version >= minimum, (
        f"ci-backend 镜像 Node {'.'.join(map(str, node_version))} 低于 pnpm@{pnpm_major} 要求的 "
        f"{'.'.join(map(str, minimum))}（{manager}）⇒ 三个前端选测 job 会在 pnpm install 处失败"
    )
