"""并行执行与重复步骤消除护栏用例（Kiwi 2318）。

锁定 `13_02` 详细设计（`bms文档/项目/02_后端基座与服务化地基/任务/13_测试执行粒度与工程效能/
13_测试执行粒度与工程效能_02_并行执行与重复步骤消除/设计/01_详细设计_02_并行执行与重复步骤消除.md`）：

- **并行开关**：`--jobs auto|N|off` 单一解析来源，预检与执行器同口径；
- **worker 库隔离**：xdist 下按 worker 注入独立 `sqlite_dir`（串行沿配置原值）；
- **自测按需**：7 个 `--self-test` 按「脚本自身 + 依赖前缀」判定，`--fast` / `--full` 全跑；
- **预算对齐**：定向 300s / 420s、全量 900s / 1800s；
- **CI 重复面**：`service-test` 依 `--format changed-services` 判定，无直接变更则跳过测试。
"""

import contextlib
import importlib.util
import os
import sys
from pathlib import Path
from typing import Any, cast

import pytest

from bms_core.testing import fixtures, plugin

_REPO_ROOT = Path(__file__).resolve().parents[5]
_PREFLIGHT_DIR = _REPO_ROOT / "scripts" / "tools" / "preflight"
if str(_PREFLIGHT_DIR) not in sys.path:
    sys.path.insert(0, str(_PREFLIGHT_DIR))


def _load_script(name: str, path: Path) -> Any:
    """按路径加载预检脚本模块（文件名可能带连字符，不能直接 `import`）。

    Args:
        name: 注册到 `sys.modules` 的模块名（与预检脚本内部 `import` 名一致）。
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
parallel_jobs: Any = _load_script("parallel_jobs", _PREFLIGHT_DIR / "parallel_jobs.py")
_PREFLIGHT: Any = _load_script("preflight_parallel_guard", _PREFLIGHT_DIR / "check-preflight.py")


def _enter_isolate_settings(monkeypatch: pytest.MonkeyPatch) -> Any:
    """进入公共隔离夹具（取 `__wrapped__` 直接驱动生成器）。

    Args:
        monkeypatch: pytest monkeypatch 夹具。

    Returns:
        Any: 夹具生成器（用完需 `next` 一次触发收尾）。
    """
    wrapped: Any = cast("Any", fixtures.isolate_settings).__wrapped__
    generator: Any = wrapped(monkeypatch)
    next(generator)
    return generator


def _leave(generator: Any) -> None:
    """触发夹具收尾（忽略 StopIteration）。

    Args:
        generator: 夹具生成器。
    """
    with contextlib.suppress(StopIteration):
        next(generator)


# ===== A 并行开关 =====


@pytest.mark.kiwi_id(2318)
def test_jobs_args_auto_and_numeric() -> None:
    """`auto` ⇒ `-n auto`；正整数 ⇒ 固定并发。"""
    assert parallel_jobs.jobs_args("auto") == ("-n", "auto")
    assert parallel_jobs.jobs_args("  AUTO ") == ("-n", "auto")
    assert parallel_jobs.jobs_args("4") == ("-n", "4")
    assert parallel_jobs.describe("auto") == "并行 -n auto"


@pytest.mark.kiwi_id(2318)
def test_jobs_args_off() -> None:
    """`off` / `none` / `0` / 空串 ⇒ 串行（不追加参数）。"""
    for value in ("off", "OFF", "none", "0", "", "  "):
        assert parallel_jobs.jobs_args(value) == ()
    assert parallel_jobs.describe("off") == "串行（--jobs off）"


@pytest.mark.kiwi_id(2318)
def test_jobs_args_invalid() -> None:
    """非法取值报错并提示合法取值（不静默按 auto 处理）。"""
    for value in ("-1", "auto2", "1.5", "many"):
        with pytest.raises(ValueError, match="--jobs 取值非法"):
            parallel_jobs.jobs_args(value)


@pytest.mark.kiwi_id(2318)
def test_preflight_wires_jobs_to_all_pytest_calls() -> None:
    """预检把 `--jobs` 接到定向执行器与全量档两条 pytest 调用（防漏接）。"""
    source = (_PREFLIGHT_DIR / "check-preflight.py").read_text(encoding="utf-8")
    assert '"--jobs",\n            jobs,' in source
    assert "*jobs, *cov_args" in source
    assert 'ConcurrentStableList(["uv", "run", "pytest", "-q", *jobs])' in source
    assert parallel_jobs.DEFAULT_JOBS == "auto"


# ===== B worker 级 SQLite 库隔离 =====


@pytest.mark.kiwi_id(2318)
def test_worker_sqlite_dir_serial_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    """串行（无 `PYTEST_XDIST_WORKER`）返空串 ⇒ 沿配置原值。"""
    monkeypatch.delenv("PYTEST_XDIST_WORKER", raising=False)
    assert fixtures.worker_sqlite_dir() == ""


@pytest.mark.kiwi_id(2318)
def test_worker_sqlite_dir_worker(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """xdist worker ⇒ `<basetemp>/sqlite-<worker>` 目录存在且稳定。"""
    monkeypatch.setenv("PYTEST_XDIST_WORKER", "gw3")
    fixtures.configure_sqlite_basetemp(str(tmp_path))
    try:
        directory = fixtures.worker_sqlite_dir()
        assert directory == str(tmp_path / "sqlite-gw3")
        assert Path(directory).is_dir()
        assert fixtures.worker_sqlite_dir() == directory
    finally:
        fixtures.configure_sqlite_basetemp("")


@pytest.mark.kiwi_id(2318)
def test_worker_sqlite_dir_without_basetemp(monkeypatch: pytest.MonkeyPatch) -> None:
    """无 basetemp 时落系统临时目录（兜底路径仍按 worker 分区）。"""
    monkeypatch.setenv("PYTEST_XDIST_WORKER", "gw9")
    fixtures.configure_sqlite_basetemp("")
    directory = Path(fixtures.worker_sqlite_dir())
    assert directory.name == "sqlite-gw9"
    assert directory.parent.name == "bms-pytest-sqlite"
    assert directory.is_dir()


@pytest.mark.kiwi_id(2318)
def test_isolate_settings_injects_sqlite_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """xdist 下 `isolate_settings` 注入 worker 专属 `BMS_DATABASE__SQLITE_DIR`。"""
    monkeypatch.setenv("PYTEST_XDIST_WORKER", "gw1")
    fixtures.configure_sqlite_basetemp(str(tmp_path))
    generator = _enter_isolate_settings(monkeypatch)
    try:
        assert os.environ["BMS_DATABASE__SQLITE_DIR"] == str(tmp_path / "sqlite-gw1")
    finally:
        _leave(generator)
        fixtures.configure_sqlite_basetemp("")


@pytest.mark.kiwi_id(2318)
def test_isolate_settings_serial_keeps_configured_dir(monkeypatch: pytest.MonkeyPatch) -> None:
    """串行不注入（且既有「清 BMS_ 环境变量」行为不变）。"""
    monkeypatch.delenv("PYTEST_XDIST_WORKER", raising=False)
    generator = _enter_isolate_settings(monkeypatch)
    try:
        assert "BMS_DATABASE__SQLITE_DIR" not in os.environ
    finally:
        _leave(generator)


@pytest.mark.kiwi_id(2318)
def test_plugin_configure_passes_basetemp(tmp_path: Path) -> None:
    """`pytest_configure` 把 basetemp 交给基座（xdist worker 的 popen-gwN 目录）。"""

    class _Option:
        basetemp = str(tmp_path)

    class _Config:
        option = _Option()

    try:
        plugin.pytest_configure(cast("pytest.Config", _Config()))
        assert str(tmp_path) == fixtures._sqlite_basetemp  # pyright: ignore[reportPrivateUsage]
    finally:
        fixtures.configure_sqlite_basetemp("")


# ===== C 自测按需 =====


@pytest.mark.kiwi_id(2318)
def test_self_test_selected_by_script() -> None:
    """变更脚本自身 ⇒ 该自测执行。"""
    entry = _PREFLIGHT._SELF_TESTS[0]  # pyright: ignore[reportPrivateUsage]
    changes = test_selection.ConcurrentStableList([entry.script])
    assert _PREFLIGHT._self_test_selected(entry, changes) is True  # pyright: ignore[reportPrivateUsage]


@pytest.mark.kiwi_id(2318)
def test_self_test_selected_by_dependency() -> None:
    """改基座 ⇒ 依赖基座的 5 项执行、纯标准库两项不执行。"""
    changes = test_selection.ConcurrentStableList(["backend/libs/bms_core/src/bms_core/core/concurrent.py"])
    selected = [
        entry.label
        for entry in _PREFLIGHT._SELF_TESTS  # pyright: ignore[reportPrivateUsage]
        if _PREFLIGHT._self_test_selected(entry, changes)  # pyright: ignore[reportPrivateUsage]
    ]
    assert len(selected) == 5
    assert not any("check-system-fields" in label or "check-env-example" in label for label in selected)


@pytest.mark.kiwi_id(2318)
def test_self_test_skipped_when_unrelated() -> None:
    """纯文档 / 前端变更 ⇒ 全部不选（预检逐条打印跳过）。"""
    changes = test_selection.ConcurrentStableList(["bms文档/规范/AI开发规范.md", "frontend/apps/portal/src/main.ts"])
    assert not any(
        _PREFLIGHT._self_test_selected(entry, changes)  # pyright: ignore[reportPrivateUsage]
        for entry in _PREFLIGHT._SELF_TESTS  # pyright: ignore[reportPrivateUsage]
    )


@pytest.mark.kiwi_id(2318)
def test_self_test_registry_complete() -> None:
    """自测登记 7 项、均含脚本自身依赖，且 `--fast` / `--full` 保留全跑口径。"""
    entries = _PREFLIGHT._SELF_TESTS  # pyright: ignore[reportPrivateUsage]
    assert len(entries) == 7
    assert all(entry.script in entry.deps for entry in entries)
    source = (_PREFLIGHT_DIR / "check-preflight.py").read_text(encoding="utf-8")
    assert "force_all=fast or full" in source
    assert "跳过（变更未触及" in source


# ===== D 预算护栏 =====


@pytest.mark.kiwi_id(2318)
def test_budget_defaults_calibrated() -> None:
    """预算按实测重标定：定向 300/420、全量 900/1800。"""
    assert _PREFLIGHT._DEFAULT_SCOPED_BUDGET == (300.0, 420.0)  # pyright: ignore[reportPrivateUsage]
    assert _PREFLIGHT._DEFAULT_FULL_BUDGET == (900.0, 1800.0)  # pyright: ignore[reportPrivateUsage]


@pytest.mark.kiwi_id(2318)
def test_budget_zero_exhausts() -> None:
    """零预算即判耗尽（既有护栏语义保留）。"""
    guard = _PREFLIGHT._Budget(step_seconds=0.0, total_seconds=0.0)  # pyright: ignore[reportPrivateUsage]
    assert guard.remaining() <= 0


# ===== E CI 重复面 =====


@pytest.mark.kiwi_id(2318)
def test_changed_services_direct_only() -> None:
    """只认直接命中的服务：`uv.lock` / `libs` ⇒ 空；`services/txn/**` ⇒ `txn`。"""
    shared = test_selection.ConcurrentStableList(["backend/uv.lock", "backend/libs/bms_core/src/bms_core/core/x.py"])
    assert test_selection.changed_services(shared) == ()
    direct = test_selection.ConcurrentStableList(
        ["backend/services/txn/src/bms_txn/services/recovery.py", "backend/services/txn/tests/test_a.py"]
    )
    assert test_selection.changed_services(direct) == ("txn",)
    mixed = test_selection.ConcurrentStableList(["backend/services/identity/tests/test_a.py", "backend/uv.lock"])
    assert test_selection.changed_services(mixed) == ("identity",)


@pytest.mark.kiwi_id(2318)
def test_service_template_uses_changed_services() -> None:
    """服务子流水线按 `changed-services` 判定并在无直接变更时跳过测试。"""
    template = (_REPO_ROOT / "deploy" / "ci" / "templates" / "backend-service.yml").read_text(encoding="utf-8")
    assert "--format changed-services" in template
    assert "无直接变更" in template and "跳过测试" in template
    assert "保守执行本服务测试" in template


@pytest.mark.kiwi_id(2318)
def test_backend_test_passes_jobs() -> None:
    """CI `backend-test` 并行档与本地同口径（显式 `--jobs auto`）。"""
    ci = (_REPO_ROOT / ".gitlab-ci.yml").read_text(encoding="utf-8")
    assert "--jobs auto" in ci


# ===== F 覆盖率目标排除（插件入口） =====


@pytest.mark.kiwi_id(2318)
def test_plugin_entry_excluded_from_coverage() -> None:
    """覆盖率目标排除 pytest 插件入口（探针启动前加载，行执行不可观测），并打印原因。"""
    runner = _load_script("run_selected_guard", _PREFLIGHT_DIR / "run-selected.py")
    assert runner._COVERAGE_EXCLUDED_MODULES == ("bms_core.testing.plugin",)  # pyright: ignore[reportPrivateUsage]
    source = (_PREFLIGHT_DIR / "run-selected.py").read_text(encoding="utf-8")
    assert "行执行不可观测" in source
