#!/usr/bin/env python3
"""界面交付「实现 ↔ 原型」核对护栏（check-prototype-review）。

口径见《原型审查规范》§4.9「实现 ↔ 原型 / 布局 核对（界面类交付验收）」与《AI 开发规范》§7「界面先原型」/
§8 检查清单——**界面类交付必须有原型依据 + 逐页对照结论**。此前仅靠人工自律，已出现「登录页被套进主框架外壳」
（2026-10-04 用户复核实测发现，阶段计划 §7 第 53 项）一类**实现偏离原型却一路通过**的事故，故设本机器门禁。

规则：

1. **界面改动检测**（`--changed [base]`，缺省 `origin/main`）：取 `git diff --name-only <base>...HEAD`，
   命中界面源码路径（`frontend/apps/desktop/src/{views,components,layouts}`、`frontend/packages/ui-ep/src`、
   任意 `*.vue`）即视为**界面改动**；
2. 含界面改动的变更集必须包含**测试记录**（`bms文档/项目/*/任务/**/测试/*.md`），且该记录含**原型对照节**：
   节标题含「原型」、节内表头含「结论」且至少一行数据、至少一个**存在**的截图引用（`.png`）、
   且不含未完成词（`待补` / `待对照` / `未核对` / `TODO` 等）；纯逻辑改动可写「不适用」并给出理由（≥10 字）；
3. **原型依据**：上述记录（或该变更集内的设计 / 实施记录）须出现 `设计/原型设计/**.html` 引用，且文件存在。

用法::

    python3 scripts/tools/base-check/check-prototype-review.py [bms 仓库根]      # 全仓巡检（软提示，不阻断）
    python3 scripts/tools/base-check/check-prototype-review.py [root] --changed [base]
    python3 scripts/tools/base-check/check-prototype-review.py --self-test

`--changed` 的 `[base]` 缺省 `origin/main`；基准不可解析（CI / 浅克隆）时脚本自行跳过，不误拦。

退出码：0 通过（或软提示）；1 违规；2 参数 / 目录 / git 错误。
"""

from __future__ import annotations

import re
import subprocess
import sys
import tempfile
from pathlib import Path

# bms_core 源码根：脚本在仓库内运行，集合声明统一落插入序集合类（ConcurrentStable*）。
_SRC_ROOT = Path(__file__).resolve().parents[3] / "backend" / "libs" / "bms_core" / "src"
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))

from bms_core.core.concurrent import ConcurrentStableList  # noqa: E402

DOCS_DIR = "bms文档"
PROTOTYPE_DIR = f"{DOCS_DIR}/设计/原型设计"
RECORD_RE = re.compile(rf"^{DOCS_DIR}/项目/[^/]+/任务/.+/测试/[^/]+\.md$")
CONTEXT_RE = re.compile(rf"^{DOCS_DIR}/项目/[^/]+/任务/.+/(设计|实施|测试)/[^/]+\.md$")
PROTO_REF_RE = re.compile(r"原型设计/([^\s)\"'`<>|]+\.html)")
PNG_RE = re.compile(r"\]\(([^)\s]+\.png)\)")
UNFINISHED_RE = re.compile(r"待补|待对照|待核|未核对|未核|待定|TODO|待办")
NOT_APPLICABLE_RE = re.compile(r"不适用")
MIN_REASON_LEN = 10
PROTO_SECTION_RE = r"^##[^\n]*原型"
TABLE_HEADER_RE = re.compile(r"^\|(?![\s:|-]+\|$).*\|$")

UI_CODE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"^frontend/apps/desktop/src/(views|components|layouts)/"),
    re.compile(r"^frontend/packages/ui-ep/src/"),
    re.compile(r"^frontend/.*\.vue$"),
)
"""界面源码路径（改动命中即视为界面改动，须有原型对照）。"""


def git_changed(root: Path, base: str) -> ConcurrentStableList[str] | None:
    """取 `<base>...HEAD` 的改动文件清单。

    Args:
        root: 仓库根。
        base: 比较基准（分支 / 提交）。

    Returns:
        相对仓库根的文件路径列表；git 不可用或基准不存在时返回 None。
    """
    proc = subprocess.run(
        # `core.quotepath=false`：中文路径（`bms文档/…`）不被转义为 `\346\226\207…`，否则记录匹配不到。
        ["git", "-C", str(root), "-c", "core.quotepath=false", "diff", "--name-only", f"{base}...HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        return None
    changed: ConcurrentStableList[str] = ConcurrentStableList()
    changed.update([line.strip().strip('"') for line in proc.stdout.splitlines() if line.strip()])
    return changed


def read_section(text: str, heading_re: str) -> str:
    """取标题匹配 `heading_re` 的节内容（到下一个二级标题为止）。

    Args:
        text: 文档全文。
        heading_re: 二级标题正则。

    Returns:
        节内容（未命中返回空串）。
    """
    lines = text.splitlines()
    start: int | None = None
    for index, line in enumerate(lines):
        if re.match(heading_re, line):
            start = index + 1
            continue
        if start is not None and line.startswith("## "):
            return "\n".join(lines[start:index])
    return "" if start is None else "\n".join(lines[start:])


def prototype_basis_problems(root: Path, texts: ConcurrentStableList[tuple[str, str]]) -> ConcurrentStableList[str]:
    """校验原型依据（`原型设计/**.html` 引用且文件存在）。

    Args:
        root: 仓库根。
        texts: (来源说明, 文本) 列表。

    Returns:
        问题列表（空即通过）。
    """
    problems: ConcurrentStableList[str] = ConcurrentStableList()
    found_ref = False
    for source, text in texts:
        for match in PROTO_REF_RE.finditer(text):
            found_ref = True
            if not (root / PROTOTYPE_DIR / match.group(1)).is_file():
                problems.add(f"{source}：原型引用文件不存在 → {PROTOTYPE_DIR}/{match.group(1)}")
    if not found_ref:
        problems.add("未登记原型依据：需在（设计 / 实施 / 测试）记录中出现 `设计/原型设计/**.html` 引用")
    return problems


def review_section_problems(record: Path, text: str) -> ConcurrentStableList[str]:
    """校验原型对照节（节存在 + 结论表 + 截图 + 无未完成词）。

    Args:
        record: 测试记录路径。
        text: 记录全文。

    Returns:
        问题列表（空即通过）。
    """
    problems: ConcurrentStableList[str] = ConcurrentStableList()
    section = read_section(text, PROTO_SECTION_RE)
    if not section.strip():
        problems.add(f"{record}：缺「原型对照结论」节（按《原型审查规范》§4.9 逐页对照）")
        return problems

    if NOT_APPLICABLE_RE.search(section):
        reason = re.sub(r"\s+", "", section.replace("不适用", "", 1))
        if len(reason) < MIN_REASON_LEN:
            problems.add(f"{record}：声明「不适用」但未给理由（需 ≥{MIN_REASON_LEN} 字说明为何无界面可见变更）")
        return problems

    header = ""
    rows = 0
    for line in section.splitlines():
        stripped = line.strip()
        if not TABLE_HEADER_RE.match(stripped):
            continue
        if "结论" in stripped and not header:
            header = stripped
        elif header:
            rows += 1
    if not header:
        problems.add(
            f"{record}：原型对照节缺表头含「结论」的对照表（列建议 `# / 对照项 / 原型依据 / 实现实测 / 结论`）"
        )
    elif rows == 0:
        problems.add(f"{record}：原型对照表无数据行（逐页 / 逐项结论均需落行）")

    shots = 0
    for match in PNG_RE.finditer(section):
        if (record.parent / match.group(1)).resolve().is_file():
            shots += 1
    if shots == 0:
        problems.add(f"{record}：原型对照节缺**存在**的截图证据（`.png` 引用，落 `测试/资源/<记录名>/`）")

    unfinished = UNFINISHED_RE.search(section)
    if unfinished:
        problems.add(f"{record}：原型对照节含未完成词「{unfinished.group(0)}」（对照须给出结论，不得留待办）")
    return problems


def check_records(
    root: Path,
    records: ConcurrentStableList[Path],
    context_texts: ConcurrentStableList[tuple[str, str]],
) -> ConcurrentStableList[str]:
    """对给定测试记录集执行原型对照 + 原型依据校验。

    Args:
        root: 仓库根。
        records: 测试记录路径列表。
        context_texts: 原型依据候选文本（设计 / 实施 / 测试记录）。

    Returns:
        问题列表。
    """
    problems: ConcurrentStableList[str] = ConcurrentStableList()
    for record in records:
        problems.update(review_section_problems(record, record.read_text(encoding="utf-8")))
    problems.update(prototype_basis_problems(root, context_texts))
    return problems


def changed_mode(root: Path, base: str) -> int:
    """推送前硬拦模式：含界面改动则必须有原型对照。

    Args:
        root: 仓库根。
        base: 比较基准。

    Returns:
        退出码。
    """
    changed = git_changed(root, base)
    if changed is None:
        print(f"[check-prototype-review] 跳过：无法解析 `git diff {base}...HEAD`（CI / 浅克隆等场景）")
        return 0
    ui_files: ConcurrentStableList[str] = ConcurrentStableList()
    records: ConcurrentStableList[Path] = ConcurrentStableList()
    texts: ConcurrentStableList[tuple[str, str]] = ConcurrentStableList()
    for name in changed:
        if any(pattern.search(name) for pattern in UI_CODE_PATTERNS):
            ui_files.add(name)
        if CONTEXT_RE.match(name):
            path = root / name
            if path.is_file():
                texts.add((name, path.read_text(encoding="utf-8")))
        if RECORD_RE.match(name):
            path = root / name
            if path.is_file():
                records.add(path)

    if not ui_files:
        print(f"[check-prototype-review] 通过：本次改动无界面源码（{base}...HEAD 共 {len(changed)} 个文件）")
        return 0
    print(f"[check-prototype-review] 本次含界面改动 {len(ui_files)} 个，例：{ui_files[0]}")
    if not records:
        print(
            "[check-prototype-review] ✗ 含界面改动但变更集内**没有测试记录**——"
            "按《原型审查规范》§4.9 须落「原型对照结论」（逐页 + 结论 + 截图）"
        )
        return 1
    problems = check_records(root, records, texts)
    if problems:
        for item in problems:
            print(f"[check-prototype-review] ✗ {item}")
        return 1
    print(f"[check-prototype-review] 通过：原型依据 + 对照结论齐备（{records[0]}）")
    return 0


def inspect_mode(root: Path) -> int:
    """全仓巡检（软提示）：列出未落原型对照的任务测试记录。

    Args:
        root: 仓库根。

    Returns:
        退出码（恒 0）。
    """
    docs = root / DOCS_DIR / "项目"
    if not docs.is_dir():
        print(f"[check-prototype-review] 目录缺失：{docs}", file=sys.stderr)
        return 2
    records: ConcurrentStableList[Path] = ConcurrentStableList()
    records.update(sorted(docs.glob("*/任务/**/测试/*.md")))
    missing: ConcurrentStableList[str] = ConcurrentStableList()
    for record in records:
        if not read_section(record.read_text(encoding="utf-8"), PROTO_SECTION_RE).strip():
            missing.add(str(record.relative_to(root)))
    print(
        f"[check-prototype-review] 巡检：任务测试记录 {len(records)} 份，"
        f"未落「原型对照结论」{len(missing)} 份（软提示）"
    )
    for name in missing[:20]:
        print(f"  · {name}")
    if len(missing) > 20:
        print(f"  · …（余 {len(missing) - 20} 份）")
    print("[check-prototype-review] 提示：界面类任务须补对照结论；非界面类无需补（推送时按界面改动硬拦）")
    return 0


def self_test() -> int:
    """自检：构造样例文档树，校验通过 / 拦截分支。

    Returns:
        退出码（0 通过，1 失败）。
    """
    failures: ConcurrentStableList[str] = ConcurrentStableList()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / PROTOTYPE_DIR / "03_通用骨架").mkdir(parents=True)
        (root / PROTOTYPE_DIR / "03_通用骨架/02_登录页.html").write_text("<html></html>", encoding="utf-8")
        record_dir = root / DOCS_DIR / "项目/06_认证与安全/任务/05_登录前端/05_登录前端_01_x/测试"
        (record_dir / "资源/01_测试_01_x").mkdir(parents=True)
        (record_dir / "资源/01_测试_01_x/实现-登录页.png").write_bytes(b"png")
        record = record_dir / "01_测试_01_x.md"

        good = (
            "## 1. 测试信息\n\n"
            "## 4. 原型对照结论（实现 ↔ 原型 / 布局，按《原型审查规范》§4.9）\n\n"
            "基准：[登录页原型](../../../../../../../设计/原型设计/03_通用骨架/02_登录页.html)。\n\n"
            "| # | 对照项 | 原型依据 | 实现实测 | 结论 |\n| --- | --- | --- | --- | --- |\n"
            "| 1 | 独立全屏 | 登录页原型 | 无侧栏 / 页签 | 通过 |\n\n"
            "| 截面 | 截图 |\n| --- | --- |\n"
            "| 实现 | [实现-登录页.png](资源/01_测试_01_x/实现-登录页.png) |\n"
        )
        good_texts: ConcurrentStableList[tuple[str, str]] = ConcurrentStableList()
        good_texts.add(("record", good))
        one_record: ConcurrentStableList[Path] = ConcurrentStableList()
        one_record.add(record)

        record.write_text(good, encoding="utf-8")
        if check_records(root, one_record, good_texts):
            failures.add("样例 A（齐备）应通过")

        bare_texts: ConcurrentStableList[tuple[str, str]] = ConcurrentStableList()
        bare_texts.add(("record", "无对照节"))
        record.write_text("## 1. 测试信息\n\n无对照节\n", encoding="utf-8")
        if not check_records(root, one_record, bare_texts):
            failures.add("样例 B（缺对照节）应被拦")

        record.write_text(good.replace("| 通过 |", "| 待补 |"), encoding="utf-8")
        if not check_records(root, one_record, good_texts):
            failures.add("样例 C（含未完成词）应被拦")

        record.write_text("## 4. 原型对照结论\n\n不适用：本次仅修复请求头拼写，界面无可见变更。\n", encoding="utf-8")
        if check_records(root, one_record, good_texts):
            failures.add("样例 D（不适用 + 理由）应通过")

        no_ref = "## 4. 原型对照结论\n\n| # | 对照项 | 结论 |\n| --- | --- | --- |\n| 1 | x | 通过 |\n"
        no_ref_texts: ConcurrentStableList[tuple[str, str]] = ConcurrentStableList()
        no_ref_texts.add(("record", no_ref))
        record.write_text(no_ref, encoding="utf-8")
        if not check_records(root, one_record, no_ref_texts):
            failures.add("样例 E（缺原型依据 + 缺截图）应被拦")

        bad_ref = good.replace("03_通用骨架/02_登录页.html", "03_通用骨架/99_不存在.html")
        bad_ref_texts: ConcurrentStableList[tuple[str, str]] = ConcurrentStableList()
        bad_ref_texts.add(("record", bad_ref))
        record.write_text(bad_ref, encoding="utf-8")
        if not check_records(root, one_record, bad_ref_texts):
            failures.add("样例 F（原型引用文件不存在）应被拦")

    if failures:
        for item in failures:
            print(f"[check-prototype-review self-test] ✗ {item}", file=sys.stderr)
        return 1
    print("[check-prototype-review self-test] 通过：断言用例 6 个")
    return 0


def main() -> int:
    """入口。

    Returns:
        退出码。
    """
    argv = list(sys.argv[1:])
    if "--self-test" in argv:
        return self_test()
    base = "origin/main"
    if "--changed" in argv:
        index = argv.index("--changed")
        if index + 1 < len(argv) and not argv[index + 1].startswith("-"):
            base = argv[index + 1]
    root_arg = ""
    for item in argv:
        if not item.startswith("-") and item != base:
            root_arg = item
            break
    root = Path(root_arg).resolve() if root_arg else Path(".").resolve()
    if "--changed" in argv:
        return changed_mode(root, base)
    return inspect_mode(root)


if __name__ == "__main__":
    raise SystemExit(main())
