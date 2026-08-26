# -*- coding: utf-8 -*-
"""禅道 → 文档 同步（scripts/tools/zentao/zentao_sync_pull.py）

把禅道任务的状态/完成日期读回，回写到需求/任务文档：
    - 需求文档元信息行：状态 / 完成日期
    - 任务文档信息表：状态 / 完成日期

状态口径（禅道 → 文档，保留文档侧更细语义）：
    wait  → 未开始（文档原为「搁置」则保留搁置）
    doing → 进行中（文档原为「部分完成」则保留部分完成）
    done / closed → 已完成
    pause → 搁置　cancel → 已取消

用法：
    python zentao_sync_pull.py --stage 00_准备期 --dry-run    # 只读禅道+打印对照，不改文档
    python zentao_sync_pull.py --stage 00_准备期               # 回写文档
"""
import argparse
import re

import zentao_tasks as T
from zentao_client import ZentaoClient

from zentao_sync_common import (
    ROOT, base_status, list_child_task_files, list_req_files, parse_req_file,
    parse_task_file, stage_paths,
)

# 禅道任务状态全集：wait/doing/done/pause/cancel/closed（22.5 实测）；
# finished/canceled 为历史写法容错，正常读不到。
ZT2DOC = {
    "wait": "未开始",
    "doing": "进行中",
    "done": "已完成",
    "finished": "已完成",
    "closed": "已完成",
    "pause": "搁置",
    "cancel": "已取消",
    "canceled": "已取消",
}


def pull_status(doc_status: str, zt_status: str) -> str:
    """禅道状态 → 文档状态；文档侧更细的「搁置/部分完成」在粗态下保留。"""
    base_doc = base_status(doc_status)
    if zt_status == "wait":
        return "搁置" if base_doc == "搁置" else "未开始"
    if zt_status == "doing":
        return "部分完成" if base_doc == "部分完成" else "进行中"
    return ZT2DOC.get(zt_status, zt_status)


def find_task(client, task, execution=None):
    """查禅道任务：优先回填 id，否则按（父任务+名称）。"""
    if task.task_id:
        try:
            return T.get(client, int(task.task_id))
        except Exception:
            return None
    tasks = T.list_(client, execution=execution) if execution else T.list_(client)
    for t in tasks:
        if (t.get("parent") or 0) == task.parent_task and t.get("name", "").strip() == task.title.strip():
            return t
    return None


def update_req_meta(path: str, number: str, status: str, date: str) -> bool:
    p = ROOT / path
    text = p.read_text(encoding="utf-8")
    m = re.search(r"##\s+\d+\.\s+需求\s+" + re.escape(number) + r"：[^\n]*\n\n([^\n]+)", text)
    if not m:
        return False
    line = m.group(1)
    new_line = re.sub(r"(状态：)[^　|]+", r"\g<1>" + status, line)
    new_line = re.sub(r"(完成日期：)[^　|]+", r"\g<1>" + date, new_line)
    if new_line == line:
        return False
    p.write_text(text[:m.start(1)] + new_line + text[m.end(1):], encoding="utf-8")
    return True


def update_task_table(path: str, status: str, date: str) -> bool:
    p = ROOT / path
    text = p.read_text(encoding="utf-8")
    changed = False
    for label in ("状态", "完成日期"):
        val = date if label == "完成日期" else status
        m = re.search(r"^(\|\s*" + label + r"\s*\|\s*)[^|\n]*(\|\s*)$", text, flags=re.M)
        if m:
            # 值与右侧竖线之间保留一个空格（g2 原样可能吞掉前置空格，导致「已完成|」）
            new = text[:m.start()] + m.group(1) + val + " " + m.group(2) + text[m.end():]
            if new != text:   # 内容无变化不计更新（幂等）
                changed = True
            text = new
    if changed:
        p.write_text(text, encoding="utf-8")
    return changed


def run(args) -> bool:
    sp = stage_paths(args.stage)
    tasks, reqs = {}, {}
    for f in list_child_task_files(sp["task"]):
        t = parse_task_file(f)
        tasks[t.number] = t
    for f in list_req_files(sp["req"]):
        for r in parse_req_file(f):
            reqs[r.number] = r

    client = ZentaoClient()
    print(f"stage={args.stage}  任务 {len(tasks)} 条   dry-run={args.dry_run}")
    updated = 0
    for number in sorted(tasks):
        task, req = tasks[number], reqs.get(number)
        zt = find_task(client, task, args.execution)
        if not zt:
            print(f"[{number}] 禅道无此任务（未建？）— 文档状态={task.status}")
            continue
        zt_status = zt.get("status")
        status = pull_status(task.status, zt_status)
        # 已完成（done/closed）取完成日期：done 有 finishedDate；closed 态 finishedDate 被置空，用 deadline 兜底
        if zt_status in ("done", "closed"):
            date = zt.get("finishedDate") or zt.get("deadline") or "—"
        else:
            date = "—"
        mark = "　[dry-run]" if args.dry_run else ""
        print(f"[{number}] 禅道 {zt_status} → 文档 {status}，完成日期 {date}{mark}")
        if not args.dry_run:
            if req and update_req_meta(req.file, number, status, date):
                updated += 1
            if update_task_table(task.file, status, date):
                updated += 1
    if args.dry_run:
        print("dry-run：未改文档。")
    else:
        print(f"回写完成（{updated} 处字段更新）。")
    return True


def main():
    ap = argparse.ArgumentParser(description="禅道 → 文档 同步")
    ap.add_argument("--stage", default="00_准备期", help="阶段目录名（默认 00_准备期）")
    ap.add_argument("--execution", type=int, default=3, help="禅道迭代 id（默认 3=M0）")
    ap.add_argument("--dry-run", action="store_true", help="只读禅道+打印对照，不改文档")
    args = ap.parse_args()
    ok = run(args)
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
