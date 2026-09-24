#!/usr/bin/env python3
"""需求 / 任务 / 计划三类项目文档的一致性核对。

用途（《需求文档规范》「进度口径」节、《任务文档规范》§7、《计划文档规范》§6）：需求文档只承载
「做什么与验收标准」，进度（状态 / 完成日期 / 工时）以任务与计划两类文档为准；需求侧只校验
**编号集合**（域文档 ↔ 总览总清单）。本脚本按固定规则扫描阶段目录，输出不一致清单，供阶段收口
与 CI 常跑使用。

规则分两层：
- **硬规则（默认阻断）**：结构性约束，任何时点都必须成立（需求编号集合、任务状态取值与日期口径、
  任务 ↔ 域总览 ↔ 计划一致、计划两表互斥、工时对齐、排期窗口格式）。
- **软提示（默认告警，``--strict`` 时阻断）**：统计与叙述类（计划头计数、工时合计、
  甘特与剩余表），阶段在途时可能暂不一致。

用法::

    python3 scripts/tools/check-docs/check-status.py                 # 阶段一（默认），硬规则阻断
    python3 scripts/tools/check-docs/check-status.py --stage 00_准备期
    python3 scripts/tools/check-docs/check-status.py --all           # 全部阶段
    python3 scripts/tools/check-docs/check-status.py --strict        # 软提示也阻断

默认只核对**阶段一（01_项目骨架）**：阶段 0 准备期文档为早期口径（完成日期含时间戳、
状态存在「框架完成」等扩展取值、域总览子任务清单列序不同），按现行规范核对会整体误报，
需显式 `--all` 或 `--stage 00_准备期` 才纳入（结果仅供人工参考，不作门禁）。

退出码：硬规则（或 ``--strict`` 下的软提示）存在不合规 → 1；否则 0。
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

STATUSES = ("未开始", "进行中", "部分完成", "已完成", "搁置")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

REQ_ID_RE = re.compile(r"^\d{2}-\d+$")
TASK_ID_RE = re.compile(r"^\d{2}-\d+-\d+$")  # 嵌套子任务编号（如 01-3-1）
PLAN_ID_RE = re.compile(r"^\d{2}_\d{2}$")

REQ_HEADING_RE = re.compile(r"^## \d+\. 需求 (?P<id>\d{2}-\d+)：")
ROW_RE = re.compile(r"^\|(?P<cells>.*)\|\s*$")
GANTT_NODE_RE = re.compile(r"^\s*(?P<id>\d{2}_\d{2})\s")
STATS_HEAD_RE = re.compile(r"已完成\s*(?P<done>\d+)\s*项，剩余\s*(?P<todo>\d+)\s*项")
EFFORT_RE = re.compile(
    # 兼容三种既有写法：`**316h**`（星号含 h）/ `316h`（无星号）/ `**316**h`（星号仅包数字）；
    # 2026-09-24 修正：原正则只认末一种，导致 S1 工时子校验在所有阶段计划上从未触发（10_01 实施发现）。
    r"已完成\s*\*{0,2}(?P<done>\d+)h\*{0,2}；剩余\s*\*{0,2}(?P<todo>\d+)h\*{0,2}"
    r".*?阶段合计\s*\*{0,2}(?P<total>\d+)h\*{0,2}"
)
HOURS_RE = re.compile(r"^(\d+)h$")


@dataclass
class Finding:
    """一条核对发现。"""

    level: str  # 硬 / 软
    code: str
    message: str


@dataclass
class TaskDoc:
    """顶层任务文档的关键字段。"""

    path: Path
    domain: str
    seq: str
    status: str
    date: str
    hours: str
    reqs: list[str]


@dataclass
class Report:
    """核对结果累积器。"""

    stage: str
    hard: list[Finding] = None  # type: ignore[assignment]
    soft: list[Finding] = None  # type: ignore[assignment]
    checks: int = 0

    def __post_init__(self) -> None:
        self.hard = [] if self.hard is None else self.hard
        self.soft = [] if self.soft is None else self.soft

    def ok(self, count: int = 1) -> None:
        self.checks += count

    def fail(self, level: str, code: str, message: str) -> None:
        self.checks += 1
        target = self.hard if level == "硬" else self.soft
        target.append(Finding(level, code, message))


def docs_hours(cell: str) -> int | None:
    """单元格取前导工时数字（兼容「21h（重估：…）」说明形态）。"""
    match = re.match(r"(\d+)h", cell.strip())
    return int(match.group(1)) if match else None


def split_row(line: str) -> list[str] | None:
    """把 Markdown 表格行切成单元格（表头分隔行返回 None）。"""
    match = ROW_RE.match(line)
    if not match:
        return None
    cells = [cell.strip() for cell in match.group("cells").split("|")]
    if all(set(cell) <= set("-: ") and cell for cell in cells):
        return None
    return cells


def read_section(text: str, heading_re: str) -> str:
    """截取从匹配 heading 的行到下一个二级标题之间的正文。"""
    lines = text.splitlines()
    start = None
    for idx, line in enumerate(lines):
        if re.search(heading_re, line):
            start = idx + 1
            break
    if start is None:
        return ""
    end = len(lines)
    for idx in range(start, len(lines)):
        if lines[idx].startswith("## "):
            end = idx
            break
    return "\n".join(lines[start:end])


def parse_req_domain(path: Path) -> dict[str, tuple[str, str]]:
    """解析需求域文档：编号 → (状态, 完成日期)。"""
    result: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        heading = REQ_HEADING_RE.match(line)
        if heading:
            result.add(heading.group("id"))
    return result


def parse_overview(path: Path) -> set[str]:
    """解析需求总览总清单表：编号集合（需求文档不承载进度）。"""
    result: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        cells = split_row(line)
        if cells and REQ_ID_RE.match(cells[0]):
            result.add(cells[0])
    return result


def parse_task_meta(path: Path) -> dict[str, str]:
    """解析任务文档「任务信息」表（两列表格）。"""
    section = read_section(path.read_text(encoding="utf-8"), r"^## 1\. 任务信息")
    meta: dict[str, str] = {}
    for line in section.splitlines():
        cells = split_row(line)
        if cells and len(cells) == 2:
            meta[cells[0]] = cells[1]
    return meta


def parse_domain_overview(path: Path) -> dict[str, tuple[str, str]]:
    """解析域总览子任务清单表：域内序号 → (状态, 完成日期)。"""
    section = read_section(path.read_text(encoding="utf-8"), r"^## 2\. 子任务清单")
    result: dict[str, tuple[str, str]] = {}
    for line in section.splitlines():
        cells = split_row(line)
        if cells and len(cells) == 6 and re.fullmatch(r"\d{2}", cells[0]):
            result[cells[0]] = (cells[3], cells[4])
    return result


def parse_plan(path: Path) -> dict[str, object]:
    """解析计划文档：两张排期表 + 头部统计 + 域地图。"""
    text = path.read_text(encoding="utf-8")
    done_section = read_section(text, r"^## 2\. 已完成任务")
    todo_section = read_section(text, r"^## 3\. 剩余任务排期")
    done: dict[str, dict[str, str]] = {}
    todo: dict[str, dict[str, str]] = {}
    for line in done_section.splitlines():
        cells = split_row(line)
        if cells and len(cells) == 6 and PLAN_ID_RE.match(cells[0]):
            done[cells[0]] = {"hours": cells[2], "date": cells[3]}
    for line in todo_section.splitlines():
        cells = split_row(line)
        if cells and len(cells) == 7 and PLAN_ID_RE.match(cells[0]):
            todo[cells[0]] = {"hours": cells[2], "window": cells[4]}
    head = STATS_HEAD_RE.search(text)
    effort = EFFORT_RE.search(text)
    gantt_ids = {
        m.group("id")
        for m in (GANTT_NODE_RE.match(line) for line in text.splitlines())
        if m
    }
    return {
        "done": done,
        "todo": todo,
        "stats": (int(head.group("done")), int(head.group("todo"))) if head else None,
        "effort": (
            int(effort.group("done")), int(effort.group("todo")), int(effort.group("total"))
        ) if effort else None,
        "gantt": gantt_ids,
    }


def expand_reqs(cell: str) -> list[str]:
    """从「对应需求」单元格提取需求编号；`A ~ B` 形态按域内序号展开。"""
    ids = re.findall(r"\d{2}-\d+", cell)
    if "~" in cell and len(ids) == 2 and ids[0].split("-")[0] == ids[1].split("-")[0]:
        domain = ids[0].split("-")[0]
        start, end = int(ids[0].split("-")[1]), int(ids[1].split("-")[1])
        if start <= end:
            return [f"{domain}-{seq}" for seq in range(start, end + 1)]
    return ids


def collect_tasks(stage_dir: Path, report: Report) -> dict[str, TaskDoc]:
    """扫描顶层任务文档（域/{域总览.md} 之下的同级任务目录），返回 计划编号 → 任务。"""
    task_root = stage_dir / "任务"
    tasks: dict[str, TaskDoc] = {}
    if not task_root.is_dir():
        return tasks
    for domain_dir in sorted(p for p in task_root.iterdir() if p.is_dir()):
        domain = domain_dir.name.split("_")[0]
        for task_dir in sorted(p for p in domain_dir.iterdir() if p.is_dir()):
            if task_dir.name in ("设计", "测试", "实施"):
                # 域级任务附属目录（任务级设计 / 测试记录 / 实施记录），非任务目录
                continue
            docs = [p for p in task_dir.glob("*.md")]
            if len(docs) != 1:
                report.fail("硬", "H5", f"任务目录文档数异常（{len(docs)}）：{task_dir}")
                continue
            path = docs[0]
            meta = parse_task_meta(path)
            seq = meta.get("编号", "").strip()
            status = meta.get("状态", "").strip()
            if TASK_ID_RE.match(seq):
                report.ok(2)  # 嵌套子任务：只校验状态与日期口径
                if status not in STATUSES:
                    report.fail("硬", "H2", f"任务状态取值非法：{path} → {status}")
                check_date(report, f"任务 {path}", status, meta.get("完成日期", "").strip())
                continue
            if not re.fullmatch(r"\d{2}", seq):
                report.fail("硬", "H5", f"任务编号未识别：{path} → {seq!r}")
                continue
            plan_id = f"{domain}_{seq}"
            doc = TaskDoc(
                path=path,
                domain=domain,
                seq=seq,
                status=status,
                date=meta.get("完成日期", "").strip(),
                hours=meta.get("工时（重估）", "").strip(),
                reqs=expand_reqs(meta.get("对应需求", "")),
            )
            if plan_id in tasks:
                report.fail("硬", "H6", f"计划编号重复：{plan_id}（{path}）")
            tasks[plan_id] = doc
            report.ok(2)
            if doc.status not in STATUSES:
                report.fail("硬", "H2", f"任务状态取值非法：{path} → {doc.status}")
            check_date(report, f"任务 {path}", doc.status, doc.date)
            for req in doc.reqs:
                report.ok()
                if req not in REQ_INDEX:
                    report.fail("硬", "H5", f"对应需求不存在：{path} → {req}")
    return tasks


def check_date(report: Report, label: str, status: str, date: str) -> None:
    """H3：已完成 ⇔ 完成日期为 YYYY-MM-DD。"""
    if status == "已完成":
        if not DATE_RE.match(date):
            report.fail("硬", "H3", f"{label} 已完成但完成日期非 YYYY-MM-DD：{date!r}")
    elif date not in ("—", ""):
        report.fail("硬", "H3", f"{label} 非已完成但填了完成日期：{status} / {date!r}")


REQ_INDEX: dict[str, str] = {}  # 编号 → 域文档路径（跨阶段全局）


def check_stage(stage_dir: Path, report: Report) -> None:
    """单个阶段的三类文档核对。"""
    req_dir = stage_dir / "需求"
    plan_dir = stage_dir / "计划"
    if not req_dir.is_dir() or not plan_dir.is_dir():
        print(f"[{stage_dir.name}] 跳过：缺少 需求/ 或 计划/ 目录")
        return

    overview_files = sorted(req_dir.glob("00_需求_*.md"))
    if not overview_files:
        report.fail("硬", "H1", f"缺少需求总览：{req_dir}/00_需求_*.md")
        return
    overview_path = overview_files[0]
    overview = parse_overview(overview_path)

    domain_reqs: dict[str, set[str]] = {}
    for domain_path in sorted(p for p in req_dir.glob("*.md") if not p.name.startswith("00_")):
        domain = domain_path.name.split("_")[0]
        domain_reqs[domain] = parse_req_domain(domain_path)
        for req in domain_reqs[domain]:
            REQ_INDEX[req] = str(domain_path)

    # H1：域文档编号集合 == 总览总清单编号集合（需求文档不承载进度）
    seen: dict[str, str] = {}
    for domain, reqs in domain_reqs.items():
        for req in reqs:
            if req in seen:
                report.fail("硬", "H1", f"需求编号重复：{req}（{seen[req]} / {domain}）")
            seen[req] = domain
            report.ok()
    for req in sorted(set(seen) - set(overview)):
        report.fail("硬", "H1", f"域文档有而总清单缺：{req}")
    for req in sorted(set(overview) - set(seen)):
        report.fail("硬", "H1", f"总清单有而域文档缺：{req}")

    # 任务类
    tasks = collect_tasks(stage_dir, report)

    # H5：域总览子任务清单与任务文档一致
    for domain_dir in sorted(p for p in (stage_dir / "任务").iterdir() if p.is_dir()):
        domain = domain_dir.name.split("_")[0]
        overview_doc = domain_dir / f"{domain_dir.name}.md"
        if not overview_doc.is_file():
            continue
        listed = parse_domain_overview(overview_doc)
        for seq, (status, date) in listed.items():
            plan_id = f"{domain}_{seq}"
            report.ok()
            doc = tasks.get(plan_id)
            if doc is None:
                report.fail("硬", "H5", f"域总览列出而任务文档缺失：{plan_id}（{overview_doc.name}）")
                continue
            if (doc.status, doc.date) != (status, date):
                report.fail(
                    "硬", "H5",
                    f"域总览与任务文档不一致：{plan_id} 域总览 {status} / {date}，"
                    f"任务 {doc.status} / {doc.date}",
                )
        for plan_id in sorted(t for t in tasks if t.startswith(f"{domain}_")):
            report.ok()
            if plan_id.split("_")[1] not in listed:
                report.fail("硬", "H5", f"任务文档未登记进域总览：{plan_id}")

    # 计划类
    plan_files = sorted(plan_dir.glob("01_计划_*.md"))
    if not plan_files:
        report.fail("硬", "H6", f"缺少计划文档：{plan_dir}/01_计划_*.md")
        return
    plan_path = plan_files[0]
    plan = parse_plan(plan_path)
    done: dict[str, dict[str, str]] = plan["done"]  # type: ignore[assignment]
    todo: dict[str, dict[str, str]] = plan["todo"]  # type: ignore[assignment]

    # H6：计划两表编号互斥 + 与任务文档一一对应
    for plan_id in sorted(set(done) & set(todo)):
        report.fail("硬", "H6", f"计划编号同时出现在已完成为剩余表：{plan_id}")
    report.ok()
    for plan_id in sorted(set(done) | set(todo)):
        report.ok()
        if plan_id not in tasks:
            report.fail("硬", "H6", f"计划列出而任务文档缺失：{plan_id}")
    for plan_id in sorted(tasks):
        report.ok()
        if plan_id not in done and plan_id not in todo:
            report.fail("硬", "H6", f"任务文档未登记进计划：{plan_id}")

    # H7：工时对齐（任务信息表 == 计划表；任务侧单元格可带「（重估：…）」说明，取前导数字）
    # 部分完成（重开后追加嵌套子任务）的父任务：任务信息表记重估总工时（含未实施子任务），计划已完成表记
    # 已完成部分，二者口径不同、不直接比较；其剩余子任务在计划剩余表按各自工时逐条核对。
    for plan_id, doc in tasks.items():
        if doc.status == "部分完成":
            continue
        row = done.get(plan_id) or todo.get(plan_id)
        if not row:
            continue
        report.ok()
        task_hours = docs_hours(doc.hours)
        plan_hours = docs_hours(row["hours"])
        if task_hours is None or plan_hours is None or task_hours != plan_hours:
            report.fail(
                "硬", "H7",
                f"工时不一致：{plan_id} 任务 {doc.hours}，计划 {row['hours']}",
            )

    # H8：排期窗口格式
    for plan_id, row in sorted(todo.items()):
        report.ok()
        window = row["window"]
        if window.startswith("搁置"):
            continue
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}( ~ \d{4}-\d{2}-\d{2})?", window):
            report.fail("硬", "H8", f"排期窗口格式非法：{plan_id} → {window}")

    # S1：统计数字与明细一致
    stats = plan["stats"]
    if stats:
        report.checks += 1
        if stats != (len(done), len(todo)):
            report.fail(
                "软", "S1",
                f"计划头计数与明细不符：头部 {stats[0]}/{stats[1]}，明细 {len(done)}/{len(todo)}",
            )
    effort = plan["effort"]
    if effort:
        report.checks += 1
        sum_done = sum(int(HOURS_RE.match(r["hours"]).group(1)) for r in done.values() if HOURS_RE.match(r["hours"]))
        sum_todo = sum(int(HOURS_RE.match(r["hours"]).group(1)) for r in todo.values() if HOURS_RE.match(r["hours"]))
        if effort != (sum_done, sum_todo, sum_done + sum_todo):
            report.fail(
                "软", "S1",
                f"计划工时统计与明细不符：头部 {effort}，明细 {(sum_done, sum_todo, sum_done + sum_todo)}",
            )

    # S2：甘特与剩余排期表一致
    gantt: set[str] = plan["gantt"]  # type: ignore[assignment]
    for plan_id in sorted(todo):
        report.ok()
        if plan_id not in gantt:
            report.fail("软", "S2", f"剩余排期表有而甘特缺：{plan_id}")
    for plan_id in sorted(gantt & set(done)):
        report.fail("软", "S2", f"甘特仍含已完成任务节点：{plan_id}")

    # S3：已完成任务的留痕记录齐备（父任务可由嵌套子任务目录承担）
    for plan_id, doc in tasks.items():
        if doc.status != "已完成":
            continue
        report.ok()
        base = doc.path.parent
        has_impl = (base / "实施").is_dir() or any(
            (child / "实施").is_dir() for child in base.iterdir() if child.is_dir()
        )
        if not has_impl:
            report.fail("软", "S3", f"已完成任务缺 实施/ 记录：{plan_id}（{base.name}）")


def main(argv: list[str] | None = None) -> int:
    """入口：逐阶段核对并汇总。"""
    parser = argparse.ArgumentParser(description="需求 / 任务 / 计划 状态一致性核对")
    parser.add_argument("--root", default=".", help="仓库根目录（默认当前目录）")
    parser.add_argument("--stage", default="01_项目骨架", help="阶段目录名（默认 01_项目骨架）")
    parser.add_argument("--all", action="store_true", help="核对全部阶段（含历史阶段，仅供人工参考）")
    parser.add_argument("--strict", action="store_true", help="软提示同样阻断（退出码 1）")
    args = parser.parse_args(argv)

    project_root = Path(args.root).resolve() / "bms文档" / "项目"
    if not project_root.is_dir():
        print(f"未找到阶段目录：{project_root}")
        return 2
    stages = (
        sorted(p for p in project_root.iterdir() if p.is_dir())
        if args.all
        else [project_root / args.stage]
    )
    if args.all:
        print("提示：--all 含历史阶段（准备期），其文档为早期口径，结果仅供人工参考")

    total_hard = 0
    total_soft = 0
    total_checks = 0
    for stage_dir in stages:
        if not stage_dir.is_dir():
            print(f"[{stage_dir.name}] 跳过：目录不存在")
            continue
        report = Report(stage=stage_dir.name)
        check_stage(stage_dir, report)
        total_hard += len(report.hard)
        total_soft += len(report.soft)
        total_checks += report.checks
        print(f"\n[{report.stage}] 检查 {report.checks} 项：硬规则不合规 {len(report.hard)}，软提示 {len(report.soft)}")
        for finding in report.hard + report.soft:
            print(f"  [{finding.level}] {finding.code} {finding.message}")

    print(
        f"\n汇总：检查 {total_checks} 项；硬规则不合规 {total_hard}，软提示 {total_soft}"
    )
    if total_hard or (args.strict and total_soft):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
