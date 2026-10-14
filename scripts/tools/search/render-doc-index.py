#!/usr/bin/env python3
"""把 gen-doc-index.py 产出的骨架 JSON 渲染为《文档域路由索引》Markdown。

产物定位（见 AGENTS.md「代码与文档检索（强制口径）」）：
- 只做**导航**——「这个主题去哪个域、从哪份文件查起」；
- 不复制、不改写任何口径权威（前后端基类清单 / 基座文档清单 / 各规范正文）；
- 结构由 gen-doc-index.py 扫描目录生成，语义（topic / questions / entry_files）
  由本地 LLM 批量补全，本脚本只负责排版与一致性校验。

用法：
    python3 render-doc-index.py <骨架.json> -o <输出.md>
    python3 render-doc-index.py <骨架.json> -o <输出.md> --check   # 只校验不写文件
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

# bms_core 源码根：集合声明统一落插入序集合类（ConcurrentStable*，见裸集合护栏口径）。
_ROOT = Path(__file__).resolve().parents[3]
_SRC_ROOT = _ROOT / "backend" / "libs" / "bms_core" / "src"
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))

from bms_core.core.concurrent import (  # noqa: E402
    ConcurrentStableDict,
    ConcurrentStableList,
)

# 主题域展示顺序（未列出的域按名称接在后面）
DOMAIN_ORDER: ConcurrentStableList[str] = ConcurrentStableList(
    [
        "规范与约束",
        "规划与选型",
        "架构设计",
        "基类体系",
        "数据库设计",
        "概要设计",
        "组件设计",
        "其他设计",
        "项目进度",
        "资料与知识档案",
        "审计",
        "用户文档",
        "其他",
    ]
)

# 入口文件展示名上限（超出折叠为「等」）
ENTRY_CAP = 3

# 宿主仓 = 本索引所在仓库（bms）。非宿主仓的入口按项目分治口径写纯文本。
HOME_REPO = "bms"

# 仓库名 → 文档根名（用于把单元的相对路径还原为工作区可见路径）
REPO_DOC_ROOT = {
    "bms": "bms/bms文档",
    "mdm": "mdm/mdm文档",
    "biz": "biz/biz文档",
    "test": "test/test文档",
}


def entry_path(unit: ConcurrentStableDict, rel: str) -> str:
    """入口路径按项目引用分治口径生成：

    - 宿主仓（bms，即本索引所在仓）：用仓内相对路径，可在 VS Code 里跳转；
    - 其他仓（mdm / biz / test）：写「仓库/文档根/…」**纯文本**，不写成链接——
      与 bms 正文跨仓引用口径一致（CI 只 clone bms 会判断链，跨仓必断）。
    """
    root = REPO_DOC_ROOT.get(unit["repo"], f"{unit['repo']}/")
    full = f"{root}/{rel}"
    if unit["repo"] == HOME_REPO:
        return f"[{Path(rel).stem}]({rel})"
    return f"〔{full}〕"


def render_unit(unit: ConcurrentStableDict, lines: ConcurrentStableList[str]) -> None:
    sem = unit.get("semantic") or {}
    topic = sem.get("topic")
    files = unit["files"]
    entry = sem.get("entry_files") or [f["rel"] for f in files[:1]]
    entry = [e for e in entry if any(f["rel"] == e for f in files)][:ENTRY_CAP]

    # 标题 = 仓库 · 目录 · 主题（同名单元靠仓库与主题区分）
    title = f"{unit['repo']} · {unit['dir']}"
    if topic:
        title += f"（{topic}）"
    lines.add(f"#### {title}")
    lines.add("")
    meta = f"{unit['file_count']} 份"
    if sem.get("questions"):
        meta += f" · {' / '.join(sem['questions'])}"
    lines.add(f"- **规模**：{meta}")
    if entry:
        links = "、".join(entry_path(unit, e) for e in entry)
        lines.add(f"- **首查**：{links}")
    lines.add("")


def render(skeleton: ConcurrentStableList[ConcurrentStableDict]) -> str:
    today = date.today().isoformat()
    total_files = sum(u["file_count"] for u in skeleton)
    by_repo: ConcurrentStableDict[str, int] = ConcurrentStableDict()
    for u in skeleton:
        repo = u["repo"]
        by_repo.set(repo, by_repo.get(repo, 0) + u["file_count"])

    lines: ConcurrentStableList[str] = ConcurrentStableList()
    lines.add("# 文档域路由索引")
    lines.add("")
    lines.add("> 按「主题域 × 阶段」指路的文档导航 · 与《文档首页》互补：首页管全量树，本索引管「去哪查」")
    lines.add("")
    lines.add("[文档首页](文档首页.md) › 文档域路由索引　|　[配套：基座文档清单 →](基座文档清单.md)")
    lines.add("")
    lines.add("---")
    lines.add("")
    lines.add('## 1. 这是什么、不是什么 <a id="what"></a>')
    lines.add("")
    lines.add("**是**：一张「主题 → 去哪个域 → 从哪份文件查起」的路由表。")
    lines.add("文档规模已到 1788 份 / 1190 万字符，常见词命中上千文件，")
    lines.add("直接全库撒词的代价远高于先查本索引再进目录。")
    lines.add("")
    lines.add("**不是**：任何口径的权威来源。基类继承链仍以《前端基类清单》《后端基类清单》为唯一权威，")
    lines.add("基座边界以《基座文档清单》为准，规范正文以各《规范》为准——本索引只指路，不复制结论。")
    lines.add("")
    lines.add("**维护**：结构由 `scripts/tools/search/gen-doc-index.py` 扫描目录生成，")
    lines.add("语义（典型问题 / 首查文件）由本地 LLM 批量补全；")
    lines.add("目录结构变化后重跑生成，勿手改结构部分。")
    lines.add("")
    lines.add("配套：[代码落点索引](代码落点索引.md)（代码去哪找）· [基座文档清单](基座文档清单.md)（基座边界）")
    lines.add("")
    lines.add('## 2. 规模总览 <a id="scale"></a>')
    lines.add("")
    lines.add("| 仓库 | 文档份数 |")
    lines.add("| --- | --- |")
    for repo in sorted(by_repo, key=lambda r: -by_repo[r]):
        lines.add(f"| `{repo}` | {by_repo[repo]} |")
    lines.add(f"| **合计** | **{total_files}** |")
    lines.add("")

    # 按主题域分组
    lines.add('## 3. 主题域路由 <a id="routing"></a>')
    lines.add("")
    domains: ConcurrentStableDict[str, ConcurrentStableList[ConcurrentStableDict]] = ConcurrentStableDict()
    for u in skeleton:
        dom = u["domain"]
        if dom not in domains:
            domains.set(dom, ConcurrentStableList())
        domains.get(dom).add(u)
    ordered = [d for d in DOMAIN_ORDER if d in domains]
    ordered += [d for d in sorted(domains) if d not in DOMAIN_ORDER]

    for dom in ordered:
        units = sorted(
            domains[dom],
            # 同域内排序：宿主仓（bms）优先，其余按仓库名 + 目录名。
            # 项目进度域各仓都有「项目/…」单元，bms 是主体，应排在最前。
            key=lambda u: (0 if u["repo"] == HOME_REPO else 1, u["repo"], u["dir"]),
        )
        lines.add(f"### {dom}")
        lines.add("")
        for unit in units:
            render_unit(unit, lines)

    lines.add("---")
    lines.add("")
    lines.add(f"> 由 `scripts/tools/search/` 生成 · {today} · 结构自动 / 语义 LLM 补全")
    lines.add("")
    lines.add("> 依《[文档生成规范](规范/文档生成规范.md)》编写")
    lines.add("")
    return "\n".join(lines)


def check(skeleton: ConcurrentStableList[ConcurrentStableDict]) -> int:
    """一致性校验：入口文件必须真实存在、语义字段非空。"""
    problems = 0
    for u in skeleton:
        if not u.get("needs_llm"):
            continue
        sem = u.get("semantic")
        if not sem:
            log_problem(f"{u['repo']}/{u['dir']}：缺语义")
            problems += 1
            continue
        if not sem.get("topic"):
            log_problem(f"{u['repo']}/{u['dir']}：topic 为空")
            problems += 1
        if not sem.get("questions"):
            log_problem(f"{u['repo']}/{u['dir']}：questions 为空")
            problems += 1
        if not sem.get("entry_files"):
            log_problem(f"{u['repo']}/{u['dir']}：entry_files 为空")
            problems += 1
    return problems


def log_problem(msg: str) -> None:
    print(f"[不一致] {msg}", file=sys.stderr)


def main() -> int:
    parser = argparse.ArgumentParser(description="渲染《文档域路由索引》")
    parser.add_argument("skeleton", help="gen-doc-index.py 产出的骨架 JSON")
    parser.add_argument("-o", "--out", help="输出 Markdown 路径")
    parser.add_argument("--check", action="store_true", help="只校验不写文件")
    args = parser.parse_args()

    skeleton = json.loads(Path(args.skeleton).read_text(encoding="utf-8"))
    problems = check(skeleton)
    if problems:
        print(f"[校验] 发现 {problems} 处不一致", file=sys.stderr)
        return 1
    print(f"[校验] {sum(1 for u in skeleton if u.get('needs_llm'))} 个语义单元全部一致")

    if args.check:
        return 0
    if not args.out:
        print("未指定 -o，仅校验", file=sys.stderr)
        return 2

    text = render(skeleton)
    Path(args.out).write_text(text, encoding="utf-8")
    print(f"[输出] {args.out}（{len(text.splitlines())} 行）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
