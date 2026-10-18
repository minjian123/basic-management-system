"""变更影响分析选测器护栏用例（Kiwi 2316）：推导口径、退化路径与扩圈契约。

锁定 `13_01` 详细设计（`bms文档/项目/02_后端基座与服务化地基/任务/13_测试执行粒度与工程效能/
13_测试执行粒度与工程效能_01_变更影响分析与细粒度选测/设计/01_详细设计_01_变更影响分析与细粒度选测.md`）：

- **单一来源**：预检与 CI 共用 `scripts/tools/preflight/test_selection.py`（CLI 输出与库结果一致）；
- **双重收敛**：目录同构（含「仅源码有」差集）+ AST 导入图（跨目录、传递依赖）；
- **显式退化**：基础模块 / 无引用者 / 全局变更 / 基准不可解析 ⇒ 工程级全量且打印原因；
- **前端同构**：`workspace:*` 依赖反向闭包 + 根级配置全包退化；
- **扩圈**：覆盖率缺行模块反查引用测试，无增长由调用方退化全量。
"""

import importlib.util
import json
import sys
from collections.abc import Iterable
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[5]
_SCRIPT = _REPO_ROOT / "scripts" / "tools" / "preflight" / "test_selection.py"
_spec = importlib.util.spec_from_file_location("test_selection_guard", _SCRIPT)
assert _spec is not None and _spec.loader is not None
test_selection = importlib.util.module_from_spec(_spec)
sys.modules["test_selection_guard"] = test_selection
_spec.loader.exec_module(test_selection)

_BACKEND = _REPO_ROOT / "backend"
_FRONTEND = _REPO_ROOT / "frontend"


def _write(path: Path, text: str) -> None:
    """写文件（自动建父目录）。

    Args:
        path: 目标文件。
        text: 文件内容。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _make_project(
    root: Path,
    *,
    name: str = "demo",
    sources: Iterable[tuple[str, str]] = (),
    tests: Iterable[tuple[str, str]] = (),
) -> Path:
    """在临时仓库根构造一个最小后端工程（`backend/libs/<name>`）。

    Args:
        root: 临时仓库根。
        name: 工程与包名。
        sources: 相对 `src/<包>/` 的源文件内容。
        tests: 相对 `tests/` 的测试文件内容。

    Returns:
        Path: 工程目录。
    """
    project = root / "backend" / "libs" / name
    _write(project / "src" / name / "__init__.py", "")
    for rel, text in sources:
        _write(project / "src" / name / rel, text)
    (project / "tests").mkdir(parents=True, exist_ok=True)
    for rel, text in tests:
        _write(project / "tests" / rel, text)
    return project


@pytest.mark.kiwi_id(2316)
def test_discover_projects_libs_and_services() -> None:
    """工程发现：1 个库 + 9 个服务；库在前、服务按名排序；路径口径正确。"""
    projects = test_selection.discover_projects(_BACKEND)
    names = [project.name for project in projects]

    assert len(projects) == 10
    assert names[0] == "bms_core"
    assert names[1:] == sorted(names[1:])
    assert {"bms_platform", "bms_identity", "bms_txn"} <= set(names)
    assert projects[0].src == "backend/libs/bms_core/src"
    assert projects[0].tests == "libs/bms_core/tests"


@pytest.mark.kiwi_id(2316)
def test_isomorphic_candidates_hit_same_named_dir() -> None:
    """目录同构：`db/bootstrap.py` 的候选全部落在 `tests/db/`。"""
    project = test_selection.discover_projects(_BACKEND)[0]
    candidates = test_selection._isomorphic_candidates(
        _BACKEND, "backend/libs/bms_core/src/bms_core/db/bootstrap.py", project
    )

    assert candidates
    assert all(rel.startswith("libs/bms_core/tests/db/") for rel in candidates)
    assert all(Path(rel).name.startswith("test_") for rel in candidates)


@pytest.mark.kiwi_id(2316)
def test_isomorphic_candidates_empty_without_test_dir(tmp_path: Path) -> None:
    """目录同构差集：源目录无同名测试目录时候选为空（不抛错，交给 AST 图兜底）。"""
    root = tmp_path
    _make_project(
        root,
        sources=(("onlysrc/a.py", "VALUE = 1\n"),),
        tests=(("test_other.py", "def test_x():\n    pass\n"),),
    )
    project = test_selection.discover_projects(root / "backend")[0]

    assert (
        test_selection._isomorphic_candidates(root / "backend", "backend/libs/demo/src/demo/onlysrc/a.py", project)
        == ()
    )


@pytest.mark.kiwi_id(2316)
def test_transitive_import_pulls_test(tmp_path: Path) -> None:
    """AST 传递收敛：测试只 import `a`，变更 `c`（a→b→c）仍选中该测试。"""
    root = tmp_path
    _make_project(
        root,
        sources=(
            ("a.py", "from .b import VALUE\n"),
            ("b.py", "from .c import VALUE\n"),
            ("c.py", "VALUE = 1\n"),
        ),
        tests=(
            ("test_a.py", "from demo.a import VALUE\n\n\ndef test_value() -> None:\n    assert VALUE == 1\n"),
            ("other/test_f1.py", "def test_f1() -> None:\n    pass\n"),
            ("other/test_f2.py", "def test_f2() -> None:\n    pass\n"),
            ("other/test_f3.py", "def test_f3() -> None:\n    pass\n"),
        ),
    )

    selection = test_selection.build_selection(root / "backend", ("backend/libs/demo/src/demo/c.py",))

    assert "libs/demo/tests/test_a.py" in selection.test_paths
    assert selection.cov_modules == ("demo.c",)
    assert not selection.degraded


@pytest.mark.kiwi_id(2316)
def test_cross_directory_reference() -> None:
    """跨目录引用：改 `core/exceptions.py` 影响面超阈值 ⇒ 显式退化工程级全量。"""
    selection = test_selection.build_selection(_BACKEND, ("backend/libs/bms_core/src/bms_core/core/exceptions.py",))
    metrics = {metric.name: metric for metric in selection.projects}["bms_core"]

    assert selection.degraded
    assert metrics.picked == metrics.total
    assert "bms_core 退化工程级全量" in selection.reason


@pytest.mark.kiwi_id(2316)
def test_changed_test_file_always_selected() -> None:
    """测试文件自身变更必选（回归「相对 backend 与相对仓库根基准不一致」缺陷）。"""
    rel = "libs/bms_core/tests/db/test_keys.py"
    selection = test_selection.build_selection(_BACKEND, (f"backend/{rel}",))

    assert rel in selection.test_paths


@pytest.mark.kiwi_id(2316)
def test_degrade_over_threshold() -> None:
    """基础模块绝对阈值：受影响测试超过 `--base-threshold` ⇒ 该工程退化全量。"""
    selection = test_selection.build_selection(
        _BACKEND,
        ("backend/libs/bms_core/src/bms_core/db/bootstrap.py",),
        base_threshold=1,
    )
    metrics = {metric.name: metric for metric in selection.projects}["bms_core"]

    assert selection.degraded
    assert metrics.picked == metrics.total
    assert any("超过基础模块阈值" in note for note in selection.notes)


@pytest.mark.kiwi_id(2316)
def test_degrade_when_no_referrer(tmp_path: Path) -> None:
    """无引用者：变更模块无任何测试引用 ⇒ 退化工程级全量并说明原因。"""
    root = tmp_path
    _make_project(
        root,
        sources=(("orphan.py", "VALUE = 1\n"),),
        tests=(("other/test_other.py", "def test_x() -> None:\n    pass\n"),),
    )

    selection = test_selection.build_selection(root / "backend", ("backend/libs/demo/src/demo/orphan.py",))

    assert selection.degraded
    assert any("无测试引用者" in note for note in selection.notes)


@pytest.mark.kiwi_id(2316)
def test_degrade_on_global_change() -> None:
    """全局变更（pyproject / 部署 / 配置）⇒ 全部工程全量。"""
    for rel in ("backend/pyproject.toml", "deploy/compose/gateway.yml", "backend/config.toml"):
        selection = test_selection.build_selection(_BACKEND, (rel,))
        assert selection.degraded, rel
        assert selection.picked == selection.total, rel


@pytest.mark.kiwi_id(2316)
def test_degrade_reason_visible() -> None:
    """退化不静默：`reason` 非空（供预检与 CI 打印「为什么跑全量」）。"""
    selection = test_selection.build_selection(_BACKEND, ("deploy/compose/gateway.yml",))

    assert selection.degraded
    assert selection.reason


@pytest.mark.kiwi_id(2316)
def test_force_full_forces_degrade() -> None:
    """基准不可解析：`--force-full` ⇒ 全量 + 显式原因。"""
    selection = test_selection.build_selection(_BACKEND, (), force_full=True)

    assert selection.degraded
    assert selection.picked == selection.total
    assert "强制退化全量" in selection.reason


@pytest.mark.kiwi_id(2316)
def test_ops_change_maps_to_ops_tests() -> None:
    """`ops` 变更：只并入基座 `tests/ops` 用例，不产生覆盖率目标。"""
    selection = test_selection.build_selection(_BACKEND, ("backend/ops/test_db.py",))

    assert selection.test_paths
    assert all("/tests/ops/" in f"/{rel}" for rel in selection.test_paths)
    assert selection.cov_modules == ()
    assert any("ops 变更" in note for note in selection.notes)


@pytest.mark.kiwi_id(2316)
def test_preflight_script_change_selects_guards() -> None:
    """预检脚本变更：并入 3 个护栏用例（改选测器必须跑其用例）。"""
    selection = test_selection.build_selection(_BACKEND, ("scripts/tools/preflight/run-selected.py",))

    for rel in test_selection._PREFLIGHT_TESTS:
        assert rel in selection.test_paths, rel
    assert selection.cov_modules == ()


@pytest.mark.kiwi_id(2316)
def test_docs_and_frontend_change_yields_empty() -> None:
    """纯文档 / 前端变更：不引后端测试与覆盖率目标。"""
    selection = test_selection.build_selection(
        _BACKEND, ("bms文档/规范/测试规范.md", "frontend/apps/desktop/src/main.ts")
    )

    assert selection.picked == 0
    assert selection.cov_modules == ()
    assert not selection.degraded


@pytest.mark.kiwi_id(2316)
def test_frontend_package_discovery() -> None:
    """前端包发现：4 packages + 1 app + 3 modules；`workspace:*` 依赖边正确。"""
    packages = {package.name: package for package in test_selection.discover_frontend_packages(_FRONTEND)}

    assert len(packages) == 8
    assert packages["@bms/core"].path == "frontend/packages/core"
    assert packages["@bms/core"].workspace_deps == ()
    assert packages["@bms/vue"].workspace_deps == ("@bms/core",)
    assert packages["@bms/api-types"].workspace_deps == ("@bms/core",)
    assert packages["@bms/desktop"].workspace_deps == ("@bms/api-types", "@bms/core", "@bms/ui-ep")


@pytest.mark.kiwi_id(2316)
def test_frontend_dependency_reverse_closure() -> None:
    """前端反向闭包：改 `@bms/core` ⇒ 依赖它的包全部受影响。"""
    selection = test_selection.build_frontend_selection(_FRONTEND, ("frontend/packages/core/src/base/x.ts",))

    assert "@bms/core" in selection.packages
    assert {"@bms/vue", "@bms/ui-ep", "@bms/desktop", "@bms/module-demo"} <= set(selection.packages)
    assert not selection.degraded


@pytest.mark.kiwi_id(2316)
def test_frontend_root_config_degrades_all() -> None:
    """前端根级配置：`pnpm-lock.yaml` 变更 ⇒ 全部包 + 显式退化。"""
    selection = test_selection.build_frontend_selection(_FRONTEND, ("pnpm-lock.yaml",))

    assert len(selection.packages) == 8
    assert selection.degraded
    assert selection.reason


@pytest.mark.kiwi_id(2316)
def test_frontend_unrelated_change_empty() -> None:
    """非前端变更：不引任何前端包。"""
    selection = test_selection.build_frontend_selection(
        _FRONTEND, ("backend/libs/bms_core/src/bms_core/core/exceptions.py",)
    )

    assert selection.packages == ()
    assert not selection.degraded


@pytest.mark.kiwi_id(2316)
def test_expand_adds_tests_for_missing_modules(tmp_path: Path) -> None:
    """扩圈：覆盖率缺行模块 ⇒ 反查其引用测试并入。"""
    root = tmp_path
    _make_project(
        root,
        sources=(("a.py", "from .c import VALUE\n"), ("c.py", "VALUE = 1\n")),
        tests=(("test_a.py", "from demo.a import VALUE\n\n\ndef test_value() -> None:\n    assert VALUE == 1\n"),),
    )
    coverage = tmp_path / "coverage.json"
    coverage.write_text(
        json.dumps({"files": {str(root / "backend/libs/demo/src/demo/c.py"): {"missing_lines": [1]}}}),
        encoding="utf-8",
    )

    missing = test_selection.expand_from_coverage(coverage, ("demo.c",))
    assert missing == ("demo.c",)
    assert "libs/demo/tests/test_a.py" in test_selection.tests_for_modules(root / "backend", missing)


@pytest.mark.kiwi_id(2316)
def test_expand_ignores_covered_modules(tmp_path: Path) -> None:
    """扩圈：模块已全覆盖（无缺行）⇒ 返回空（调用方不重跑）。"""
    root = tmp_path
    _make_project(
        root,
        sources=(("c.py", "VALUE = 1\n"),),
        tests=(("test_c.py", "def test_x() -> None:\n    pass\n"),),
    )
    coverage = tmp_path / "coverage.json"
    coverage.write_text(
        json.dumps({"files": {str(root / "backend/libs/demo/src/demo/c.py"): {"missing_lines": []}}}),
        encoding="utf-8",
    )

    assert test_selection.expand_from_coverage(coverage, ("demo.c",)) == ()


@pytest.mark.kiwi_id(2316)
def test_cli_json_matches_library(capsys: pytest.CaptureFixture[str]) -> None:
    """单一来源：CLI（预检 / CI 消费）与库函数输出一致。"""
    rel = "backend/libs/bms_core/src/bms_core/db/bootstrap.py"
    library = json.loads(test_selection._format(test_selection.build_selection(_BACKEND, (rel,)), "json"))

    code = test_selection.main(("--root", str(_REPO_ROOT), "--changed-file", rel, "--format", "json"))
    printed = json.loads(capsys.readouterr().out)

    assert code == 0
    assert printed == library


@pytest.mark.kiwi_id(2316)
def test_cli_frontend_packages(capsys: pytest.CaptureFixture[str]) -> None:
    """前端 CLI：`--scope frontend --format packages` 输出受影响包名。"""
    code = test_selection.main(
        (
            "--root",
            str(_REPO_ROOT),
            "--scope",
            "frontend",
            "--changed-file",
            "frontend/packages/core/src/base/x.ts",
            "--format",
            "packages",
        )
    )

    assert code == 0
    output = capsys.readouterr().out.split()
    assert "@bms/core" in output
    assert "@bms/desktop" in output
