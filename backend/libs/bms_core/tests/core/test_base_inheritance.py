"""基类继承护栏：`app/` 下所有自定义类都必须继承基类。

依据《后端开发规范》第 3.1 节「必须继承（覆盖一切自定义类，强制）」与「异常类必须继承异常基类」：

- 无基类（或仅继承 `object`）→ 失败；
- 仅继承被禁内建基类（`Exception` / `RuntimeError` / `ValueError` 等）→ 失败（异常类须继承 `BizError` 与段位基）；
- 例外：L0 根基类 `BaseObject` 本身（无父类）。

本用例为**静态护栏（不接数据库 / 不起服务）**：CI `backend-test` 阶段随 pytest 执行，新增违规类即失败。
"""

import ast
from collections.abc import Iterator
from pathlib import Path

from bms_core.core.base import BaseObject

_BACKEND = Path(__file__).resolve().parents[4]
_PACKAGE_DIRS = [
    _BACKEND / "libs" / "bms_core" / "src" / "bms_core",
    *sorted(p for p in (_BACKEND / "services").glob("*/src/*") if p.is_dir()),
]
_ROOT_FILE = _PACKAGE_DIRS[0] / "core" / "base.py"
_ROOT_CLASS = "BaseObject"
_FORBIDDEN_BUILTINS = frozenset(
    {
        "object",
        "Exception",
        "RuntimeError",
        "ValueError",
        "TypeError",
        "KeyError",
        "OSError",
        "dict",
        "list",
        "set",
        "tuple",
        "str",
        "int",
        "float",
    }
)


def _iter_class_defs(path: Path) -> Iterator[ast.ClassDef]:
    """解析文件并产出全部类定义节点。

    Args:
        path: Python 源文件路径。

    Yields:
        ast.ClassDef: 类定义节点。
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            yield node


def test_all_app_classes_inherit_a_base() -> None:
    """工作区各包下所有类均须继承基类（无基类 / 仅内建基类即失败）。"""
    offenders: list[str] = []
    for package_dir in _PACKAGE_DIRS:
        for path in sorted(package_dir.rglob("*.py")):
            for node in _iter_class_defs(path):
                if path == _ROOT_FILE and node.name == _ROOT_CLASS:
                    continue  # 根基类本身无父类
                bases = [ast.unparse(base) for base in node.bases]
                rel = path.relative_to(_BACKEND)
                if not bases or set(bases) <= {"object"}:
                    offenders.append(f"{rel}:{node.lineno} {node.name} 无基类")
                elif all(base in _FORBIDDEN_BUILTINS for base in bases):
                    offenders.append(f"{rel}:{node.lineno} {node.name} 仅继承内建基类 {bases}")
    assert not offenders, "所有自定义类必须继承基类（《后端开发规范》§3.1）；违规：\n" + "\n".join(offenders)


def test_guard_detects_offenders(tmp_path: Path) -> None:
    """护栏自检：无基类的类与仅内建基类的类应被识别为违规。"""
    assert issubclass(BaseObject, object)
    bad = tmp_path / "bad.py"
    bad.write_text(
        "class NoBase:\n    pass\n\nclass BuiltinOnly(Exception):\n    pass\n",
        encoding="utf-8",
    )
    offenders: list[str] = []
    for node in _iter_class_defs(bad):
        bases = [ast.unparse(base) for base in node.bases]
        if not bases or set(bases) <= {"object"} or all(base in _FORBIDDEN_BUILTINS for base in bases):
            offenders.append(node.name)
    assert offenders == ["NoBase", "BuiltinOnly"]
