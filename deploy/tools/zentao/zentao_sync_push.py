# -*- coding: utf-8 -*-
"""文档 → 禅道 同步（deploy/tools/zentao/zentao_sync_push.py）

把 文档/项目/{stage}/ 的需求/任务/计划 同步到禅道产品（story）+ 迭代（任务）：
    1. 每条需求建/更 1 个 story（title/pri/spec），回填 story id
    2. 每条任务建/更 1 个子任务（挂父任务、挂需求 story、estStarted/deadline、desc、状态流转、指派），回填任务 id
    3. 排期：计划「已完成表」完成日期 → finish 的 finishedDate；「剩余排期表」排期窗口 → estStarted/deadline

幂等：
    - story/task 优先用文档已回填的 id（req.story_id / task.task_id）；
    - 未建则按「产品内 title 精确匹配 / 父任务+name 精确匹配」查已有，命中则复用并回填；未命中才创建。

用法：
    python zentao_sync_push.py --stage 00_准备期 --dry-run    # 只解析+打印计划，不写禅道、不改文档
    python zentao_sync_push.py --stage 00_准备期               # 实跑（建/更 story+任务、流转状态、回填 id）
    python zentao_sync_push.py --stage 00_准备期 --assign minjian
"""
import argparse

import zentao_stories as S
import zentao_tasks as T
from zentao_client import ZentaoClient

from zentao_sync_common import (
    Plan, base_status, build_desc, build_spec, list_child_task_files, list_plan_files,
    list_req_files, parse_finished, parse_plan_file, parse_req_file, parse_task_file,
    stage_paths, backfill_req_task_id, backfill_story_id, backfill_task_id, zt_status,
)

FALLBACK_DATE = "2026-09-28"   # M1 锚点：缺 estStarted/deadline 或搁置时的占位


# ---------- 索引 ----------

def index_stories(client, product):
    """产品内 story：title(strip) → story。"""
    idx = {}
    for s in S.list_(client, product=product):
        idx[s.get("title", "").strip()] = s
    return idx


def index_tasks(client, execution):
    """迭代内任务：(parent, name strip) → task。"""
    idx = {}
    for t in T.list_(client, execution=execution):
        idx[(t.get("parent") or 0, t.get("name", "").strip())] = t
    return idx


def resolve_dates(task, plan):
    """由状态+计划推导 (estStarted, deadline)。

    已完成：finishedDate=完成日，realStarted=完成日-1 天（禅道要求完成日严格晚于开始日）。
    其余：排期窗口；搁置/缺失用 M1 占位。
    """
    from datetime import datetime, timedelta
    if base_status(task.status) == "已完成":
        d = parse_finished(task.finished) or (plan.done_date or "") or FALLBACK_DATE
        try:
            start = (datetime.strptime(d, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")
        except ValueError:
            start = d
        return start, d
    est = plan.est_started or FALLBACK_DATE
    ddl = plan.deadline or est
    return est, ddl


# ---------- 建/更 story ----------

def ensure_story(client, product, req, story_idx, dry_run):
    """返回 story id；req.story_id 已回填则直接复用，否则查已有/创建。"""
    if req.story_id:
        return int(req.story_id)
    hit = story_idx.get(req.title.strip())
    if hit:
        return hit["id"]
    spec = build_spec(req)
    if dry_run:
        print(f"    [dry-run] 建 story：{req.title}（pri={req.pri}，spec {len(spec)} 字）")
        return 0
    resp = S.create(client, product, req.title, pri=req.pri, category="feature", spec=spec)
    sid = resp.get("id") if isinstance(resp, dict) else None
    if sid is None and isinstance(resp, dict):
        sid = resp.get("story") or resp.get("id")
    return sid


def sync_story(client, product, req, story_idx, dry_run):
    sid = ensure_story(client, product, req, story_idx, dry_run)
    if dry_run or not sid:
        return sid
    # 更新 title/pri/spec（幂等，值一致也无害）
    spec = build_spec(req)
    S.update(client, sid, title=req.title, pri=req.pri, spec=spec)
    return sid


# ---------- 建/更 任务 ----------

def ensure_task(client, execution, task, est_s, ddl, task_idx, dry_run):
    """返回 (task_id, created_bool)。task.task_id 已回填则复用；否则查父任务下同名/创建。"""
    if task.task_id:
        return int(task.task_id), False
    hit = task_idx.get((task.parent_task, task.title.strip()))
    if hit:
        return hit["id"], False
    if dry_run:
        print(f"    [dry-run] 建任务（父 {task.parent_task}）：{task.title}（est={est_s}~{ddl}，{task.estimate}h）")
        return 0, True
    created = T.create(client, execution, task.title, estimate=task.estimate,
                       est_started=est_s, deadline=ddl, pri=2, type_="devel",
                       parent=task.parent_task)
    if created:
        return created[0].get("id"), True
    return None, True


def apply_status(client, task_id, task, est_s, ddl, dry_run):
    """按文档状态流转禅道任务：已完成→start+finish+close；进行中/部分完成→start；其余保持 wait。"""
    base = base_status(task.status)
    target = zt_status(task.status)
    if dry_run:
        print(f"    [dry-run] 状态 → {base}（禅道 {target}）")
        return
    if task_id is None:
        return
    left = task.estimate or 1
    try:
        if base == "已完成":
            cur = (T.get(client, task_id) or {}).get("status")
            # 禅道状态：wait -> doing -> done -> closed；done 为完成态
            if cur not in ("done", "closed"):
                if cur == "wait":
                    T.start(client, task_id, left=left, real_started=est_s)
                T.finish(client, task_id, consumed=left, real_started=est_s,
                         finished_date=ddl)
            if (T.get(client, task_id) or {}).get("status") != "closed":
                client.put(f"/tasks/{task_id}", body={"status": "closed"})
        elif base in ("进行中", "部分完成"):
            cur = (T.get(client, task_id) or {}).get("status")
            if cur == "wait":
                T.start(client, task_id, left=left, real_started=est_s)
        # 未开始 / 搁置：保持 wait
    except Exception as e:  # 单任务状态流转失败不阻断整体
        print(f"    [warn] 任务 {task_id} 状态流转失败：{e}")


def sync_task(client, execution, task, plan, task_idx, dry_run, assign, sid):
    est_s, ddl = resolve_dates(task, plan)
    tid, created = ensure_task(client, execution, task, est_s, ddl, task_idx, dry_run)
    if dry_run or not tid:
        return tid
    # 新建任务先指派（此时仍 wait/open；已完成的 85~90 已指派，跳过）
    if created and assign:
        try:
            T.assign(client, tid, assign)
        except Exception as e:
            print(f"    [warn] 任务 {tid} 指派失败：{e}")
    # 更新 desc / estStarted / deadline / estimate / story（story 字段即任务-需求关联，
    # 22.5 PUT /tasks/:id 字段白名单含 story，重复设置同值幂等）
    fields = dict(desc=build_desc(task), estStarted=est_s, deadline=ddl, estimate=task.estimate)
    if sid:
        fields["story"] = sid
    T.update(client, tid, **fields)
    apply_status(client, tid, task, est_s, ddl, dry_run)
    return tid


# ---------- 主流程 ----------

def run(args):
    sp = stage_paths(args.stage)
    reqs, tasks, plan = {}, {}, {}
    for f in list_req_files(sp["req"]):
        for r in parse_req_file(f):
            reqs[r.number] = r
    for f in list_child_task_files(sp["task"]):
        t = parse_task_file(f)
        tasks[t.number] = t
    for f in list_plan_files(sp["plan"]):
        plan.update(parse_plan_file(f))

    numbers = sorted(set(reqs) & set(tasks))
    missing = sorted(set(reqs) ^ set(tasks))
    if missing:
        print(f"[warn] 需求与任务编号不一致（跳过）：{missing}")
    parents = sorted({t.parent_task for t in tasks.values() if t.parent_task})
    print(f"stage={args.stage}  需求 {len(reqs)} 条 / 任务 {len(tasks)} 条 / 计划 {len(plan)} 项")
    print(f"父任务：{parents}   产品={args.product}   迭代={args.execution}   dry-run={args.dry_run}")

    client = None if args.dry_run else ZentaoClient()
    story_idx = index_stories(client, args.product) if not args.dry_run else {}
    task_idx = index_tasks(client, args.execution) if not args.dry_run else {}

    ok, fail = 0, 0
    for number in numbers:
        req, task, p = reqs[number], tasks[number], plan.get(number, Plan())
        base = base_status(req.status)
        print(f"\n[{number}] {req.title}  （{base}）")
        try:
            sid = sync_story(client, args.product, req, story_idx, args.dry_run)
            tid = sync_task(client, args.execution, task, p, task_idx, args.dry_run, args.assign, sid)
            if not args.dry_run:
                if sid:
                    backfill_story_id(req.file, number, sid)
                if tid and (not task.task_id or int(task.task_id) != tid):
                    backfill_task_id(task.file, number, tid, task.parent_task)
                    backfill_req_task_id(req.file, number, tid, task.parent_task)
            ok += 1
        except Exception as e:
            print(f"    [error] {number} 同步失败：{e}")
            fail += 1

    print(f"\n汇总：成功 {ok} / 失败 {fail}（共 {len(numbers)} 条）")
    if args.dry_run:
        print("dry-run 模式：未写禅道、未改文档。")
    return fail == 0


def main():
    ap = argparse.ArgumentParser(description="文档 → 禅道 同步")
    ap.add_argument("--stage", default="00_准备期", help="阶段目录名（默认 00_准备期）")
    ap.add_argument("--product", type=int, default=1, help="禅道产品 id（默认 1）")
    ap.add_argument("--execution", type=int, default=3, help="禅道迭代 id（默认 3=M0）")
    ap.add_argument("--assign", default="minjian", help="新建任务指派账号（默认 minjian；空串=不指派）")
    ap.add_argument("--dry-run", action="store_true", help="只解析+打印，不写禅道、不改文档")
    args = ap.parse_args()
    ok = run(args)
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
