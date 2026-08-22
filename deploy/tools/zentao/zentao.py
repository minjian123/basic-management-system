# -*- coding: utf-8 -*-
"""禅道 API 命令行工具（BMS 项目 · deploy/tools/zentao/zentao.py）

用法（凭据默认读 deploy/.env 的 ZENTAO_API_*，可 --account/--password/--url 覆盖）：
    python zentao.py token
    python zentao.py products list
    python zentao.py products create --name "BMS 基础管理系统" --code bms
    python zentao.py projects list
    python zentao.py projects create --name "BMS 开发" --type scrum --begin 2026-08-24 --end 2027-09-20 --products 1
    python zentao.py executions list --project 1
    python zentao.py executions create --project 1 --name "M0 启动就绪" --begin 2026-08-24 --end 2026-09-07
    python zentao.py stories list --product 1
    python zentao.py stories list --product 1 --brief     # 需求摘要输出（每条一行）
    python zentao.py stories create --product 1 --title "用户管理" --pri 2 --category feature --spec "用户增删改查"
    python zentao.py stories delete --id 5         # REST 删除（22.5 已验证；Web 删除需 confirm=yes 备用）
    python zentao.py users create --user-account zhangsan --user-password Zhang_123 --realname "张三" --gender m
    python zentao.py users delete --id 2
    python zentao.py tasks list --execution 3
    python zentao.py tasks list --execution 3 --brief   # 摘要输出（每任务一行，避免全量 JSON 爆屏）
    python zentao.py tasks search --name 接口                       # 客户端过滤：按名称模糊查（全局）
    python zentao.py tasks search --assigned-to minjian --status doing   # 客户端过滤：指派人+状态
    python zentao.py tasks search --parent 1                        # 客户端过滤：某父任务下的子任务
    python zentao.py tasks search --deadline-from 2026-09-01 --deadline-to 2026-09-30
    python zentao.py tasks search --server --name 接口              # 22.5 服务端过滤（name/assigned-to/status/pri）
    python zentao.py tasks search --server --assigned-to minjian --status doing --limit 50 --order id_desc
    python zentao.py tasks search --server --merge-children        # 子任务并入父任务
    python zentao.py stories search --product 1 --name 用户         # 需求（name 匹配 title）
    python zentao.py stories list --product 1 --browse-type closedstory   # 22.5 服务端 browseType 预筛
    python zentao.py users list --full                              # 22.5 用户全字段（full=1）
    python zentao.py products search --name BMS
    python zentao.py tasks batch-create --execution 3 --file tasks.json
    python zentao.py tasks create --execution 3 --name "接口测试" --estimate 16 --begin 2026-08-24 --end 2026-09-07 --to minjian
    python zentao.py tasks create --execution 3 --parent 1 --name "子任务" --estimate 4 --begin 2026-08-24 --end 2026-09-07 --to minjian
    python zentao.py tasks update --id 1 --pri 1
    python zentao.py tasks update --id 1 --desc "单行描述"
    python zentao.py tasks update --id 1 --desc-file desc.txt    # 多行描述走文件（优先于 --desc）
    python zentao.py tasks assign --id 1 --to minjian
    python zentao.py tasks web-delete --id 1          # 经 Web 会话删除（REST delete 有 bug 用不了）
    python zentao.py tasks web-delete --ids 82 83 84  # 批量删除（复用同一登录会话）
    python zentao.py stories web-delete --id 5        # 通用 Web 删除（story/product/project/execution 同）
    python zentao.py tasks start --id 1
    python zentao.py tasks finish --id 1 --consumed 16
    python zentao.py tasks close --id 1
    python zentao.py users list

tasks.json 格式（batch-create）：[{"name": "...", "estimate": 16, "estStarted": "2026-08-24",
    "deadline": "2026-09-07", "pri": 2, "type": "devel"}, ...]

详细说明与踩坑见《禅道API使用说明.md》（文档/资料/AI/）。
"""
import argparse
import json
import sys

from zentao_client import ZentaoClient, ZentaoError
import zentao_products
import zentao_projects
import zentao_executions
import zentao_stories
import zentao_tasks
import zentao_users
import zentao_web

RESOURCES = ["token", "products", "projects", "executions", "stories", "tasks", "users"]
ACTIONS = ["list", "get", "search", "create", "update", "delete", "web-delete", "batch-create",
           "assign", "start", "finish", "close", "active"]


def out(data):
    print(json.dumps(data, ensure_ascii=False, indent=2))


STATUS_ZH = {"wait": "待开始", "doing": "进行中", "done": "已完成",
             "closed": "已关闭", "pause": "暂停", "cancel": "已取消"}


def brief_tasks(items):
    """tasks list/search --brief：全量 JSON 动辄数千行，摘要为每任务一行。"""
    rows = []
    for t in items:
        a = t.get("assignedTo")
        account = a.get("account", "") if isinstance(a, dict) else (a or "")
        rows.append({"id": t.get("id"), "status": STATUS_ZH.get(t.get("status"), t.get("status")),
                     "pri": t.get("pri"), "estimate": t.get("estimate"),
                     "assignedTo": account, "name": t.get("name")})
    return rows


def brief_stories(items):
    """stories list/search --brief：需求字段（title/阶段）与任务不同，单独映射。"""
    rows = []
    for s in items:
        a = s.get("assignedTo")
        account = a.get("account", "") if isinstance(a, dict) else (a or "")
        rows.append({"id": s.get("id"), "status": STATUS_ZH.get(s.get("status"), s.get("status")),
                     "pri": s.get("pri"), "stage": s.get("stage"),
                     "assignedTo": account, "title": s.get("title")})
    return rows


BRIEF_KEYS = {
    "executions": ("id", "name", "status", "begin", "end", "project"),
    "products": ("id", "name", "code", "status"),
    "projects": ("id", "name", "model", "status", "begin", "end"),
    "users": ("id", "account", "realname", "role"),
}


def brief_rows(items, resource):
    """executions/products/projects/users --brief：按资源取关键列的通用摘要。
    assignedTo/PO 等人员字段在 API 返回里可能是 dict（{account,...}），自动解开。"""
    people = ("assignedTo", "PO", "QD", "RD")
    rows = []
    for it in items:
        row = {}
        for k in BRIEF_KEYS[resource]:
            v = it.get(k)
            if k in people and isinstance(v, dict):
                v = v.get("account") or ""
            elif k == "status":
                v = STATUS_ZH.get(v, v)
            row[k] = v
        rows.append(row)
    return rows


def build_filters(args):
    """从 CLI 参数收集 search 过滤条件（未传的不进 dict）。"""
    f = {}
    if args.name:
        f["name"] = args.name
    if args.assigned_to:
        f["assigned_to"] = args.assigned_to
    if args.status:
        f["status"] = args.status
    if args.pri is not None:
        f["pri"] = args.pri
    if args.parent:
        f["parent"] = args.parent
    if args.deadline_from:
        f["deadline_from"] = args.deadline_from
    if args.deadline_to:
        f["deadline_to"] = args.deadline_to
    if args.est_from:
        f["est_from"] = args.est_from
    if args.est_to:
        f["est_to"] = args.est_to
    return f


def build_parser():
    p = argparse.ArgumentParser(prog="zentao.py", description="禅道 API 命令行工具")
    # 凭据（默认读 deploy/.env 的 ZENTAO_API_*）
    p.add_argument("--url")
    p.add_argument("--account")
    p.add_argument("--password")
    # 通用参数（顶层共享）
    p.add_argument("--id", type=int, help="资源 ID")
    p.add_argument("--ids", nargs="+", type=int, help="web-delete 批量：多个资源 ID（与 --id 可并用）")
    p.add_argument("--name", help="名称")
    p.add_argument("--code", help="代号")
    p.add_argument("--desc", help="描述")
    p.add_argument("--desc-file", dest="desc_file", help="描述文件路径（多行描述，优先于 --desc）")
    p.add_argument("--type", dest="model", default="scrum", help="项目类型 scrum/kanban/waterfall")
    p.add_argument("--begin", help="开始日期 YYYY-MM-DD")
    p.add_argument("--end", help="截止日期 YYYY-MM-DD")
    p.add_argument("--products", help="项目关联产品 ID 逗号分隔，如 1,2")
    p.add_argument("--project", type=int, help="项目 ID（迭代）")
    p.add_argument("--product", type=int, help="产品 ID（需求）")
    p.add_argument("--execution", type=int, help="迭代 ID（任务）")
    p.add_argument("--title", help="需求标题")
    p.add_argument("--pri", type=int, help="优先级 1-4（create 不传默认 2；search 不传则不按优先级筛）")
    p.add_argument("--category", default="feature",
                   help="需求分类 feature/interface/performance/safe/experience/improve/other")
    p.add_argument("--spec", help="需求描述")
    p.add_argument("--estimate", type=float, help="预计工时（小时）")
    p.add_argument("--left", type=float, help="预计剩余（小时）")
    p.add_argument("--parent", type=int, default=0, help="父任务 ID（>0 时创建为子任务，走 URL task 参数）")
    p.add_argument("--to", dest="assigned_to", help="指派给（账号）")
    p.add_argument("--consumed", type=float, help="已消耗工时（小时，finish）")
    p.add_argument("--real-started", help="实际开始时间 YYYY-MM-DD[ HH:MM:SS]（start/finish；纯日期有 UTC 比较坑）")
    p.add_argument("--finished-date", help="实际完成时间 YYYY-MM-DD[ HH:MM:SS]（finish）")
    p.add_argument("--reason", help="关闭原因 done/cancel（close，默认 done）")
    p.add_argument("--file", dest="json_file", help="batch-create 的 JSON 文件路径")
    # search 过滤参数（客户端过滤）
    p.add_argument("--status", help="search 过滤：状态 wait/doing/done/pause/cancel/closed")
    p.add_argument("--deadline-from", dest="deadline_from", help="search 过滤：截止日期 >= (YYYY-MM-DD)")
    p.add_argument("--deadline-to", dest="deadline_to", help="search 过滤：截止日期 <= (YYYY-MM-DD)")
    p.add_argument("--est-from", dest="est_from", help="search 过滤：预计开始 >= (YYYY-MM-DD)")
    p.add_argument("--est-to", dest="est_to", help="search 过滤：预计开始 <= (YYYY-MM-DD)")
    # 22.5 服务端查询参数
    p.add_argument("--server", action="store_true",
                   help="tasks search 走 22.5 服务端过滤（search=1；支持 name/assigned-to/status/pri）")
    p.add_argument("--limit", type=int, default=None, help="服务端查询：每页条数（默认 10000 一次取全）")
    p.add_argument("--page", type=int, default=1, help="服务端查询：页码")
    p.add_argument("--order", default="id_desc", help="服务端查询：排序 id_desc/id_asc/pri_asc 等")
    p.add_argument("--merge-children", dest="merge_children", action="store_true",
                   help="服务端查询：子任务并入父任务 children")
    p.add_argument("--browse-type", dest="browse_type",
                   help="stories list/search 服务端 browseType（unclosed/closedstory/all 等）")
    p.add_argument("--full", action="store_true", help="users list：全字段（full=1）")
    p.add_argument("--brief", action="store_true",
                   help="tasks/stories list/search：摘要输出（每条一行，避免全量 JSON 爆屏）")
    # users create 专用
    p.add_argument("--user-account", dest="user_account", help="users create：新账号（登录名）")
    p.add_argument("--user-password", dest="user_password", help="users create：新密码")
    p.add_argument("--realname", help="users create：真实姓名")
    p.add_argument("--role", default="dev", help="users create：角色 dev/pm/designer/qa 等（默认 dev）")
    p.add_argument("--gender", choices=["m", "f"], help="users create：性别 m 男 / f 女（必填）")
    # stories create 用
    p.add_argument("--reviewer", help="stories create：评审人账号（逗号分隔多人，默认当前登录账号）")
    p.add_argument("resource", choices=RESOURCES, help="资源")
    p.add_argument("action", nargs="?", help="操作")
    return p


def main():
    args = build_parser().parse_args()
    r, a = args.resource, args.action
    try:
        c = ZentaoClient(url=args.url, account=args.account, password=args.password)
        if r == "token":
            out({"token": c.get_token()})
        elif r == "products":
            m = zentao_products
            if a == "list":
                r = m.list_(c)
                out(brief_rows(r, "products") if args.brief else r)
            elif a == "search":
                r = m.search(c, **build_filters(args))
                out(brief_rows(r, "products") if args.brief else r)
            elif a == "get":
                out(m.get(c, args.id))
            elif a == "create":
                out(m.create(c, args.name, args.code or "", desc=args.desc or ""))
            elif a == "update":
                fields = {}
                if args.name:
                    fields["name"] = args.name
                if args.code:
                    fields["code"] = args.code
                if args.desc:
                    fields["desc"] = args.desc
                out(m.update(c, args.id, **fields))
            elif a == "delete":
                out(m.delete(c, args.id))
            elif a == "web-delete":
                out(zentao_web.web_delete(c, "product", args.id))
        elif r == "projects":
            m = zentao_projects
            if a == "list":
                r = m.list_(c)
                out(brief_rows(r, "projects") if args.brief else r)
            elif a == "search":
                r = m.search(c, **build_filters(args))
                out(brief_rows(r, "projects") if args.brief else r)
            elif a == "get":
                out(m.get(c, args.id))
            elif a == "create":
                products = [int(x) for x in (args.products or "").split(",") if x.strip()]
                out(m.create(c, args.name, args.begin, args.end, products, model=args.model))
            elif a == "update":
                fields = {}
                if args.name:
                    fields["name"] = args.name
                if args.begin:
                    fields["begin"] = args.begin
                if args.end:
                    fields["end"] = args.end
                out(m.update(c, args.id, **fields))
            elif a == "delete":
                out(m.delete(c, args.id))
            elif a == "web-delete":
                out(zentao_web.web_delete(c, "project", args.id))
        elif r == "executions":
            m = zentao_executions
            if a == "list":
                r = m.list_(c, project=args.project)
                out(brief_rows(r, "executions") if args.brief else r)
            elif a == "get":
                out(m.get(c, args.id))
            elif a == "create":
                out(m.create(c, args.project, args.name, args.begin, args.end))
            elif a == "update":
                fields = {}
                if args.name:
                    fields["name"] = args.name
                if args.begin:
                    fields["begin"] = args.begin
                if args.end:
                    fields["end"] = args.end
                out(m.update(c, args.id, **fields))
            elif a == "delete":
                out(m.delete(c, args.id))
            elif a == "web-delete":
                out(zentao_web.web_delete(c, "execution", args.id))
        elif r == "stories":
            m = zentao_stories
            if a == "list":
                r = m.list_(c, product=args.product, browse_type=args.browse_type)
                out(brief_stories(r) if args.brief else r)
            elif a == "search":
                r = m.search(c, product=args.product, browse_type=args.browse_type, **build_filters(args))
                out(brief_stories(r) if args.brief else r)
            elif a == "get":
                out(m.get(c, args.id))
            elif a == "create":
                reviewer = [x.strip() for x in args.reviewer.split(",") if x.strip()] if args.reviewer else None
                out(m.create(c, args.product, args.title, pri=args.pri or 2,
                             category=args.category, spec=args.spec or "", reviewer=reviewer))
            elif a == "update":
                fields = {}
                if args.title:
                    fields["title"] = args.title
                if args.pri:
                    fields["pri"] = args.pri
                if args.category:
                    fields["category"] = args.category
                if args.spec:
                    fields["spec"] = args.spec
                out(m.update(c, args.id, **fields))
            elif a == "delete":
                out(m.delete(c, args.id))
            elif a == "web-delete":
                out(zentao_web.web_delete(c, "story", args.id))
        elif r == "tasks":
            m = zentao_tasks
            if a == "list":
                r = m.list_(c, execution=args.execution)
                out(brief_tasks(r) if args.brief else r)
            elif a == "search":
                if args.server:
                    f = build_filters(args)
                    client_only = [k for k in ("parent", "deadline_from", "deadline_to", "est_from", "est_to") if f.get(k)]
                    if client_only:
                        raise ValueError(f"服务端查询（--server）不支持 {client_only}，这些是客户端维度；去掉 --server 或去掉这些参数")
                    r = m.search_server(c, name=f.get("name"), assigned_to=f.get("assigned_to"),
                                        status=f.get("status"), pri=f.get("pri"),
                                        limit=args.limit or 10000, page=args.page,
                                        order=args.order, merge_children=args.merge_children)
                else:
                    r = m.search(c, execution=args.execution, **build_filters(args))
                out(brief_tasks(r) if args.brief else r)
            elif a == "get":
                out(m.get(c, args.id))
            elif a == "create":
                fields = {"assignedTo": args.assigned_to} if args.assigned_to else {}
                out(m.create(c, args.execution, args.name, estimate=args.estimate or 0,
                             est_started=args.begin, deadline=args.end,
                             pri=args.pri or 2, type_=args.model, parent=args.parent, **fields))
            elif a == "batch-create":
                with open(args.json_file, encoding="utf-8") as f:
                    tasks = json.load(f)
                out(m.batch_create(c, args.execution, tasks, parent=args.parent))
            elif a == "update":
                fields = {}
                for k, v in (("name", args.name), ("pri", args.pri),
                             ("estimate", args.estimate), ("left", args.left),
                             ("estStarted", args.begin), ("deadline", args.end)):
                    if v is not None:
                        fields[k] = v
                if args.assigned_to:
                    fields["assignedTo"] = args.assigned_to
                if args.desc_file:
                    with open(args.desc_file, encoding="utf-8") as f:
                        fields["desc"] = f.read()
                elif args.desc:
                    fields["desc"] = args.desc
                out(m.update(c, args.id, **fields))
            elif a == "delete":
                out(m.delete(c, args.id))
            elif a == "web-delete":
                ids = ([args.id] if args.id is not None else []) + (args.ids or [])
                if not ids:
                    raise ValueError("web-delete 需要至少一个 --id（或 --ids 多个）")
                out(m.web_delete(c, ids))
            elif a == "assign":
                out(m.assign(c, args.id, args.assigned_to, left=args.left))
        elif a == "start":
            out(m.start(c, args.id, real_started=getattr(args, "real_started", None),
                        left=getattr(args, "left", None)))
        elif a == "finish":
            out(m.finish(c, args.id, consumed=args.consumed or 0,
                         real_started=getattr(args, "real_started", None),
                         finished_date=getattr(args, "finished_date", None)))
        elif a == "close":
            out(m.close(c, args.id, closed_reason=getattr(args, "reason", None) or "done"))
        elif a == "active":
            out(m.active(c, args.id))
        elif r == "users":
            if a == "list":
                r = zentao_users.list_(c, full=args.full)
                out(brief_rows(r, "users") if args.brief else r)
            elif a == "get":
                out(zentao_users.get(c, args.id))
            elif a == "create":
                if not args.user_account or not args.user_password or not args.realname or not args.gender:
                    raise ValueError("users create 需要 --user-account --user-password --realname --gender(m/f)")
                out(zentao_users.create(c, args.user_account, args.user_password,
                                        args.realname, role=args.role, gender=args.gender))
            elif a == "delete":
                out(zentao_users.delete(c, args.id))
            elif a == "web-delete":
                out(zentao_web.web_delete(c, "user", args.id))
    except ZentaoError as e:
        print(f"错误：{e}", file=sys.stderr)
        sys.exit(1)
    except ValueError as e:
        print(f"参数错误：{e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
