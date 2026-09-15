#!/usr/bin/env python3
"""阶段末复盘清单自动核对（《项目规划说明》§25.3 L1 执行链）。

**只读脚本**：逐项核对阶段收口状态，输出「通过 / 不通过 + 证据」，不修改任何文档；
发现不一致只报告，由人决定处置（异常项处理留痕见任务实施记录 §4 / §6）。

核对清单（九项）：

1. 三类文档状态一致（复用 `check-docs/check-status.py`）
2. 基座自检通过（复用 `base-check/check-base.py`）
3. 验收门禁表结论齐备（10 行 / 5 列 / 结论取值合法 / 达标项有证据索引）
4. 阶段残留为 0（需求与任务文档无「未开始 / 进行中 / 部分完成」）
5. 遗留项已登记（计划「后续阶段待办」节非空）
6. 报告与 README 就位（报告章节齐备；四份 README 关键命令与导航存在）
7. 记录齐备（已完成任务目录存在 `实施/`，有嵌套时容许子目录承担）
8. Kiwi 用例编号引用（任务测试记录均含 Kiwi 字段）
9. 架构重评触发条件复核（打印微服务 T1~T8 与微前端 F1~F8 供人工判断；档案《微服务 · 10 项目评估》《微前端 · 06 项目评估》）

用法::

    python3 scripts/tools/governance/review_stage.py
    python3 scripts/tools/governance/review_stage.py --stage 01_项目骨架

退出码：0 = 全部通过；1 = 存在不通过项（逐项打印）。
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

STATUSES_DONE = {"已完成"}
STATUS_LEGAL = {"未开始", "进行中", "部分完成", "已完成", "搁置"}
CONCLUSIONS = {"达标", "进行中", "不达标"}
REQ_META_RE = re.compile(r"^优先级：\S+（[^）]*）\u3000\|\u3000状态：(\S+)\u3000\|\u3000完成日期：\S+\s*$")
TASK_META_RE = re.compile(r"^\|\s*状态\s*\|\s*(\S+?)\s*\|")
ROW_RE = re.compile(r"^\|(?P<cells>.*)\|\s*$")

# 架构重评触发条件（微服务《10 项目评估》§7 T1~T8；微前端《06 项目评估》§7 F1~F8；人工判断，脚本只提醒不判定）
MICROSERVICE_TRIGGERS = (
    "T1 团队规模（≥ 5~8 人且需独立交付节奏）",
    "T2 领域边界稳定（≥ 2~3 个大阶段未调整）",
    "T3 发布瓶颈（单体发布风险/频率成为瓶颈）",
    "T4 资源画像（某模块独立伸缩收益可量化）",
    "T5 故障隔离（模块级故障拖垮全局且进程内隔离无法覆盖）",
    "T6 隔离/合规（物理隔离要求且独立服务出口不满足）",
    "T7 运维能力（有专职平台/运维角色且 CD/可观测/编排达到前提）",
    "T8 性能证据（瓶颈在非可拆模块内部）",

)

MICRO_FRONTEND_TRIGGERS = (
    "F1 团队规模（前端/产品出现 ≥ 2~3 个独立交付节奏的团队）",
    "F2 技术异构（确有团队需要不同框架/技术栈或旧栈接续）",
    "F3 独立发布（产品前端需独立于平台发版且构建期合并无法满足）",
    "F4 性能/体积（首屏体积或构建时长成为瓶颈）",
    "F5 隔离/嵌入（需嵌入第三方不可信前端，先评估 iframe）",
    "F6 多形态差异（PC/H5/大屏/门户共存，先评估 BFF）",
    "F7 治理就绪（设计系统、体积预算、按模块归因与契约测试就绪）",
    "F8 试点验证（Module Federation 试点证明收益 > 代价）",
)


@dataclass
class Check:
    """一项复盘结果。"""

    name: str
    passed: bool
    evidence: str


def split_row(line: str) -> list[str] | None:
    """切分 Markdown 表格行（表头分隔行返回 None）。"""
    match = ROW_RE.match(line)
    if not match:
        return None
    cells = [cell.strip() for cell in match.group("cells").split("|")]
    if all(cell and set(cell) <= set("-: ") for cell in cells):
        return None
    return cells


def read_section(text: str, heading_re: str) -> str:
    """截取匹配 heading 的二级标题到下一个二级标题之间的正文。"""
    lines = text.splitlines()
    start = None
    for idx, line in enumerate(lines):
        if re.search(heading_re, line):
            start = idx + 1
            break
    if start is None:
        return ""
    for idx in range(start, len(lines)):
        if lines[idx].startswith("## "):
            return "\n".join(lines[start:idx])
    return "\n".join(lines[start:])


def run_script(root: Path, rel: str) -> tuple[bool, str]:
    """以 subprocess 复用既有校验脚本（不重复实现）。"""
    proc = subprocess.run([sys.executable, rel], cwd=root, capture_output=True, text=True, check=False, timeout=600)
    tail = [line for line in (proc.stdout or "").splitlines() if line.strip()][-1:] or [""]
    return proc.returncode == 0, f"`{rel}` 退出码 {proc.returncode}；末行：{tail[0][:90]}"


def check_gate_table(stage_dir: Path) -> Check:
    """门禁表：10 行 / 5 列 / 结论合法 / 达标有证据。"""
    overview = next(iter(sorted((stage_dir / "需求").glob("00_需求_*.md"))), None)
    if overview is None:
        return Check("验收门禁表结论齐备", False, "未找到需求总览")
    rows = []
    for line in read_section(overview.read_text(encoding="utf-8"), r"^## \d+\. .*验收门禁").splitlines():
        cells = split_row(line)
        if not cells or len(cells) != 5:
            continue
        conclusion = cells[3].split("（")[0].strip()  # 允许括注，如「达标（占位口径）」
        if conclusion in CONCLUSIONS:
            rows.append(cells + [conclusion])
    problems = [f"「{row[0]}」结论 {row[5]} 缺证据索引" for row in rows if row[5] == "达标" and not row[4]]
    ok = len(rows) == 10 and not problems
    detail = f"{len(rows)} 行（期望 10）"
    if problems:
        detail += "；" + "；".join(problems)
    return Check("验收门禁表结论齐备", ok, detail)


def check_residue(stage_dir: Path) -> Check:
    """阶段残留：需求与任务文档不得停在未开始 / 进行中 / 部分完成。"""
    pending: list[str] = []
    for doc in sorted((stage_dir / "需求").glob("*.md")):
        if doc.name.startswith("00_"):
            continue
        for line in doc.read_text(encoding="utf-8").splitlines():
            meta = REQ_META_RE.match(line)
            if meta and meta.group(1) not in STATUSES_DONE and meta.group(1) in STATUS_LEGAL:
                pending.append(f"{doc.name}:{meta.group(1)}")
    for doc in sorted((stage_dir / "任务").rglob("*.md")):
        if doc.parent.name in ("设计", "实施", "测试"):
            continue
        for line in doc.read_text(encoding="utf-8").splitlines():
            meta = TASK_META_RE.match(line)
            if meta and meta.group(1) not in STATUSES_DONE and meta.group(1) in STATUS_LEGAL:
                pending.append(f"{doc.name}:{meta.group(1)}")
    return Check(
        "阶段残留为 0（需求 / 任务全部已完成）",
        not pending,
        f"残留 {len(pending)} 项" + ("：" + "；".join(pending[:6]) if pending else ""),
    )


def check_deferred(stage_dir: Path) -> Check:
    """遗留项：计划「后续阶段待办」节非空。"""
    plan = next(iter(sorted((stage_dir / "计划").glob("01_计划_*.md"))), None)
    if plan is None:
        return Check("遗留项已登记", False, "未找到计划文档")
    section = read_section(plan.read_text(encoding="utf-8"), r"^### \d+\.\d+ 后续阶段待办")
    rows = [split_row(line) for line in section.splitlines()]
    # 排除表头行（首列为「待办」），只统计待办明细
    count = sum(1 for cells in rows if cells and cells[0] not in ("待办", "—"))
    return Check("遗留项已登记", count >= 10, f"计划「后续阶段待办」{count} 条")


def check_deliverables(root: Path, stage_dir: Path) -> Check:
    """报告与 README 就位（章节 + 关键命令 + 导航）。"""
    problems: list[str] = []
    report = stage_dir / "01_测试报告_项目骨架.md"
    if not report.is_file():
        problems.append("缺测试报告")
    else:
        text = report.read_text(encoding="utf-8")
        for heading in ("用例执行统计", "缺陷统计", "覆盖率", "风险与遗留项", "复盘", "附录"):
            if heading not in text:
                problems.append(f"报告缺「{heading}」")
    readme_expect = {
        "README.md": ["app.main:create_app --factory", "01_测试报告_项目骨架.md", "npm run dev"],
        "backend/README.md": ["uv run uvicorn", "文档导航", "check-status.py"],
        "frontend/README.md": ["npm run dev", "文档导航", "5173"],
        "frontend-mobile/README.md": ["npm run dev", "文档导航", "5174"],
    }
    for rel, needles in readme_expect.items():
        path = root / rel
        if not path.is_file():
            problems.append(f"缺 {rel}")
            continue
        text = path.read_text(encoding="utf-8")
        missing = [needle for needle in needles if needle not in text]
        if missing:
            problems.append(f"{rel} 缺 {missing}")
    return Check(
        "报告与 README 就位",
        not problems,
        "；".join(problems) if problems else "报告章节齐备；四份 README 关键命令与导航齐备",
    )


def check_records(stage_dir: Path) -> Check:
    """记录齐备：已完成任务目录存在 实施/（父任务可由嵌套子任务承担）。"""
    missing: list[str] = []
    task_root = stage_dir / "任务"
    for domain_dir in sorted(p for p in task_root.iterdir() if p.is_dir()):
        for task_dir in sorted(p for p in domain_dir.iterdir() if p.is_dir()):
            doc = next(iter(task_dir.glob("*.md")), None)
            if doc is None:
                continue
            status = next(
                (
                    m.group(1)
                    for line in doc.read_text(encoding="utf-8").splitlines()
                    if (m := TASK_META_RE.match(line))
                ),
                "",
            )
            if status != "已完成":
                continue
            has_impl = (task_dir / "实施").is_dir() or any(
                (child / "实施").is_dir() for child in task_dir.iterdir() if child.is_dir()
            )
            if not has_impl:
                missing.append(task_dir.name)
    return Check(
        "记录齐备（已完成任务有实施记录）",
        not missing,
        f"缺 {len(missing)} 项" + ("：" + "、".join(missing[:5]) if missing else ""),
    )


def check_kiwi(stage_dir: Path) -> Check:
    """Kiwi 用例编号引用：任务测试记录均含 Kiwi 字段。"""
    missing: list[str] = []
    for record in sorted((stage_dir / "任务").rglob("测试/*.md")):
        if "Kiwi" not in record.read_text(encoding="utf-8"):
            missing.append(record.name)
    return Check(
        "Kiwi 用例编号引用齐备",
        not missing,
        f"缺 {len(missing)} 份" + ("：" + "、".join(missing[:5]) if missing else ""),
    )


def check_review_triggers() -> Check:
    """架构重评触发条件提醒：打印微服务 T1~T8 与微前端 F1~F8 供人工逐条判断（脚本不作自动判定）。"""
    return Check(
        "架构重评触发条件复核（人工）",
        True,
        "T1~T8（微服务）与 F1~F8（微前端）见知识档案对应评估篇；本项为提醒，不自动判定",
    )


def main(argv: list[str] | None = None) -> int:
    """入口：跑九项复盘清单并汇总。"""
    parser = argparse.ArgumentParser(description="阶段末复盘清单自动核对（只读）")
    parser.add_argument("--stage", default="01_项目骨架", help="阶段目录名（默认 01_项目骨架）")
    parser.add_argument("--root", default=".", help="仓库根目录（默认当前目录）")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    stage_dir = root / "bms文档" / "项目" / args.stage
    if not stage_dir.is_dir():
        print(f"未找到阶段目录：{stage_dir}")
        return 2

    ok_status, evidence_status = run_script(root, "scripts/tools/check-docs/check-status.py")
    ok_base, evidence_base = run_script(root, "scripts/tools/base-check/check-base.py")
    checks = [
        Check("三类文档状态一致", ok_status, evidence_status),
        Check("基座自检通过", ok_base, evidence_base),
        check_gate_table(stage_dir),
        check_residue(stage_dir),
        check_deferred(stage_dir),
        check_deliverables(root, stage_dir),
        check_records(stage_dir),
        check_kiwi(stage_dir),
        check_review_triggers(),
    ]

    print(f"== 阶段末复盘清单（{args.stage}）==")
    for idx, item in enumerate(checks, 1):
        print(f"[{idx}/{len(checks)}] {'通过' if item.passed else '不通过'} {item.name}：{item.evidence}")
    failed = [item for item in checks if not item.passed]
    print(f"\n汇总：{len(checks) - len(failed)}/{len(checks)} 通过" + ("；不通过项见上" if failed else "（全部通过）"))
    print("\n架构重评触发条件（逐条人工判断）：")
    print("微服务（见知识档案《微服务 · 10 项目评估》§7）：")
    for trigger in MICROSERVICE_TRIGGERS:
        print(f"  - {trigger}")
    print("微前端（见知识档案《微前端 · 06 项目评估》§7）：")
    for trigger in MICRO_FRONTEND_TRIGGERS:
        print(f"  - {trigger}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
