"""模块边界护栏：分层依赖方向与跨模块私有引用。

依据《后端开发规范》§3.1「依赖方向」与 §3.2「模块边界与数据所有权」：

- `core/` 不得反向依赖 `api/` / `services/`（横切基座不感知上层）；
- `repositories/` 不得依赖 `services/`（数据访问不承载业务规则）；
- 跨包不得 import 他包私有模块（下划线前缀）——模块内部类与实现不得外泄。

本用例为**静态护栏（AST 扫描，不接数据库 / 不起服务）**：CI `backend-test` 阶段随 pytest 执行，新增越界即失败。
批 2（ORM 关系与 SQL 表前缀扫描）待批 1 稳定后补齐，见《后端开发规范》§3.2「执行护栏」。
"""

import ast
from collections.abc import Iterator
from functools import lru_cache
from pathlib import Path

import pytest

_APP_DIR = Path(__file__).resolve().parents[2] / "app"

# 分层反向依赖黑名单：源包 → 禁止依赖的目标包
_LAYER_RULES: dict[str, frozenset[str]] = {
    "core": frozenset({"api", "services"}),
    "repositories": frozenset({"services"}),
}

_MIN_SOURCE_FILES = 100


def _package_of(rel_path: str) -> str:
    """返回源文件所属包（`app/<pkg>/...` 的第二段）。

    Args:
        rel_path: 相对仓库根的源文件路径（`app/...`）。

    Returns:
        str: 包名；`app/` 根下文件返回 `app`。
    """
    parts = rel_path.split("/")
    return parts[1] if len(parts) > 2 else "app"


def _iter_app_imports(path: Path) -> Iterator[tuple[int, str]]:
    """解析文件并产出全部 `app.*` 导入。

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
            if module == "app" or module.startswith("app."):
                yield node.lineno, module


@lru_cache(maxsize=1)
def _scan() -> tuple[tuple[str, ...], tuple[str, ...], int]:
    """扫描 `app/` 下全部源文件，收集越界导入。

    Returns:
        tuple[tuple[str, ...], tuple[str, ...], int]: 分层反向依赖、跨包私有引用、已扫描文件数。
    """
    reverse: list[str] = []
    private: list[str] = []
    scanned = 0
    for path in sorted(_APP_DIR.rglob("*.py")):
        scanned += 1
        rel = path.relative_to(_APP_DIR.parent).as_posix()
        source = _package_of(rel)
        for lineno, module in _iter_app_imports(path):
            parts = module.split(".")
            target = parts[1] if len(parts) > 1 else "app"
            detail = f"{rel}:{lineno} import {module}"
            if target in _LAYER_RULES.get(source, frozenset()):
                reverse.append(f"[{source}→{target}] {detail}")
            if target != source and any(part.startswith("_") for part in parts[1:]):
                private.append(f"[{source}→{target}] {detail}")
    return tuple(reverse), tuple(private), scanned


@pytest.mark.kiwi_id(688)
def test_scan_covers_app_sources() -> None:
    """护栏有效性自检：扫描样本须覆盖 `app/` 下足量源文件（防路径错误导致假通过）。"""
    _, _, scanned = _scan()
    assert scanned >= _MIN_SOURCE_FILES, f"扫描文件数异常（{scanned}），护栏可能未覆盖真实代码"


@pytest.mark.kiwi_id(688)
def test_no_reverse_layer_dependency() -> None:
    """分层依赖方向：`core/` 不依赖 `api/` / `services/`，`repositories/` 不依赖 `services/`。"""
    reverse, _, _ = _scan()
    assert not reverse, "禁止反向依赖（《后端开发规范》§3.1「依赖方向」）；违规：\n" + "\n".join(reverse)


@pytest.mark.kiwi_id(688)
def test_no_cross_package_private_import() -> None:
    """跨包不得 import 他包私有模块（下划线前缀即模块内部实现）。"""
    _, private, _ = _scan()
    assert not private, "禁止跨模块引用他模块私有实现（《后端开发规范》§3.2）；违规：\n" + "\n".join(private)
