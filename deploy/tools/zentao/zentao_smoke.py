# -*- coding: utf-8 -*-
"""禅道 API 冒烟测试（deploy/tools/zentao/zentao_smoke.py）

用途：easysoft/zentao:latest 是滚动镜像，升级后《禅道API使用说明.md》的踩坑结论
可能失效。本脚本对文档踩坑逐条做行为探测，PASS=结论仍成立、FAIL/WARN=行为变化需复核文档。

用法（凭据自动读 deploy/.env 的 ZENTAO_API_*）：
    python zentao_smoke.py                  # 只读检查（不动数据）
    python zentao_smoke.py --with-write     # 含写检查：建测试任务复现创建/删除坑，自动清理
    python zentao_smoke.py --json           # 以 JSON 输出结果

结果分两类：
    [CHECK]  有明确预期的断言（FAIL = 踩坑结论失效，须更新文档）
    [OBSERVE] 行为快照（值变化仅提示复核，不算失败）
"""
import argparse
import datetime
import json
import sys

from zentao_client import ZentaoClient, ZentaoError
import zentao_tasks

RESULTS = []  # [(kind, name, status, detail)]  kind: CHECK/OBSERVE  status: PASS/FAIL/WARN/INFO


def record(kind, name, ok, detail=""):
    status = {True: "PASS", False: "FAIL", None: "WARN"}[ok]
    RESULTS.append((kind, name, status, detail))
    print(f"[{kind:<7}] {status:<4} {name}" + (f" —— {detail}" if detail else ""))


def observe(name, detail):
    RESULTS.append(("OBSERVE", name, "INFO", detail))
    print(f"[OBSERVE] INFO {name} —— {detail}")


# ---------- 只读检查 ----------

def check_read(c):
    # 坑1：Token 头认证可用；Bearer 被拒
    try:
        c.get("/users")
        record("CHECK", "#1 Token 头认证", True)
    except ZentaoError as e:
        record("CHECK", "#1 Token 头认证", False, str(e)[:120])
    import urllib.request
    req = urllib.request.Request(f"{c.base}/users")
    req.add_header("Authorization", f"Bearer {c.get_token()}")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            bearer_ok = resp.status == 200
    except Exception:
        bearer_ok = False
    record("CHECK", "#1 Bearer 应被拒（仍用 Token 头）", not bearer_ok,
           "" if not bearer_ok else "Bearer 竟然通过，认证机制变化")

    # 坑10/16：迭代列表与分页正常
    exs = c.fetch_all("/executions", status="all")
    record("CHECK", "#10 GET /executions?status=all 取全量", isinstance(exs, list) and len(exs) > 0,
           f"共 {len(exs)} 个迭代")
    proj = c.get("/projects/1")
    multiple = int(proj.get("multiple") or 0)
    root_exs = c.fetch_all(f"/projects/1/executions")
    if multiple == 0:
        record("CHECK", "#10 单迭代项目 /projects/:id/executions 只含根执行",
               len(root_exs) <= 1, f"返回 {len(root_exs)} 条（全量 {len(exs)} 条），应只含影子迭代")
    else:
        observe("#10 多迭代项目 /projects/:id/executions",
                f"multiple=1，返回 {len(root_exs)} 条 / 全量 {len(exs)} 条（多迭代模式下正常列出各迭代）")

    # 坑15/16：search=1 服务端过滤与分页
    d = zentao_tasks.search_server(c, limit=10000)
    total, got = d.get("total"), len(d.get("tasks") or [])
    record("CHECK", "#15/#16 search=1 分页取全", got >= (total or 0) > 0, f"total={total} 取回={got}")

    # 坑16：「我的任务」分支分页怪癖仍在
    mine = c.get("/tasks", params={"limit": 10000})
    items = mine.get("tasks") or []
    observe("#16 不带 search=1 的 /tasks 怪癖",
            f"limit=10000 仅返回 {len(items)} 条（total={mine.get('total')}）；"
            + ("怪癖仍在（返回远少于 total）" if len(items) < (mine.get("total") or 0) else "怪癖似乎已消失，请复核文档"))

    # 坑17：assignedTo 是字典
    tasks = d.get("tasks") or []
    if tasks:
        sample = next((t for t in tasks if t.get("assignedTo")), tasks[0])
        at = sample.get("assignedTo")
        is_dict = isinstance(at, dict) and "account" in at
        record("CHECK", "#17 assignedTo 结构", True,
               f"dict（account={at.get('account')}）" if is_dict else f"类型 {type(at).__name__}={at!r}（结构变化请复核）")

    # 坑20：不存在 id 报错不回退（状态码随镜像漂移：曾记 404，2026-08-21 复测为 400）
    try:
        r = c.get("/executions/999999999")
        record("CHECK", "#20 不存在迭代应报错", False,
               f"竟返回 id={r.get('id')} 数据（静默回退范围扩大？）")
    except ZentaoError as e:
        record("CHECK", "#20 不存在迭代应报错（不回退）", True, str(e)[:80])
    closed = [e for e in (root_exs if isinstance(root_exs, list) else []) ]
    all_status = c.get("/executions", params={"status": "all", "limit": 1000})
    closed_ids = [e["id"] for e in (all_status.get("executions") or []) if e.get("status") in ("closed", "done")]
    if closed_ids:
        cid = closed_ids[0]
        try:
            r = c.get(f"/executions/{cid}")
            observe("#20 已关闭迭代回退", f"/executions/{cid} 返回 id={r.get('id')}"
                    + ("（回退仍在）" if r.get("id") != cid else "（不再回退，请复核）"))
        except ZentaoError as e:
            observe("#20 已关闭迭代回退", f"/executions/{cid} 报错：{str(e)[:60]}（不再回退，请复核）")
    else:
        observe("#20 已关闭迭代回退", "当前无已关闭迭代，跳过")


# ---------- 写检查（自动清理） ----------

def check_write(c):
    today = datetime.date.today().isoformat()
    ex_id = _default_execution(c)
    tag = f"smoke-{datetime.datetime.now():%m%d%H%M%S}"

    # 坑4：缺 estStarted/deadline 是否静默失败（行为随镜像漂移：2026-08-21 复测竟能建成）
    zentao_tasks.batch_create(c, ex_id, [{"name": f"{tag}-nodate", "type": "devel"}])
    after = zentao_tasks.list_(c, execution=ex_id)
    leaked = [t for t in after if t["name"].startswith(tag) and t["name"].endswith("-nodate")]
    if leaked:
        detail = f"缺日期竟建成 id={leaked[0]['id']}（estStarted={leaked[0].get('estStarted')!r}, " \
                 f"deadline={leaked[0].get('deadline')!r}）；与文档「静默失败」不符，请复核"
        zentao_tasks.web_delete(c, leaked[0]["id"])
        observe("#4 缺日期 batchCreate", detail + "；漏网测试任务已自动清理")
    else:
        observe("#4 缺日期 batchCreate", "未建成（静默失败仍在，与文档一致）")

    # 正常建父任务（带齐必填）
    created = zentao_tasks.batch_create(c, ex_id, [{
        "name": f"{tag}-parent", "type": "devel", "pri": 3, "estimate": 1,
        "estStarted": today, "deadline": today,
    }])
    parent_id = created[0]["id"] if created else None
    if not parent_id:
        record("CHECK", "#3 batchCreate 创建任务", False, "正常参数也未建成，创建链路异常")
        return
    record("CHECK", "#3 batchCreate 创建任务", True, f"父任务 id={parent_id}")

    # 坑11/12：子任务 parent 走 URL 参数、body 不接受 assignedTo
    sub = zentao_tasks.batch_create(c, ex_id, [{
        "name": f"{tag}-child", "type": "devel", "estimate": 1,
        "estStarted": today, "deadline": today, "assignedTo": c.account,
    }], parent=parent_id)
    if sub:
        t = zentao_tasks.get(c, sub[0]["id"])
        record("CHECK", "#11 子任务 parent=URL 参数", int(t.get("parent") or 0) == int(parent_id),
               f"parent={t.get('parent')}（应为 {parent_id}）")
        observe("#12 body assignedTo 是否被忽略",
                f"建出 assignedTo={t.get('assignedTo')}"
                + ("（仍被忽略，与文档一致）" if not (t.get("assignedTo") or {}).get("account") else "（竟能直接指派，请复核文档）"))
    else:
        record("CHECK", "#11 子任务创建", False, "子任务未建成")
        t = None

    # 坑13：REST DELETE 是否生效（bug 修复与否属行为快照）→ Web 删除必须生效（契约）
    c.delete(f"/tasks/{parent_id}")
    still = zentao_tasks.get(c, parent_id)
    observe("#13 REST DELETE /tasks/:id",
            f"deleted={still.get('deleted')}"
            + ("（bug 仍在，与文档一致）" if not still.get("deleted") else "（竟真删了？请复核文档）"))
    r = zentao_tasks.web_delete(c, parent_id)   # 实测：父任务软删；子任务是否级联有条件性（见文档 7.6）
    ok = all(x["success"] and x["deleted"] for x in r["results"])
    record("CHECK", "#13 Web 会话删除父任务生效", ok, json.dumps(r["results"], ensure_ascii=False)[:160])
    if sub:
        sub_del = zentao_tasks.get(c, sub[0]["id"]).get("deleted")
        observe("#13 父任务删除对子任务的级联",
                f"子任务 deleted={sub_del}（快照：wait 态曾见级联、closed 态曾见不级联，变化请复核文档 7.6）")
        if not sub_del:
            zentao_tasks.web_delete(c, sub[0]["id"])   # 未级联则补删


def _default_execution(c):
    """取第一个进行中/未关闭的迭代做写检查容器（默认 M0=3）。"""
    exs = c.fetch_all("/executions", status="all")
    for e in exs:
        if e.get("status") in ("wait", "doing"):
            return e["id"]
    raise SystemExit("没有可用的未关闭迭代，写检查中止")


def main():
    ap = argparse.ArgumentParser(description="禅道 API 冒烟测试（镜像升级后复核踩坑结论）")
    ap.add_argument("--with-write", dest="with_write", action="store_true",
                    help="含写检查：会创建并删除测试任务（默认只读）")
    ap.add_argument("--json", dest="as_json", action="store_true", help="JSON 输出")
    args = ap.parse_args()

    c = ZentaoClient()
    print(f"目标：{c.url}\n")
    check_read(c)
    if args.with_write:
        print()
        check_write(c)

    n_fail = sum(1 for k, _, s, _ in RESULTS if s == "FAIL")
    n_warn = sum(1 for _, _, s, _ in RESULTS if s == "WARN")
    print(f"\n汇总：{len(RESULTS)} 项，FAIL={n_fail} WARN={n_warn}")
    print("FAIL/WARN = 行为与《禅道API使用说明.md》记录不符，请按提示复核并更新文档变更记录。")
    if args.as_json:
        print(json.dumps([{"kind": k, "name": n, "status": s, "detail": d}
                          for k, n, s, d in RESULTS], ensure_ascii=False, indent=2))
    sys.exit(1 if n_fail else 0)


if __name__ == "__main__":
    main()
