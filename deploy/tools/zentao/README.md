# 禅道 API 工具包

BMS 项目禅道（ZenTao 开源版 22.5，`easysoft/zentao:latest` 滚动镜像，mjbk 192.168.0.107:8070）REST API 的 Python 封装。

## 文件

| 文件 | 说明 |
| --- | --- |
| `zentao_client.py` | 核心客户端：token 认证、通用请求、取全 `fetch_all`（兼容分页怪癖）、.env 凭据读取 |
| `zentao_products.py` / `zentao_projects.py` / `zentao_executions.py` / `zentao_stories.py` / `zentao_tasks.py` / `zentao_users.py` | 各资源操作（列表/查看/搜索/创建/更新/删除/关闭；任务含批量创建/指派/开始/完成/关闭/激活） |
| `zentao_tasks.py` | 任务操作；22.5 新增 `search_server()`（服务端过滤 `?search=1`：name/assigned_to/status/pri/ids + 分页/排序/merge_children） |
| `zentao_search.py` | 客户端过滤 `filter_items`（取全量后按名称/指派人/状态/优先级/父任务/日期筛；日期区间、父任务维度服务端没有，靠它） |
| `zentao_web.py` | Web 会话（GET 登录 + 调 Web 端点），通用 Web 删除 `web_delete(module,id)` / 批量 `web_delete_many` / 任务删除 `delete_task`（REST 失效操作走这里） |
| `zentao_sync_common.py` | 同步共用：解析需求/任务/计划/域总览、状态口径映射、stage 路径、回填 ID（需求 story / 任务 / 父任务 / 子任务父引用） |
| `zentao_sync_push.py` | 文档 → 禅道：建/复用**父任务**、建/更需求（story）+ 子任务、排期、状态流转、回填 ID |
| `zentao_sync_pull.py` | 禅道 → 文档：读回任务状态/完成日期回写需求/任务文档 |
| `zentao.py` | 命令行入口 |

## 快速上手

```bash
# 凭据：deploy/.env 配置（不入库）
#   ZENTAO_API_URL=http://192.168.0.107:8070
#   ZENTAO_API_ACCOUNT=minjian
#   ZENTAO_API_PASSWORD=<管理员密码>

python zentao.py token                         # 获取 token
python zentao.py executions list --project 1   # 项目 1 下的迭代
python zentao.py tasks list --execution 3      # 迭代 3 的任务（取全）
python zentao.py tasks list --execution 3 --brief   # 摘要输出（每任务一行，避免全量 JSON 爆屏）
python zentao.py stories list --product 1 --brief   # 需求摘要输出（每条一行）
python zentao.py executions list --brief       # 迭代摘要；products/projects/users 同样支持 --brief
python zentao.py tasks search --server --name 接口                  # 22.5 服务端过滤（name LIKE）
python zentao.py tasks search --server --assigned-to minjian --status doing   # 指派人+状态
python zentao.py tasks search --server --limit 50 --order id_desc    # 分页 + 排序
python zentao.py tasks search --server --merge-children              # 子任务并入父任务
python zentao.py tasks search --name 接口       # 客户端过滤（取全后筛；不带 --server）
python zentao.py tasks search --parent 1       # 客户端：某父任务下的子任务（服务端不支持）
python zentao.py tasks search --deadline-from 2026-09-01 --deadline-to 2026-09-30   # 客户端：日期区间
python zentao.py stories search --product 1 --name 用户   # 需求（name 匹配 title）
python zentao.py stories list --product 1 --browse-type closedstory   # 22.5 需求服务端 browseType 预筛
python zentao.py users list --full                              # 22.5 用户全字段（full=1）
python zentao.py stories create --product 1 --title "用户管理（CRUD）" --category feature --pri 2 --spec "描述" --reviewer minjian   # 建需求（reviewer 不传默认当前账号，22.5 必须数组）
python zentao.py stories delete --id 5                    # 删需求（REST，22.5 可用）
python zentao.py users create --user-account demo --user-password Pw123! --realname "演示" --gender m   # 建用户（gender 必填 m/f）
python zentao.py users delete --id 2                      # 删用户（REST，22.5 可用）
python zentao.py tasks batch-create --execution 3 --file tasks.json
python zentao.py tasks create --execution 3 --parent 1 --name "子任务" --estimate 4 --begin 2026-08-24 --end 2026-09-07 --to minjian
python zentao.py tasks batch-create --execution 3 --parent 1 --file subtasks.json   # 批量挂到父任务 1
python zentao.py tasks assign --id 1 --to minjian
python zentao.py tasks web-delete --id 1       # REST delete 有 bug，删除走 Web 会话
python zentao.py tasks web-delete --ids 82 83 84  # 批量删除（复用同一登录会话）
python zentao.py stories web-delete --id 5     # 通用 Web 删除（story/product/project/execution 同）
python zentao.py tasks update --id 1 --desc "单行描述"
python zentao.py tasks update --id 1 --desc-file desc.txt   # 多行描述走文件（优先于 --desc）
python zentao.py tasks start --id 1            # 开始（wait -> doing，自动带 left）
python zentao.py tasks finish --id 1 --consumed 8   # 完成（doing -> done）
python zentao.py tasks close --id 1            # 关闭（done -> closed）
python zentao.py tasks active --id 1           # 激活（重开 closed -> doing，走 PUT 可靠方式）
python zentao.py executions close --id 3       # 关闭迭代（doing -> closed）
python zentao.py executions delete --id 19     # 删迭代（REST，22.5 可用；勿用 web-delete）
```

作为库使用：

```python
import sys
sys.path.insert(0, r"D:\Develop\bms\deploy\tools\zentao")
from zentao_client import ZentaoClient
import zentao_tasks as tasks

c = ZentaoClient()
created = tasks.batch_create(c, execution=3, tasks=[
    {"name": "接口测试", "type": "devel", "pri": 2, "estimate": 16,
     "estStarted": "2026-08-24", "deadline": "2026-09-07"},
])
# 子任务：parent 走 URL 参数（body 写 parent 无效），建后再指派
created = tasks.batch_create(c, execution=3, parent=1, tasks=[...])
for t in created:
    tasks.assign(c, t["id"], "minjian")
```

## 文档同步（Sync）

`文档/项目/{stage}/` 与禅道产品（story）+ 迭代（任务）的双向同步，幂等可重跑：

```bash
# 文档 → 禅道（push）：建/复用父任务 + 建/更 story/子任务 + 排期 + 状态流转 + 回填 ID
python zentao_sync_push.py --stage 01_项目骨架 --execution 4 --dry-run   # 只解析+打印，不写禅道、不改文档
python zentao_sync_push.py --stage 01_项目骨架 --execution 4            # 实跑
python zentao_sync_push.py --stage 01_项目骨架 --execution 4 --assign minjian

# 禅道 → 文档（pull）：读回任务状态/完成日期回写文档
python zentao_sync_pull.py --stage 01_项目骨架 --dry-run
python zentao_sync_pull.py --stage 01_项目骨架
```

**父任务（push 阶段，先于子任务）**：按域总览（`任务/0X_域.md`）逐域建/复用 1 个父任务：
- 优先用域总览「禅道任务」行已回填的 id；否则查迭代内**同名顶层任务**，命中则复用并回填；未命中才创建；
- 创建时 `estimate`=该域子任务工时合计，`estStarted`/`deadline`=子任务排期 min~max（缺失用兜底日期）；
- 建/复用后把父任务 id 回填域总览，并更新子任务文档的「父任务 N」引用。

**幂等**：父任务/story/task 均优先用文档已回填的 id；未建则按「产品内 title 精确匹配 / 父任务+name 精确匹配」查已有，命中复用+回填，未命中才创建。**名称须与禅道完全一致（含空格）**，否则查不到会误建重复父任务。

## 已知踩坑（详见《禅道API使用说明.md》）

- 认证头用 `Token: <token>`（不是 Bearer）
- 迭代创建 project 走 URL 参数；任务创建必须走 batchCreate 批量入口
- 任务必填 estStarted/deadline；指派必填 left；完成必填 currentConsumed/realStarted/finishedDate
- 需求创建必填 title/spec/pri/category（category 枚举 7 类）且 **`reviewer` 必须传数组**（22.5 服务端 `array_filter` TypeError；工具包默认当前账号）
- 用户创建 `POST /users` 必填 `account/password/realname/role/gender`（**`gender` 取 m/f**，22.5 明文密码直接生效，无需会话 rand 拼盐）
- 子任务：父任务 ID 走 `--parent`（URL 参数 `?task=`），body 写 `parent` 无效
- batchCreate 的 body 不接受 `assignedTo`，建任务后走 `assign` 指派
- 删除按资源区分（22.5 实测）：
  - **task**：REST `delete` 有参数错位 bug（空操作却返回 success）→ 用 `tasks web-delete`（`zentao_web` 经 Web 会话调 Web 端点，真正生效）：单个 `--id X`；批量 `--ids X Y Z`（复用同一登录会话，只登录一次，也避免触发登录锁定）
  - **story / user**：REST `DELETE /stories/:id`、`DELETE /users/:id` 已验证可用，直接 `stories delete --id X` / `users delete --id X`
  - **execution**：REST `DELETE /executions/:id` 已验证可用（返回 `{"message":"success"}`）→ `executions delete --id X`；**Web 删除失效**（`web_delete` 返回空体），勿用
  - 通用 Web 删除 `web_delete(module,id)` / `web_delete_many(module,ids)`（`zentao_web.py`，端点约定 `m={模块}&t=ajax&f=delete&{模块}ID={id}`）；story 的 Web 删除须加 `confirm=yes` 参数
- Web 会话登录必须用 **GET 参数**（`m=user&t=json&f=login&account=..&password=..`），POST body 会被返回登录页
- **服务端过滤要显式 `search=1`**（22.5）：任务 `GET /tasks?search=1&name=&assignedTo=&status=&pri=&id=`（`assignedTo` 传**账号名**、可逗号列表；分页 `limit` 无上限/`page`/`order`；`mergeChildren=1` 子任务并入父任务）→ `tasks.search_server()` / CLI `tasks search --server`；不带 `search=1` 落入「我的任务」分支、参数被忽略（21.x 观察到的「不支持服务端过滤」即此分支）
- **日期区间、父任务维度服务端不支持**：走客户端 `search()`（取全量 + `zentao_search.filter_items`）
- **需求列表 `status` 参数是 browseType（非状态值）**：unclosed(默认)/all/closedstory/activestory/reviewingstory/assignedtome/openedbyme/unplan 等 → CLI `--browse-type`
- **「我的任务」分支分页怪癖**（22.5 残留）：不带 `search=1` 的 `GET /tasks` `limit`/`page` 失效、恒 1 条；取全量/服务端查询走 `search=1`（`search_server(limit=10000)` 一次取全）
- **`assignedTo` 是字典**（`{id,account,realname,...}`）非字符串，客户端过滤取 `account` 字段比对；服务端过滤直接传账号名
