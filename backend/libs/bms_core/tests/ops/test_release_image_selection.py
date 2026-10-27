"""部署侧按 `RUN_IMAGE` 声明选运行镜像用例（Kiwi 2345）：`scripts/tools/deploy/release.py`。

覆盖：`_run_image_of` 读取脚本声明（`ast` 静态读取）、`*` 回落 platform、`ci` 拒绝、
未声明 / 非法值报错；`ops` 全部脚本声明完整性与取值合法性；镜像包集合与 Dockerfile 一致性。

`release.py` 是部署侧脚本（只依赖标准库，不在 pyright 的 `extraPaths`），故按路径动态加载，
避免类型检查出现无法解析的导入。
"""

import ast
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any, cast

import pytest

from bms_core.core.concurrent import ConcurrentStableList

_REPO_ROOT = Path(__file__).resolve().parents[5]
"""仓库根（`backend/libs/bms_core/tests/ops/` 上溯 5 级）。"""

_DEPLOY_DIR = _REPO_ROOT / "scripts" / "tools" / "deploy"
_VALID_VALUES = ("platform", "tenant", "txn", "ci", "*")


def _load_release() -> ModuleType:
    """按路径加载部署 CLI 模块（不依赖 `sys.path` 注入）。

    Returns:
        ModuleType: `release` 模块。
    """
    path = _DEPLOY_DIR / "release.py"
    spec = importlib.util.spec_from_file_location("release_under_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_RELEASE = _load_release()


def _run_image_of(module: str) -> str:
    """调用被测模块的 `_run_image_of`（显式类型，避免 pyright 未知成员）。

    Args:
        module: 模块名（`ops.seed_module`）。

    Returns:
        str: 运行镜像标识。
    """
    holder: Any = _RELEASE
    func = holder._run_image_of
    assert callable(func)
    return cast("str", func(module))


def _declared(module: str) -> str | None:
    """读取 ops 脚本的 RUN_IMAGE 声明（测试侧独立解析，避免与被测实现同源）。

    Args:
        module: 模块名（`ops.seed_module`）。

    Returns:
        str | None: 声明值；未声明返回 None。
    """
    path = _REPO_ROOT / "backend" / "ops" / f"{module.split('.', 1)[1]}.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "RUN_IMAGE" for target in node.targets
        ):
            value = node.value
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                return value.value
            return None
    return None


@pytest.mark.kiwi_id(2345)
def test_all_ops_scripts_declare_valid_run_image() -> None:
    """全部 `ops` 脚本都声明 `RUN_IMAGE` 且取值合法（`platform` / `tenant` / `txn` / `ci` / `*`）。"""
    ops_dir = _REPO_ROOT / "backend" / "ops"
    scripts = ConcurrentStableList(p.stem for p in sorted(ops_dir.glob("*.py")) if p.name != "__init__.py")
    assert len(scripts) == 33
    for script in scripts:
        declared = _declared(f"ops.{script}")
        assert declared is not None, f"{script} 未声明 RUN_IMAGE"
        assert declared in _VALID_VALUES, f"{script} 的 RUN_IMAGE 非法：{declared!r}"


@pytest.mark.kiwi_id(2345)
def test_run_image_of_reads_declaration_and_falls_back_for_star() -> None:
    """`*` 回落 platform；`platform` / `tenant` / `txn` 原样返回（与历史部署镜像等价）。"""
    assert _declared("ops.seed_module") == "*"
    assert _run_image_of("ops.seed_module") == "platform"
    assert _run_image_of("ops.seed_tables") == "platform"
    assert _declared("ops.txn_recovery") == "txn"
    assert _run_image_of("ops.txn_recovery") == "txn"
    assert _declared("ops.bootstrap_platform") == "tenant"
    assert _run_image_of("ops.bootstrap_platform") == "tenant"


@pytest.mark.kiwi_id(2345)
def test_run_image_of_rejects_ci_and_unknown() -> None:
    """声明 `ci`（无部署镜像）与非法值均报错；非 `ops` 模块名同样报错。"""
    assert _declared("ops.check_modules") == "ci"
    with pytest.raises(RuntimeError, match="无部署镜像可选"):
        _run_image_of("ops.check_modules")
    with pytest.raises(RuntimeError, match="仅支持 ops 脚本"):
        _run_image_of("bms_core.tenant.provisioning")
    with pytest.raises(RuntimeError, match="ops 脚本不存在"):
        _run_image_of("ops.ghost_script")


@pytest.mark.kiwi_id(2345)
def test_run_image_of_rejects_missing_or_illegal_declaration(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """脚本未声明 `RUN_IMAGE` 或声明非字符串时显式报错（指出脚本名）。"""
    ops_dir = tmp_path / "backend" / "ops"
    ops_dir.mkdir(parents=True)
    holder: Any = _RELEASE
    monkeypatch.setattr(holder, "REPO_ROOT", tmp_path)

    (ops_dir / "no_declare.py").write_text("import bms_core\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="未声明 RUN_IMAGE"):
        _run_image_of("ops.no_declare")

    (ops_dir / "illegal.py").write_text('RUN_IMAGE = "ghost"\n', encoding="utf-8")
    with pytest.raises(RuntimeError, match="声明非法"):
        _run_image_of("ops.illegal")

    (ops_dir / "not_str.py").write_text("RUN_IMAGE = 1\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="未声明 RUN_IMAGE"):
        _run_image_of("ops.not_str")


@pytest.mark.kiwi_id(2345)
def test_bootstrap_uses_declared_images() -> None:
    """`cmd_bootstrap` 的种子段按声明取镜像（源码断言：不再有硬编码挑镜像注释 / 字面量镜像）。"""
    source = (_DEPLOY_DIR / "release.py").read_text(encoding="utf-8")
    assert "_run_image_of(" in source
    assert "种子按「服务包 / 表归属」选运行镜像" not in source
    for module in ("ops.seed_module", "ops.seed_tables", "ops.seed_tenant", "ops.provision_tenant"):
        assert f'_run_image_of("{module}")' in source, f"bootstrap 未按声明取 {module} 的运行镜像"


@pytest.mark.kiwi_id(2345)
def test_guard_image_packages_match_dockerfile() -> None:
    """护栏的镜像包集合与 `backend/Dockerfile` 的 COPY 面一致（跑真实护栏，断言 0 违规）。"""
    guard = _REPO_ROOT / "scripts" / "tools" / "base_check" / "check_service_boundaries.py"
    result = subprocess.run(
        [sys.executable, str(guard), str(_REPO_ROOT), "--json"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    assert result.stdout.strip(), result.stderr
    payload = json.loads(result.stdout)
    drift = [item for item in payload["problems"] if "镜像包集合" in item]
    assert drift == [], drift
    assert payload["counts"]["ops_image_packages_drift"] == 0

    dockerfile = (_REPO_ROOT / "backend" / "Dockerfile").read_text(encoding="utf-8")
    assert "COPY libs/bms_core/src" in dockerfile
    assert "COPY services/${SERVICE}/src" in dockerfile
    assert "COPY ops" in dockerfile
