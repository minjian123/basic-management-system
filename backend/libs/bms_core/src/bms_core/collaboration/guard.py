"""无声明降级的护栏扫描（详细设计 §5 用例 9 的可执行部分）。

**扫描口径**（只看 `except` 处理器体，避免把「字典取值兜底」这类正常写法误判）：

- `except-pass`：处理器体只有 `pass`（失败被静默吞掉）；
- `except-empty-return`：处理器体直接返回空集合（`[]` / `()` / `{}` / `set()` / `ConcurrentStableList()` 等）；
- `except-or-empty`：处理器体内出现 `x or <空集合>` 兜底。

**用途**：`03_01` 消费方收编后，各消费方不得自写降级——降级一律经 `usage.call_capability()`
按 `CapabilityUsage` 声明执行（有日志、有指标、理由留痕）。本扫描器在测试里对已收编范围断言零命中，
对尚未收编的存量落点登记基线并随收编递减。
"""

import ast
from collections.abc import Iterable
from pathlib import Path

from bms_core.core.concurrent import ConcurrentStableList

__all__ = ["fetch_python_files", "find_undeclared_degradations"]

_EMPTY_COLLECTION_CALLS = frozenset(
    {
        "ConcurrentStableList",
        "ConcurrentStableFrozenList",
        "ConcurrentStableSet",
        "ConcurrentStableFrozenSet",
        "ConcurrentStableDict",
        "ConcurrentStableFrozenDict",
        "dict",
        "frozenset",
        "list",
        "set",
        "tuple",
    }
)


def fetch_python_files(paths: Iterable[str | Path]) -> ConcurrentStableList[Path]:
    """展开扫描目标为 Python 文件清单（目录递归、文件原样）。

    Args:
        paths: 文件或目录路径。

    Returns:
        ConcurrentStableList[Path]: Python 文件（插入序、去重后按路径排序）。
    """
    found: ConcurrentStableList[Path] = ConcurrentStableList()
    seen: ConcurrentStableList[Path] = ConcurrentStableList()
    for raw in paths:
        path = Path(raw)
        candidates = (
            ConcurrentStableList(sorted(path.rglob("*.py"))) if path.is_dir() else ConcurrentStableList((path,))
        )
        for item in candidates:
            if item in seen:
                continue
            seen.add(item)
            found.add(item)
    return found


def find_undeclared_degradations(paths: Iterable[str | Path]) -> ConcurrentStableList[str]:
    """扫描无声明降级写法（`文件:行号:类别`，按文件与行号排序）。

    Args:
        paths: 扫描目标（文件或目录）。

    Returns:
        ConcurrentStableList[str]: 命中清单（空表示无违规）。

    Raises:
        SyntaxError: 目标文件不是合法 Python（护栏自身不吞语法错误）。
    """
    findings: ConcurrentStableList[str] = ConcurrentStableList()
    for path in fetch_python_files(paths):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ExceptHandler):
                continue
            for kind, lineno in _handler_findings(node):
                findings.add(f"{path}:{lineno}:{kind}")
    return ConcurrentStableList(sorted(findings))


def _handler_findings(handler: ast.ExceptHandler) -> ConcurrentStableList[tuple[str, int]]:
    """取单个 `except` 处理器的违规类别。

    Args:
        handler: 异常处理器节点。

    Returns:
        ConcurrentStableList[tuple[str, int]]: `(类别, 行号)` 清单。
    """
    results: ConcurrentStableList[tuple[str, int]] = ConcurrentStableList()
    body: ConcurrentStableList[ast.stmt] = ConcurrentStableList(handler.body)
    if len(body) == 1:
        statement = body[0]
        if isinstance(statement, ast.Pass):
            results.add(("except-pass", statement.lineno))
        elif isinstance(statement, ast.Return) and _is_empty_collection(statement.value):
            results.add(("except-empty-return", statement.lineno))
    for node in ast.walk(handler):
        if isinstance(node, ast.BoolOp) and isinstance(node.op, ast.Or) and _is_empty_collection(node.values[-1]):
            results.add(("except-or-empty", node.lineno))
    return results


def _is_empty_collection(node: ast.AST | None) -> bool:
    """是否为「空集合」表达式（空字面量或空集合构造）。

    Args:
        node: 表达式节点。

    Returns:
        bool: 空集合为 True。
    """
    if isinstance(node, (ast.List, ast.Tuple)):
        return not node.elts
    if isinstance(node, ast.Dict):
        return not node.keys
    if isinstance(node, ast.Call):
        return bool(not node.args and not node.keywords and _call_name(node.func) in _EMPTY_COLLECTION_CALLS)
    return False


def _call_name(func: ast.expr) -> str:
    """取被调用者的末段名字（`ast.Name.id` 或 `ast.Attribute.attr`）。

    Args:
        func: 调用表达式的函数部分。

    Returns:
        str: 名字；无法识别返回空串。
    """
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return ""
