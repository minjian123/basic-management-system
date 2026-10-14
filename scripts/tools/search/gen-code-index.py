#!/usr/bin/env python3
"""代码落点索引进结构生成器（v1）。

按「模块 / 服务 → 目录 → 关键文件 → 职责」登记 bms 前后端代码的落点，
与《前端基类清单》《后端基类清单》的关系：**只做导航**——
不复制继承链、父基类、口径结论（那些的唯一权威仍是两份清单）。

结构自动扫描 + 静态提取（后端 docstring / 前端头部注释 / 包 __init__ 导出），
不调用 LLM：代码落点以「目录 + 职责一句话」为主，可由源码头部注释直接给出；
真正需要的语义归纳（如「这个能力域通常用来干什么」）由人工或后续 LLM 补。

用法：
    python3 gen-code-index.py                         # 输出到 stdout
    python3 gen-code-index.py -o <输出.md>             # 写入文件
    python3 gen-code-index.py --json <输出.json>       # 同时产出结构 JSON
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from collections.abc import Mapping
from pathlib import Path

# bms_core 源码根：集合声明统一落插入序集合类（ConcurrentStable*，见裸集合护栏口径）。
_ROOT = Path(__file__).resolve().parents[3]
_SRC_ROOT = _ROOT / "backend" / "libs" / "bms_core" / "src"
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))

from bms_core.core.concurrent import (
    ConcurrentStableDict,
    ConcurrentStableList,
)

# 后端：核心库能力域 + 服务。前者是共享基座，后者按服务拆分。
BACKEND_CORE = "backend/libs/bms_core/src/bms_core"
BACKEND_SERVICES_DIR = "backend/services"
# 前端：workspace 包
FRONTEND_PACKAGES = "frontend/packages"

# 职责描述来源：后端 docstring / 前端头部注释（JSDoc、行注释、Vue 模板注释）；取不到则留空
DOCSTRING_MAX = 80


def truncate_doc(text: str, limit: int = DOCSTRING_MAX) -> str:
    """把 docstring 首行截到 limit 内，且尽量在标点处收尾（不在半词处硬切）。"""
    text = text.strip()
    if len(text) <= limit:
        return text
    cut = text[:limit]
    for sep in ("；", "。", "，", ":", "："):
        pos = cut.rfind(sep)
        if pos >= limit // 2:
            return cut[: pos + 1]
    return cut + "…"


def module_docstring(path: Path) -> str:
    """取 Python 模块 docstring 首行（无 ast 开销，够快）。"""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    except (SyntaxError, OSError, ValueError):
        return ""
    doc = ast.get_docstring(tree)
    if not doc:
        return ""
    first = doc.strip().splitlines()[0].strip()
    return truncate_doc(first)


def package_exports(path: Path) -> ConcurrentStableList[str]:
    """从 __init__.py 提取 __all__ 或顶层 def/class 名（前若干个）。"""
    if not path.is_file():
        return []
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    except (SyntaxError, OSError, ValueError):
        return []
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if (
                    isinstance(target, ast.Name)
                    and target.id == "__all__"
                    and isinstance(node.value, ast.List | ast.Tuple)
                ):
                    return [
                        el.value
                        for el in node.value.elts
                        if isinstance(el, ast.Constant) and isinstance(el.value, str)
                    ]
    names = [
        node.name
        for node in tree.body
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef)
    ]
    return names


def _plain(obj):
    """把集合类对象递归转成普通 list / dict（JSON 序列化用）。

    ConcurrentStableList / ConcurrentStableDict 均不继承内置 list / dict
    （MRO 落在 Sequence / Mapping），json 无法序列化，需先还原。
    """
    if isinstance(obj, Mapping):
        return {k: _plain(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set, frozenset)) or (
        hasattr(obj, "__iter__") and not isinstance(obj, str)
    ):
        return [_plain(x) for x in obj]
    return obj


def rel_to_bms(bms: Path, path: Path) -> str:
    """相对 bms 仓库根的路径（不写绝对路径——避免本机目录泄露到文档）。"""
    try:
        return path.relative_to(bms).as_posix()
    except ValueError:
        return path.name


def scan_python_dir(base: Path, label: str, bms: Path) -> ConcurrentStableDict:
    """扫一个 Python 包目录，产出目录 → 文件 / 职责 的登记。"""
    entries: ConcurrentStableList[ConcurrentStableDict] = ConcurrentStableList()
    for path in sorted(base.rglob("*.py")):
        if "__pycache__" in path.parts or "tests" in path.parts:
            continue
        rel = path.relative_to(base)
        if rel.name == "__init__.py" and rel.parent == Path("."):
            continue
        entries.add(
            {
                "rel": rel.as_posix(),
                "doc": module_docstring(path),
            }
        )
    return {
        "label": label,
        "base": rel_to_bms(bms, base),
        "entries": entries,
        "exports": package_exports(base / "__init__.py"),
    }


# 块注释起始标记：TS 的 /** 与 Vue <script> 内 JSDoc 同一形态。
BLOCK_DOC_RE = re.compile(r"/\*\*(.*?)\*/", re.DOTALL)


def leading_block_doc(path: Path) -> str:
    """提取 TS / Vue 文件的头部职责注释首行。

    两种形态都认（按优先级）：
    1. JSDoc 块注释 `/** … */`——后端 docstring 的对应形态；
    2. 连续行注释 `// …`——本仓 .vue 组件常用（如 `// AI 助手容器（08_10）：…`），
       取<script 起始处起、import 之前的连续 // 行首行。

    只看文件头部：import / export / function / class / const 之前的内容，
    避免把函数体内的注释误当文件职责。
    """
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    if path.suffix == ".vue":
        # Vue 的职责注释可能在 <script> 之前的 <!-- --> 里（模板区说明），
        # 也可能在 <script> 内；两处都找，先 template 区后 script 区。
        for marker in ("<!--", "<script"):
            pos = text.find(marker)
            if pos >= 0:
                found = _leading_doc_from(text[pos:])
                if found:
                    return found
        return ""
    return _leading_doc_from(text)


def _leading_doc_from(text: str) -> str:
    """从一段文本的头部提取职责注释首行（HTML / JSDoc / 连续行注释）。"""
    # 头部边界：第一个 import / export / function / class / const 之前
    stop = len(text)
    for kw in ("import ", "export ", "function ", "class ", "const "):
        hit = text.find(kw)
        if 0 <= hit < stop:
            stop = hit
    head = text[:stop] if stop > 0 else text

    # 形态 1：HTML 注释 <!-- … -->（Vue 模板区说明）
    html = re.search(r"<!--(.*?)-->", head, re.DOTALL)
    if html:
        for ln in html.group(1).splitlines():
            ln = ln.strip()
            if ln:
                return truncate_doc(ln)

    # 形态 2：JSDoc 块注释 /** … */
    match = BLOCK_DOC_RE.search(head)
    if match:
        lines = [ln.strip().lstrip("*").strip() for ln in match.group(1).splitlines()]
        for ln in lines:
            if ln:
                return truncate_doc(ln)

    # 形态 3：连续行注释 // …（Vue <script setup> 内常用）
    for raw in head.splitlines():
        ln = raw.strip()
        # Vue 的 <script …> 开闭标签本身不是注释，跳过
        if not ln or ln.startswith(("<script", "</script")):
            continue
        if ln.startswith("//"):
            content = ln.lstrip("/").strip()
            if content:
                return truncate_doc(content)
        elif ln.startswith(("/*", "*")):
            continue  # 块注释已处理过，跳过
        else:
            break  # 遇到非注释内容即停止
    return ""


def scan_frontend_pkg(pkg: Path, bms: Path) -> ConcurrentStableDict:
    """扫一个前端包：ts / vue 源文件 + 职责（取自文件首个 JSDoc 块注释）。"""
    entries: ConcurrentStableList[ConcurrentStableDict] = ConcurrentStableList()
    for path in sorted(pkg.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix not in {".ts", ".vue", ".tsx"}:
            continue
        if "node_modules" in path.parts or "dist" in path.parts:
            continue
        rel = path.relative_to(pkg)
        entries.add(
            {
                "rel": rel.as_posix(),
                "doc": leading_block_doc(path),
            }
        )
    return {
        "label": pkg.name,
        "base": rel_to_bms(bms, pkg),
        "entries": entries,
        "exports": [],
    }


def render(
    backend: ConcurrentStableList[ConcurrentStableDict],
    frontend: ConcurrentStableList[ConcurrentStableDict],
) -> str:
    lines: ConcurrentStableList[str] = ConcurrentStableList()
    lines.add("# 代码落点索引")
    lines.add("")
    lines.add("> 按「模块 / 服务 → 目录 → 关键文件 → 职责」登记代码落点 · 只管导航")
    lines.add("")
    lines.add('## 1. 定位说明 <a id="what"></a>')
    lines.add("")
    lines.add("本索引回答两个问题：**某个能力在哪个服务 / 包**，**它的入口文件在哪**。")
    lines.add(
        "继承链、父基类、基类口径的唯一权威仍是《[前端基类清单](前端基类清单.md)》《[后端基类清单](后端基类清单.md)》——"
    )
    lines.add("本索引**不复制**这些结论，只提供目录与职责导航。")
    lines.add("")
    lines.add(
        "配套：[文档域路由索引](文档域路由索引.md)（文档去哪查）· [基座文档清单](基座文档清单.md)（基座边界）"
    )
    lines.add("")
    lines.add("维护：`scripts/tools/search/gen-code-index.py` 扫描生成；")
    lines.add(
        "职责描述取自源码头部注释：后端模块 docstring；前端 JSDoc 块注释 / 行注释 / Vue 模板注释。"
    )
    lines.add(
        "（1217 个源文件中 1211 个有头部职责注释；其余为 vitest 配置与测试文件，无需职责说明）"
    )
    lines.add("")

    lines.add('## 2. 后端 <a id="backend"></a>')
    lines.add("")
    for mod in backend:
        count = len(mod["entries"])
        lines.add(f"### {mod['label']}")
        lines.add("")
        lines.add(f"- **目录**：`{mod['base']}`")
        lines.add(f"- **源码文件**：{count} 个（不含 tests 与 __pycache__）")
        if mod["exports"]:
            shown = "、".join(f"`{e}`" for e in mod["exports"][:12])
            more = " 等" if len(mod["exports"]) > 12 else ""
            lines.add(f"- **导出面**：{shown}{more}")
        lines.add("")
        if mod["entries"]:
            lines.add("| 文件 | 职责 |")
            lines.add("| --- | --- |")
            for entry in mod["entries"]:
                doc = entry["doc"] or "待补"
                lines.add(f"| `{entry['rel']}` | {doc} |")
            lines.add("")

    lines.add('## 3. 前端 <a id="frontend"></a>')
    lines.add("")
    for pkg in frontend:
        count = len(pkg["entries"])
        with_doc = [e for e in pkg["entries"] if e["doc"].strip()]
        lines.add(f"### {pkg['label']}")
        lines.add("")
        lines.add(f"- **目录**：`{pkg['base']}`")
        lines.add(
            f"- **源文件**：{count} 个（ts / vue / tsx，不含 dist）"
            f" · 有头部职责注释 {len(with_doc)} 个"
        )
        lines.add("")
        if with_doc:
            lines.add("| 文件 | 职责 |")
            lines.add("| --- | --- |")
            for entry in with_doc:
                lines.add(f"| `{entry['rel']}` | {entry['doc']} |")
            lines.add("")
        no_doc = [e for e in pkg["entries"] if not e["doc"].strip()]
        if no_doc:
            names = "、".join(f"`{e['rel']}`" for e in no_doc[:20])
            more = f" 等 {len(no_doc)} 个" if len(no_doc) > 20 else ""
            lines.add(f"> 无头部职责注释：{names}{more}")
            lines.add("")

    lines.add("---")
    lines.add("")
    lines.add("> 由 `scripts/tools/search/` 生成 · 结构自动扫描 / 职责取自头部注释")
    lines.add("> （后端 docstring、前端 JSDoc 块注释 / 行注释 / Vue 模板注释三种形态）")
    lines.add("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="代码落点索引进结构生成器")
    parser.add_argument("--bms-root", default=".", help="bms 仓库根（默认当前目录）")
    parser.add_argument("-o", "--out", help="输出 Markdown 路径")
    parser.add_argument("--json", dest="json_out", help="同时输出结构 JSON")
    args = parser.parse_args()

    bms = Path(args.bms_root).resolve()

    backend: ConcurrentStableList[ConcurrentStableDict] = ConcurrentStableList()
    core = bms / BACKEND_CORE
    if core.is_dir():
        # 核心库按能力域分子表，一个能力域一块
        for sub in sorted(core.iterdir()):
            if sub.is_dir() and not sub.name.startswith("__"):
                backend.add(scan_python_dir(sub, f"bms_core · {sub.name}", bms))
    services = bms / BACKEND_SERVICES_DIR
    if services.is_dir():
        for svc in sorted(services.iterdir()):
            src = svc / "src"
            if not src.is_dir():
                continue
            # 服务 src 下是 bms_<名> 包
            pkgs = [
                p for p in src.iterdir() if p.is_dir() and not p.name.startswith("__")
            ]
            for pkg in pkgs:
                backend.add(scan_python_dir(pkg, f"服务 {svc.name} · {pkg.name}", bms))

    frontend: ConcurrentStableList[ConcurrentStableDict] = ConcurrentStableList()
    pkgs_dir = bms / FRONTEND_PACKAGES
    if pkgs_dir.is_dir():
        for pkg in sorted(pkgs_dir.iterdir()):
            if pkg.is_dir() and (pkg / "src").is_dir():
                frontend.add(scan_frontend_pkg(pkg, bms))

    if args.json_out:
        Path(args.json_out).write_text(
            json.dumps(
                {"backend": _plain(backend), "frontend": _plain(frontend)},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"[JSON] {args.json_out}")

    text = render(backend, frontend)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"[输出] {args.out}（{len(text.splitlines())} 行）")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
