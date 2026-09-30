#!/usr/bin/env python3
"""集合声明静态护栏（bms 基座校验，CI base-integrity 与本地 preflight 调用）。

《后端开发规范》「后端基座体系（强制）」节「集合与排序」：**对外数据契约、值对象与模块类的集合
字段与函数签名一律使用继承 `BaseCollection` 的插入序集合类**（业务面只落 `ConcurrentStable*`），
**禁止裸无序集合、只读 / 可变抽象落点与升序形态**。本脚本以 AST 检查后端 Python 的**类字段注解**、
**函数签名注解**（参数 / 返回）与**函数体局部变量注解**，集合声明必须命中**插入序白名单**，
存量以**基线快照**豁免、**新增违规即失败**。

口径（08-1 交付；**08_02 白名单收紧 + 豁免取消**，2026-09-29）：

- **查**：类字段注解 + 函数签名注解（参数 / 返回）+ 函数体带注解局部变量。
- **判违规**（集合声明必须命中插入序白名单，其余集合形态一律违规）：
  - 裸容器：`dict` / `list` / `set` / `frozenset` 及 typing 别名 `Dict` / `List` / `Set` / `FrozenSet` / `DefaultDict`；
  - 只读 / 可变抽象：`Sequence` / `Mapping` / `AbstractSet` / `Collection` / `MutableSequence` /
    `MutableMapping` / `MutableSet`；
  - 升序形态：`SortedList` / `SortedDict` / `SortedSet` / `ConcurrentSortedList` / `ConcurrentSortedSet` /
    `ConcurrentSortedDict`（基座内部实现，业务与契约不得声明 / 继承）。
- **白名单**（不报）：插入序形态 `ConcurrentStableList` / `ConcurrentStableSet` / `ConcurrentStableDict`
  及后续登记形态。
- **不查**：迭代与调用协议（`Iterable` / `Iterator` / `Generator` / `AsyncIterator` / `Callable`）——
  非集合声明，不承担有序输出。
- **不属约束对象**：集合体系**实现文件**（`core/collections.py` / `core/concurrent.py` /
  `core/sorted_collections.py` / `core/redis_collections.py`）不属本护栏的约束对象——本护栏只约束**业务侧集合声明**
  （对外数据契约、值对象与模块类）；集合体系实现文件是体系自身，其内置容器是内部底座与序列化出口（08_02，2026-09-29）。
- **范围**：`backend/libs/bms_core/src` + `tests`、`backend/services/*/src` + `tests`、`backend/ops`、`scripts/tools`
  （**含测试目录与函数体局部变量**；`ClassVar` 类级常量与 `BaseSettings` 配置字段不再豁免，2026-09-29）。
- **基线**：`deploy/boundaries/bare_collections_baseline.json`（文件 + 规范化行内容指纹 + 容器 + 计数）；
  口径收紧后先 `--update-baseline` 如实吸收，随后按批次递减。

用法::

    python3 scripts/tools/base-check/check-bare-collections.py [bms 仓库根]
    python3 scripts/tools/base-check/check-bare-collections.py . --json
    python3 scripts/tools/base-check/check-bare-collections.py . --report
    python3 scripts/tools/base-check/check-bare-collections.py . --update-baseline
    python3 scripts/tools/base-check/check-bare-collections.py --self-test

退出码：``0`` 通过（或 ``--report``）；``1`` 存在新增违规 / 基线非法 / 扫描异常。

用例：Kiwi **2213**（`--self-test` 自测矩阵；覆盖白名单 / 抽象落点 / 升序形态 / 实现文件不属约束对象 /
迭代协议 / 位置（类字段 / 签名 / 局部变量）/ 测试目录纳入 / 基线语义 / 模式与输出）。
"""

from __future__ import annotations

import ast
import contextlib
import io
import json
import re
import sys
import tempfile
from collections import Counter
from datetime import date
from pathlib import Path
from typing import NamedTuple

SCRIPT_REPO = Path(__file__).resolve().parents[3]
"""本脚本所在 bms 仓库根（按脚本位置定位，自检的临时仓库不影响定位）。"""

ROOT = Path(sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("-") else ".").resolve()

BASELINE_RELATIVE = "deploy/boundaries/bare_collections_baseline.json"
"""基线快照相对路径（与 `deploy/boundaries/data_ownership_exceptions.json` 同目录）。"""

BASELINE_VERSION = 1
"""基线快照格式版本（非该值即拒，fail-fast）。"""

SCAN_TARGETS: tuple[str, ...] = (
    "backend/libs/bms_core/src",
    "backend/libs/bms_core/tests",
    "backend/services",
    "backend/ops",
    "scripts/tools",
)
"""扫描目标（相对仓库根）；`backend/services` 取其下各服务的 `src` 与 `tests`。"""

_EXCLUDED_PARTS = frozenset({"__pycache__", ".venv", "node_modules", ".git"})

SYSTEM_IMPLEMENTATION_FILES: frozenset[str] = frozenset(
    {
        "backend/libs/bms_core/src/bms_core/core/collections.py",
        "backend/libs/bms_core/src/bms_core/core/concurrent.py",
        "backend/libs/bms_core/src/bms_core/core/sorted_collections.py",
        "backend/libs/bms_core/src/bms_core/core/redis_collections.py",
    }
)
"""集合体系实现文件：**不属本护栏的约束对象**（护栏只约束业务侧集合声明；实现文件是体系自身，
其内置容器为内部底座与序列化出口，`Sorted*` / `ConcurrentSorted*` 为体系内部形态）。"""

BARE_CONTAINERS: frozenset[str] = frozenset(
    {"dict", "list", "set", "frozenset", "Dict", "List", "Set", "FrozenSet", "DefaultDict"}
)
"""裸容器：内建可变 / 无序容器与 typing 别名。"""

READONLY_ABSTRACTIONS: frozenset[str] = frozenset(
    {"Sequence", "Mapping", "AbstractSet", "Collection", "MutableSequence", "MutableMapping", "MutableSet"}
)
"""只读 / 可变抽象落点（不再作集合落点）。"""

ASCENDING_FORMS: frozenset[str] = frozenset(
    {"SortedList", "SortedDict", "SortedSet", "ConcurrentSortedList", "ConcurrentSortedSet", "ConcurrentSortedDict"}
)
"""升序形态（基座内部实现，业务与契约不得声明 / 继承）。"""

BANNED_FORMS: frozenset[str] = BARE_CONTAINERS | READONLY_ABSTRACTIONS | ASCENDING_FORMS
"""判违规形态全集（集合声明必须命中插入序白名单）。"""

WHITELIST_FORMS: frozenset[str] = frozenset(
    {"ConcurrentStableList", "ConcurrentStableSet", "ConcurrentStableDict"}
)
"""插入序白名单（业务与契约唯一落点；后续登记形态在此追加）。"""

POSITION_CLASS_FIELD = "class_field"
POSITION_SIGNATURE_PARAM = "signature_param"
POSITION_SIGNATURE_RETURN = "signature_return"
POSITION_LOCAL = "local"

_STRING_CONTAINER = re.compile(r"\b(" + "|".join(sorted(BANNED_FORMS)) + r")\b")
"""字符串前向引用注解中的违规形态名（词边界近似，AST 不解析字符串注解语义）。"""

problems: list[str] = []
"""全部问题（违规 + 扫描异常），main 据此决定退出码。"""

counts: Counter[str] = Counter()
"""分类计数（供 JSON 输出与报告模式）。"""


class Hit(NamedTuple):
    """一处理命中（违规集合声明位置）。"""

    file: str
    line: str
    container: str
    position: str
    base_object: bool


class BaselineError(Exception):
    """基线快照非法（格式 / 版本 / 字段）。"""


def _base_name(node: ast.expr) -> str:
    """取基类名（`Name.id` 或 `Attribute.attr`）。

    Args:
        node: 基类表达式节点。

    Returns:
        str: 基类名（无法识别时返回空串）。
    """
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Subscript):
        return _base_name(node.value)
    return ""


def _annotation_containers(node: ast.expr | None) -> list[str]:
    """递归取注解中出现的违规集合形态名（裸容器 / 只读-可变抽象 / 升序形态）。

    Args:
        node: 注解表达式（可为 None）。

    Returns:
        list[str]: 命中形态名（可能重复，调用方按需去重）。
    """
    if node is None:
        return []
    if isinstance(node, ast.Name):
        return [node.id] if node.id in BANNED_FORMS else []
    if isinstance(node, ast.Attribute):
        return [node.attr] if node.attr in BANNED_FORMS else []
    if isinstance(node, ast.Subscript):
        return [*_annotation_containers(node.value), *_annotation_containers(node.slice)]
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
        return [*_annotation_containers(node.left), *_annotation_containers(node.right)]
    if isinstance(node, (ast.Tuple, ast.List)):
        found: list[str] = []
        for item in node.elts:
            found.extend(_annotation_containers(item))
        return found
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return sorted(set(_STRING_CONTAINER.findall(node.value)))
    return []


def _is_excluded(path: Path, root: Path) -> bool:
    """判断文件是否在排除范围（仅缓存 / 虚拟环境等非源码目录）。"""
    rel = path.relative_to(root)
    return any(part in _EXCLUDED_PARTS for part in rel.parts)


def _iter_target_files(root: Path) -> list[Path]:
    """枚举扫描目标下的 Python 文件（`backend/services` 取其下各服务的 `src` 与 `tests`）。"""
    files: list[Path] = []
    for rel in SCAN_TARGETS:
        base = root / rel
        if not base.is_dir():
            continue
        if rel == "backend/services":
            candidates = [
                child / sub for child in sorted(base.iterdir()) if child.is_dir() for sub in ("src", "tests")
            ]
        else:
            candidates = [base]
        for candidate in candidates:
            if not candidate.is_dir():
                continue
            for path in sorted(candidate.rglob("*.py")):
                if not _is_excluded(path, root):
                    files.append(path)
    return files


def _scan_source(rel: str, source: str) -> list[Hit]:
    """扫描单个源文件，收集违规集合声明命中。

    覆盖位置：**类字段注解** + **函数签名注解**（参数 / 返回）+ **函数体带注解局部变量**。

    Args:
        rel: 相对仓库根的路径（写入命中）。
        source: 源码文本。

    Returns:
        list[Hit]: 命中清单（按行序稳定）。
    """
    tree = ast.parse(source)
    lines = source.splitlines()
    hits: list[Hit] = []

    class_fields: dict[int, bool] = {}
    for cls in ast.walk(tree):
        if not isinstance(cls, ast.ClassDef):
            continue
        base_object = any(_base_name(base) == "BaseObject" for base in cls.bases)
        for stmt in cls.body:
            if isinstance(stmt, ast.AnnAssign):
                class_fields[id(stmt)] = base_object

    def add(node: ast.AST, container: str, position: str, *, base_object: bool = False) -> None:
        """登记一处命中（行内容取声明行、规范化空白）。"""
        lineno = getattr(node, "lineno", 0)
        text = lines[lineno - 1].strip() if 0 < lineno <= len(lines) else ""
        hits.append(Hit(rel, text, container, position, base_object))

    for node in ast.walk(tree):
        if isinstance(node, ast.AnnAssign):
            is_field = id(node) in class_fields
            position = POSITION_CLASS_FIELD if is_field else POSITION_LOCAL
            for container in dict.fromkeys(_annotation_containers(node.annotation)):
                add(node, container, position, base_object=is_field and class_fields[id(node)])
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for container in dict.fromkeys(_annotation_containers(node.returns)):
                add(node.returns or node, container, POSITION_SIGNATURE_RETURN)
            args = (*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs)
            for arg in args:
                if arg.annotation is None:
                    continue
                for container in dict.fromkeys(_annotation_containers(arg.annotation)):
                    add(arg.annotation, container, POSITION_SIGNATURE_PARAM)
    return hits


def collect(root: Path) -> list[Hit]:
    """扫描目标文件，收集违规集合声明命中（扫描异常记入 `problems`）。

    覆盖位置：**类字段注解** + **函数签名注解**（参数 / 返回）+ **函数体带注解局部变量**。
    `ClassVar` 类级常量与 `BaseSettings` 配置字段**不再豁免**（一律纳入扫描）。

    Args:
        root: 仓库根。

    Returns:
        list[Hit]: 命中清单（按文件与行序稳定）。
    """
    hits: list[Hit] = []
    for path in _iter_target_files(root):
        rel = path.relative_to(root).as_posix()
        if rel in SYSTEM_IMPLEMENTATION_FILES:
            continue
        try:
            source = path.read_text(encoding="utf-8")
            file_hits = _scan_source(rel, source)
        except (OSError, SyntaxError, UnicodeDecodeError) as exc:
            problems.append(f"[扫描异常] {rel}：{exc}")
            continue
        hits.extend(file_hits)
    return hits


def _baseline_key(hit: Hit) -> tuple[str, str, str]:
    """基线与比对键（文件 + 规范化行内容 + 容器；不含行号，容行漂移）。"""
    return (hit.file, hit.line, hit.container)


def _read_baseline(path: Path) -> Counter[tuple[str, str, str]]:
    """读取基线快照。

    Args:
        path: 基线文件路径。

    Returns:
        Counter[tuple[str, str, str]]: 基线命中计数（键同 `_baseline_key`）。

    Raises:
        BaselineError: 文件存在但格式 / 版本 / 字段非法。
    """
    if not path.is_file():
        return Counter()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BaselineError(f"基线快照不可解析：{path}（{exc}）") from exc
    if not isinstance(payload, dict) or payload.get("version") != BASELINE_VERSION:
        raise BaselineError(f"基线快照版本非法（须为 {BASELINE_VERSION}）：{path}")
    entries = payload.get("entries")
    if not isinstance(entries, list):
        raise BaselineError(f"基线快照 entries 非法（须为数组）：{path}")
    counter: Counter[tuple[str, str, str]] = Counter()
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise BaselineError(f"基线快照条目非法（第 {index + 1} 条须为对象）：{path}")
        try:
            key = (str(entry["file"]), str(entry["line"]), str(entry["container"]))
            count = int(entry.get("count", 1))
        except (KeyError, TypeError, ValueError) as exc:
            raise BaselineError(f"基线快照条目字段缺失或非法（第 {index + 1} 条）：{path}") from exc
        if count < 1:
            raise BaselineError(f"基线快照条目 count 非法（第 {index + 1} 条须为正整数）：{path}")
        counter[key] += count
    return counter


def write_baseline(path: Path, hits: list[Hit]) -> None:
    """以本次扫描结果重写基线快照（自然完成递减）。

    Args:
        path: 基线文件路径。
        hits: 本次命中清单。
    """
    aggregate: Counter[tuple[str, str, str]] = Counter(_baseline_key(hit) for hit in hits)
    positions: dict[tuple[str, str, str], str] = {}
    for hit in hits:
        positions.setdefault(_baseline_key(hit), hit.position)
    entries = [
        {
            "file": key[0],
            "line": key[1],
            "container": key[2],
            "position": positions[key],
            "count": count,
        }
        for key, count in sorted(aggregate.items())
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"version": BASELINE_VERSION, "generated_at": date.today().isoformat(), "entries": entries}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _summarize(hits: list[Hit]) -> None:
    """填充分类计数（供 JSON 与报告模式）。"""
    counts.clear()
    counts["total"] = len(hits)
    counts["class_field"] = sum(1 for hit in hits if hit.position == POSITION_CLASS_FIELD)
    counts["class_field_base_object"] = sum(
        1 for hit in hits if hit.position == POSITION_CLASS_FIELD and hit.base_object
    )
    counts["signature_param"] = sum(1 for hit in hits if hit.position == POSITION_SIGNATURE_PARAM)
    counts["signature_return"] = sum(1 for hit in hits if hit.position == POSITION_SIGNATURE_RETURN)
    counts["local"] = sum(1 for hit in hits if hit.position == POSITION_LOCAL)


def check(root: Path) -> None:
    """执行护栏：扫描 → 基线比对 → 记入 `problems`。

    Args:
        root: 仓库根。
    """
    hits = collect(root)
    _summarize(hits)
    actual: Counter[tuple[str, str, str]] = Counter(_baseline_key(hit) for hit in hits)
    positions: dict[tuple[str, str, str], str] = {}
    for hit in hits:
        positions.setdefault(_baseline_key(hit), hit.position)
    try:
        baseline = _read_baseline(root / BASELINE_RELATIVE)
    except BaselineError as exc:
        problems.append(f"[基线非法] {exc}")
        return
    added = actual - baseline
    stale = baseline - actual
    counts["baseline_entries"] = sum(baseline.values())
    counts["added"] = sum(added.values())
    counts["stale"] = sum(stale.values())
    for (file, line, container), count in sorted(added.items()):
        problems.append(
            f"[新增] {file}（{positions.get((file, line, container), '?')} / {container} × {count}）：{line}"
        )
    if stale and not added:
        print(
            f"  基线可递减：{sum(stale.values())} 处已修复但仍在基线，"
            f"跑 `--update-baseline` 同步（不影响本次结论）。"
        )


def _report(root: Path, *, as_json: bool) -> None:
    """报告模式：仅统计与清单，恒退出 0。"""
    hits = collect(root)
    _summarize(hits)
    by_area: Counter[str] = Counter()
    by_container: Counter[str] = Counter()
    by_file: Counter[str] = Counter()
    for hit in hits:
        area = hit.file.split("/")[1] if hit.file.startswith("backend/") else hit.file.split("/")[0]
        by_area[area] += 1
        by_container[hit.container] += 1
        by_file[hit.file] += 1
    if as_json:
        payload = {
            "passed": not problems,
            "counts": dict(counts),
            "by_area": dict(sorted(by_area.items())),
            "by_container": dict(sorted(by_container.items())),
            "top_files": dict(by_file.most_common(20)),
            "problems": problems,
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    print(f"[check-bare-collections] 报告：命中 {counts['total']} 处（仅统计，不影响退出码）")
    print(
        f"  位置：类字段 {counts['class_field']}（含 BaseObject {counts['class_field_base_object']}）"
        f" / 签名参数 {counts['signature_param']} / 签名返回 {counts['signature_return']}"
        f" / 局部变量 {counts['local']}"
    )
    print("  容器：" + "、".join(f"{name} {num}" for name, num in sorted(by_container.items(), key=lambda kv: -kv[1])))
    print("  区域：" + "、".join(f"{name} {num}" for name, num in sorted(by_area.items(), key=lambda kv: -kv[1])))
    print("  高频文件 TOP 10：")
    for name, num in by_file.most_common(10):
        print(f"    {num:>4}  {name}")
    for problem in problems:
        print("  " + problem)


def _emit(as_json: bool) -> None:
    """输出检查结果（文本或 JSON）。"""
    if as_json:
        payload = {"passed": not problems, "counts": dict(counts), "problems": problems}
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    if problems:
        print(f"\n[check-bare-collections] 不通过：{len(problems)} 项")
        for problem in problems:
            print("  " + problem)
        return
    print(
        "[check-bare-collections] 通过：集合声明无新增违规（类字段 / 函数签名 / 局部变量）"
        f"（基线内 {counts['baseline_entries']} 处存量）。"
    )


_FIXTURE_FILES: dict[str, str] = {
    "backend/libs/bms_core/src/demo/mod.py": (
        "from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence\n"
        "from typing import AbstractSet, ClassVar\n"
        "\n"
        "class Plain:\n"
        "    tags: list[str] = []\n"
        "    ordered: ConcurrentStableList[str] = ConcurrentStableList()\n"
        "    ascending: ConcurrentSortedList[int] = ConcurrentSortedList()\n"
        "    constant: ClassVar[frozenset[str]] = frozenset()\n"
        "\n"
        "class Model(BaseObject):\n"
        "    payload: dict[str, object] = {}\n"
        "\n"
        "class Demo(BaseSettings):\n"
        "    paths: list[str] = []\n"
        "\n"
        "def f(a: dict[str, int], b: Sequence[str], c: Mapping[str, int], d: AbstractSet[str]) -> set[int]:\n"
        "    return set()\n"
        "\n"
        "def g(items: Iterable[int], stream: Iterator[int], cb: Callable[[int], int]) -> None:\n"
        "    del items, stream, cb\n"
        "\n"
        "def h() -> 'list[int]':\n"
        "    return []\n"
        "\n"
        "def inner() -> None:\n"
        "    local: dict[str, int] = {}\n"
        "    del local\n"
    ),
    "backend/libs/bms_core/src/demo/tests/test_local.py": "class X:\n    bad: list[int] = []\n",
    "backend/libs/bms_core/src/bms_core/core/concurrent.py": "def to_list(self) -> list[int]:\n    return []\n",
    "backend/libs/bms_core/src/bms_core/core/sorted_collections.py": "class S:\n    data: dict[str, int] = {}\n",
    "backend/services/svc/src/svc/mod.py": "class A:\n    data: List[int] = []\n",
    "backend/ops/op.py": "def run(payload: DefaultDict[str, int]) -> None:\n    del payload\n",
    "scripts/tools/thing.py": "def x() -> frozenset[str]:\n    return frozenset()\n",
}


def _self_test() -> int:
    """自测矩阵（临时仓库 fixture）：检出 / 不检出 / 位置 / 排除 / 基线语义（Kiwi 2213）。

    Returns:
        int: 退出码（0 全部通过 / 1 有断言失败）。
    """
    ok = True

    def expect(condition: bool, label: str) -> None:
        nonlocal ok
        if condition:
            print(f"  [自检通过] {label}")
        else:
            ok = False
            print(f"  [自检失败] {label}")

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        for rel, content in _FIXTURE_FILES.items():
            path = root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")

        problems.clear()
        hits = collect(root)
        found = {(hit.file, hit.line, hit.container, hit.position) for hit in hits}
        demo = "backend/libs/bms_core/src/demo/mod.py"
        func_line = "def f(a: dict[str, int], b: Sequence[str], c: Mapping[str, int], d: AbstractSet[str]) -> set[int]:"
        expect((demo, "tags: list[str] = []", "list", "class_field") in found, "命中类字段 list（裸容器）")
        expect(
            (demo, "payload: dict[str, object] = {}", "dict", "class_field") in found,
            "命中 BaseObject 类字段 dict",
        )
        expect((demo, func_line, "dict", "signature_param") in found, "命中签名参数 dict")
        expect((demo, func_line, "set", "signature_return") in found, "命中签名返回 set")
        expect((demo, func_line, "Sequence", "signature_param") in found, "抽象落点 Sequence 报")
        expect((demo, func_line, "Mapping", "signature_param") in found, "抽象落点 Mapping 报")
        expect((demo, func_line, "AbstractSet", "signature_param") in found, "抽象落点 AbstractSet 报")
        ascending_line = "ascending: ConcurrentSortedList[int] = ConcurrentSortedList()"
        expect((demo, ascending_line, "ConcurrentSortedList", "class_field") in found, "升序形态报")
        expect(
            all(hit.container != "ConcurrentStableList" for hit in hits),
            "白名单命中不报（ConcurrentStableList）",
        )
        expect(all(hit.container not in {"Iterable", "Iterator", "Callable"} for hit in hits), "迭代 / 调用协议不报")
        expect(
            (demo, "constant: ClassVar[frozenset[str]] = frozenset()", "frozenset", "class_field") in found,
            "ClassVar 类级常量报（豁免已取消）",
        )
        expect(
            (demo, "paths: list[str] = []", "list", "class_field") in found,
            "BaseSettings 配置字段报（豁免已取消）",
        )
        expect(
            (demo, "local: dict[str, int] = {}", "dict", "local") in found,
            "函数体局部变量报（豁免已取消）",
        )
        expect(
            any(hit.file.endswith("demo/tests/test_local.py") for hit in hits),
            "测试目录纳入扫描",
        )
        expect(
            ("backend/services/svc/src/svc/mod.py", "data: List[int] = []", "List", "class_field") in found,
            "命中 typing 别名 List",
        )
        expect(
            ("backend/ops/op.py", "def run(payload: DefaultDict[str, int]) -> None:", "DefaultDict", "signature_param")
            in found,
            "命中 DefaultDict",
        )
        expect(
            ("scripts/tools/thing.py", "def x() -> frozenset[str]:", "frozenset", "signature_return") in found,
            "命中 frozenset",
        )
        expect((demo, "def h() -> 'list[int]':", "list", "signature_return") in found, "命中字符串前向引用")
        expect(
            all(
                hit.file
                not in {
                    "backend/libs/bms_core/src/bms_core/core/concurrent.py",
                    "backend/libs/bms_core/src/bms_core/core/sorted_collections.py",
                }
                for hit in hits
            ),
            "集合体系实现文件不属约束对象（不报）",
        )

        baseline_path = root / BASELINE_RELATIVE
        check(root)
        expect(bool(problems), "无基线时全部视为新增 → 不通过")

        write_baseline(baseline_path, hits)
        problems.clear()
        check(root)
        expect(not problems, "存量入基线后通过")
        expect(counts["added"] == 0 and counts["stale"] == 0, "基线零漂移")

        extra = root / "backend/ops/extra.py"
        extra.write_text("def bad() -> list[str]:\n    return []\n", encoding="utf-8")
        problems.clear()
        check(root)
        expect(bool(problems), "新增违规被拦截")

        extra.write_text("def good() -> list[str]:\n    return []\n".replace("bad", "good"), encoding="utf-8")
        write_baseline(baseline_path, collect(root))
        problems.clear()
        check(root)
        expect(not problems, "更新基线后再次通过")

        current = len(collect(root))
        problems.clear()
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            _report(root, as_json=True)
        payload = json.loads(buffer.getvalue())
        expect(not problems and payload["counts"]["total"] == current, "报告模式 JSON 结构合法且不产生问题项")

        extra.unlink()
        problems.clear()
        check(root)
        expect(not problems and counts["stale"] > 0, "修复后基线可递减且不改结论")

    return 0 if ok else 1


def main() -> int:
    """入口：执行护栏、报告、更新基线或自检。

    Returns:
        int: 退出码（0 通过 / 1 失败）。
    """
    if "--self-test" in sys.argv:
        return _self_test()
    as_json = "--json" in sys.argv
    if "--update-baseline" in sys.argv:
        hits = collect(ROOT)
        _summarize(hits)
        write_baseline(ROOT / BASELINE_RELATIVE, hits)
        print(f"[check-bare-collections] 基线已更新：{len(hits)} 条 → {BASELINE_RELATIVE}")
        if problems:
            _emit(as_json)
            return 1
        return 0
    if "--report" in sys.argv:
        _report(ROOT, as_json=as_json)
        return 0
    check(ROOT)
    _emit(as_json)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
