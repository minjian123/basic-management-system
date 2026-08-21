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
    python zentao.py stories create --product 1 --title "用户管理" --pri 2 --category feature --spec "用户增删改查"
    python zentao.py tasks list --execution 3
    python zentao.py tasks batch-create --execution 3 --file tasks.json
    python zentao.py tasks create --execution 3 --name "接口测试" --estimate 16 --begin 2026-08-24 --end 2026-09-07 --to minjian
    python zentao.py tasks update --id 1 --pri 1
    python zentao.py tasks update --id 1 --desc "单行描述"
    python zentao.py tasks update --id 1 --desc-file desc.txt    # 多行描述走文件（优先于 --desc）
    python zentao.py tasks assign --id 1 --to minjian
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

RESOURCES = ["token", "products", "projects", "executions", "stories", "tasks", "users"]
ACTIONS = ["list", "get", "create", "update", "delete", "batch-create",
           "assign", "start", "finish", "close", "active"]


def out(data):
    print(json.dumps(data, ensure_ascii=False, indent=2))


def build_parser():
    p = argparse.ArgumentParser(prog="zentao.py", description="禅道 API 命令行工具")
    # 凭据（默认读 deploy/.env 的 ZENTAO_API_*）
    p.add_argument("--url")
    p.add_argument("--account")
    p.add_argument("--password")
    # 通用参数（顶层共享）
    p.add_argument("--id", type=int, help="资源 ID")
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
    p.add_argument("--pri", type=int, default=2, help="优先级 1-4")
    p.add_argument("--category", default="feature",
                   help="需求分类 feature/interface/performance/safe/experience/improve/other")
    p.add_argument("--spec", help="需求描述")
    p.add_argument("--estimate", type=float, help="预计工时（小时）")
    p.add_argument("--left", type=float, help="预计剩余（小时）")
    p.add_argument("--to", dest="assigned_to", help="指派给（账号）")
    p.add_argument("--consumed", type=float, help="已消耗工时（小时，finish）")
    p.add_argument("--file", dest="json_file", help="batch-create 的 JSON 文件路径")
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
                out(m.list_(c))
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
        elif r == "projects":
            m = zentao_projects
            if a == "list":
                out(m.list_(c))
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
        elif r == "executions":
            m = zentao_executions
            if a == "list":
                out(m.list_(c, project=args.project))
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
        elif r == "stories":
            m = zentao_stories
            if a == "list":
                out(m.list_(c, product=args.product))
            elif a == "get":
                out(m.get(c, args.id))
            elif a == "create":
                out(m.create(c, args.product, args.title, pri=args.pri,
                             category=args.category, spec=args.spec or ""))
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
        elif r == "tasks":
            m = zentao_tasks
            if a == "list":
                out(m.list_(c, execution=args.execution))
            elif a == "get":
                out(m.get(c, args.id))
            elif a == "create":
                fields = {"assignedTo": args.assigned_to} if args.assigned_to else {}
                out(m.create(c, args.execution, args.name, estimate=args.estimate or 0,
                             est_started=args.begin, deadline=args.end,
                             pri=args.pri, type_=args.model, **fields))
            elif a == "batch-create":
                with open(args.json_file, encoding="utf-8") as f:
                    tasks = json.load(f)
                out(m.batch_create(c, args.execution, tasks))
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
            elif a == "assign":
                out(m.assign(c, args.id, args.assigned_to, left=args.left))
            elif a == "start":
                out(m.start(c, args.id))
            elif a == "finish":
                out(m.finish(c, args.id, consumed=args.consumed or 0))
            elif a == "close":
                out(m.close(c, args.id))
            elif a == "active":
                out(m.active(c, args.id))
        elif r == "users":
            if a == "list":
                out(zentao_users.list_(c))
            elif a == "get":
                out(zentao_users.get(c, args.id))
    except ZentaoError as e:
        print(f"错误：{e}", file=sys.stderr)
        sys.exit(1)
    except ValueError as e:
        print(f"参数错误：{e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
