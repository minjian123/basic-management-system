"""模块边界护栏：分层依赖方向与跨模块私有引用（工作区形态）。

依据《后端开发规范》§3.1「依赖方向」与 §3.2「模块边界与数据所有权」：

- 共享基座库 `bms_core` 不得反向依赖任何服务（横切基座不感知服务）；
- 各服务不得互相依赖（服务之间只经公开契约或事件）；
- 服务内分层单向：`api → services → repositories → models / schemas`，`models / schemas` 不得反向；
- `bms_core` 的 `core/` 不得反向依赖 `api/` / `services/`，`repositories/` 不得依赖 `services/`；
- 跨包不得 import 他包私有模块（下划线前缀）——模块内部类与实现不得外泄。

本用例为**静态护栏（AST 扫描，不接数据库 / 不起服务）**：CI `backend-test` 阶段随 pytest 执行，新增越界即失败。
脚本版同口径护栏（供 CI base-integrity 层无 venv 运行）见 `scripts/tools/base-check/check-service-boundaries.py`。
"""

import ast
from collections.abc import Iterator
from functools import lru_cache
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[4]
"""后端工程根（`backend/`）。"""


def _discover() -> dict[str, Path]:
    """发现工作区包（`libs/*` 共享库 + `services/*` 服务）。

    Returns:
        dict[str, Path]: 包名 → 包根目录。
    """
    packages: dict[str, Path] = {}
    for kind in ("libs", "services"):
        base = _ROOT / kind
        if not base.is_dir():
            continue
        for project in sorted(base.iterdir()):
            src = project / "src"
            if not src.is_dir():
                continue
            for package in sorted(src.iterdir()):
                if package.is_dir() and (package / "__init__.py").is_file():
                    packages[package.name] = package
    return packages


_PACKAGE_ROOTS: dict[str, Path] = _discover()
"""工作区包：`{包名: 包根}`（含共享库与全部服务）。"""

_SHARED = "bms_core"
"""共享基座库包名（其余为服务包）。"""

_SHARED_LAYER_RULES: dict[str, frozenset[str]] = {
    "core": frozenset({"api", "services"}),
    "repositories": frozenset({"services"}),
}
_SERVICE_LAYER_RULES: dict[str, frozenset[str]] = {
    "services": frozenset({"api"}),
    "repositories": frozenset({"api", "services"}),
    "models": frozenset({"api", "services", "repositories"}),
    "schemas": frozenset({"api", "services", "repositories"}),
}

_MIN_SOURCE_FILES = 100


def _package_of(package: str, path: Path) -> str:
    """返回源文件所属子包（`<包>/<子包>/...` 的第二段）。

    Args:
        package: 顶层包名。
        path: 源文件路径。

    Returns:
        str: 子包名；包根下文件返回包名。
    """
    rel = path.relative_to(_PACKAGE_ROOTS[package]).as_posix()
    parts = rel.split("/")
    return parts[0] if len(parts) > 1 else package


def _iter_imports(path: Path) -> Iterator[tuple[int, str]]:
    """解析文件并产出全部受管包导入（工作区包）。

    Args:
        path: Python 源文件路径。

    Yields:
        tuple[int, str]: 行号与导入的模块名。
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Import | ast.ImportFrom):
            continue
        if isinstance(node, ast.Import):
            modules = [alias.name for alias in node.names]
        else:
            modules = [node.module] if node.module else []
        for module in modules:
            if module.split(".")[0] in _PACKAGE_ROOTS:
                yield node.lineno, module


@lru_cache(maxsize=1)
def _scan() -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...], int]:
    """扫描全部工作区包源文件，收集越界导入。

    Returns:
        tuple: （跨包反向依赖、分层反向依赖、跨包私有引用、已扫描文件数）。
    """
    cross: list[str] = []
    reverse: list[str] = []
    private: list[str] = []
    scanned = 0
    for package, root in _PACKAGE_ROOTS.items():
        shared = package == _SHARED
        layer_rules = _SHARED_LAYER_RULES if shared else _SERVICE_LAYER_RULES
        for path in sorted(root.rglob("*.py")):
            scanned += 1
            rel = path.relative_to(_ROOT).as_posix()
            source = _package_of(package, path)
            for lineno, module in _iter_imports(path):
                top = module.split(".")[0]
                parts = module.split(".")
                detail = f"{rel}:{lineno} import {module}"
                target_shared = top == _SHARED
                if shared and not target_shared:
                    cross.append(f"[{package}→{top}] {detail}")
                if not shared and top != package and not target_shared:
                    cross.append(f"[服务互相依赖 {package}→{top}] {detail}")
                target = parts[1] if len(parts) > 1 else package
                if top == package and target in layer_rules.get(source, frozenset()):
                    reverse.append(f"[{source}→{target}] {detail}")
                if top != package and any(part.startswith("_") for part in parts[1:]):
                    private.append(f"[{package}→{top}] {detail}")
                if top == package and target != source and any(part.startswith("_") for part in parts[1:]):
                    private.append(f"[{source}→{target}] {detail}")
    return tuple(cross), tuple(reverse), tuple(private), scanned


@pytest.mark.kiwi_id(688)
def test_scan_covers_sources() -> None:
    """护栏有效性自检：扫描样本须覆盖足量源文件（防路径错误导致假通过）。"""
    *_, scanned = _scan()
    assert scanned >= _MIN_SOURCE_FILES, f"扫描文件数异常（{scanned}），护栏可能未覆盖真实代码"


@pytest.mark.kiwi_id(688)
def test_shared_library_has_no_service_dependency() -> None:
    """共享基座库不得依赖任何服务（`bms_core` 不感知服务包）。"""
    cross, _, _, _ = _scan()
    assert not cross, "禁止共享库反向依赖服务 / 服务互相依赖（《微服务演进规划》S1）；违规：\n" + "\n".join(cross)


@pytest.mark.kiwi_id(688)
def test_no_reverse_layer_dependency() -> None:
    """分层依赖方向：各包内不得反向依赖上层。"""
    _, reverse, _, _ = _scan()
    assert not reverse, "禁止反向依赖（《后端开发规范》§3.1「依赖方向」）；违规：\n" + "\n".join(reverse)


@pytest.mark.kiwi_id(688)
def test_no_cross_package_private_import() -> None:
    """跨包不得 import 他包私有模块（下划线前缀即模块内部实现）。"""
    _, _, private, _ = _scan()
    assert not private, "禁止跨模块引用他模块私有实现（《后端开发规范》§3.2）；违规：\n" + "\n".join(private)
