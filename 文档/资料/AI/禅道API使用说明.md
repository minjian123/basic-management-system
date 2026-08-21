# 禅道 API 使用说明

> 禅道（ZenTao 22.5）REST API 与 BMS 工具包使用指南 · 2026-08-21

[文档首页](../../文档首页.md) › [资料](../工具/Ubuntu安装部署使用说明.md) › 禅道 API 使用说明　|　[开发服务器：禅道部署 →](../开发服务器/禅道部署使用说明.md)

## 1. 目的与范围 <a id="purpose"></a>

本文档固化禅道开源版 REST API（`/api.php/v1`）的调用方法与**实测踩坑**，并说明 BMS 项目配套 Python 工具包（`deploy/tools/zentao/`）的用法，供后继 AI 与开发者直接使用，**无需重新摸索**。

> **版本说明**：镜像 `easysoft/zentao:latest` 为滚动发布，2026-08-21 实测容器版本为 **22.5**（`/apps/zentao/VERSION`）。本文「21.x 实测」表述即指本容器早期版本，行为随镜像升级可能变化，**升级镜像后需对踩坑条目复核**。

适用：禅道部署于 mjbk（`http://192.168.0.107:8070`，见《[禅道部署使用说明](../开发服务器/禅道部署使用说明.md)》）；职责分工：禅道管需求/任务/迭代，GitLab Issue 管代码缺陷，Kiwi TCMS 管测试用例（禅道缺陷/测试模块不使用）。

## 2. 认证 <a id="auth"></a>

```bash
# 获取 token（account/password 为禅道管理员）
curl -s -X POST http://192.168.0.107:8070/api.php/v1/tokens \
  -H "Content-Type: application/json" \
  -d '{"account":"minjian","password":"<密码>"}'
# => {"token":"<token>"}
```

- 后续所有请求带请求头 **`Token: <token>`**（不是 `Authorization: Bearer`，实测 Bearer 返回 Unauthorized）。
- token 即会话，长期有效；每次脚本运行获取一次即可。

## 3. BMS 工具包（推荐） <a id="toolkit"></a>

位置：`deploy/tools/zentao/`，仅依赖 Python 标准库（urllib），Windows/Linux 均可用。

| 文件 | 说明 |
| --- | --- |
| `zentao_client.py` | 核心客户端 `ZentaoClient`：token 认证、通用请求、取全 `fetch_all`（兼容分页怪癖）、.env 凭据读取 |
| `zentao_products.py` / `zentao_projects.py` / `zentao_executions.py` / `zentao_stories.py` / `zentao_tasks.py` / `zentao_users.py` | 各资源操作（列表/查看/搜索/创建/更新/删除） |
| `zentao_search.py` | 客户端过滤 `filter_items`（API 不支持服务端过滤，取全量后按名称/指派人/状态/优先级/父任务/日期筛） |
| `zentao_web.py` | Web 会话删除（`web_delete`/`web_delete_many`/`delete_task`） |
| `zentao.py` | 命令行入口 |
| `README.md` | 工具包快速上手 |

凭据（`deploy/.env`，不入库）：`ZENTAO_API_URL`、`ZENTAO_API_ACCOUNT`、`ZENTAO_API_PASSWORD`；也支持 `--url/--account/--password` 参数覆盖。

### 3.1 命令行用法 <a id="cli"></a>

```bash
cd deploy/tools/zentao

python zentao.py token                                # 获取 token
python zentao.py products list                        # 产品列表
python zentao.py products create --name "XX" --code xx
python zentao.py projects list
python zentao.py projects create --name "P" --type scrum --begin 2026-08-24 --end 2027-09-20 --products 1
python zentao.py executions list --project 1          # 项目 1 的迭代
python zentao.py executions create --project 1 --name "M0 启动就绪" --begin 2026-08-24 --end 2026-09-07
python zentao.py stories list --product 1             # 产品 1 的需求
python zentao.py tasks list --execution 3             # 迭代 3 的任务（取全）
python zentao.py tasks search --name 接口              # 按名称模糊查（取全后客户端筛）
python zentao.py tasks search --assigned-to minjian --status doing
python zentao.py tasks search --parent 1              # 某父任务下的子任务
python zentao.py tasks search --deadline-from 2026-09-01 --deadline-to 2026-09-30
python zentao.py stories search --product 1 --name 用户   # 需求（name 匹配 title）
python zentao.py tasks create --execution 3 --name "接口测试" --estimate 16 --begin 2026-08-24 --end 2026-09-07 --to minjian
python zentao.py tasks create --execution 3 --parent 1 --name "子任务" --estimate 4 --begin 2026-08-24 --end 2026-09-07 --to minjian
python zentao.py tasks batch-create --execution 3 --parent 1 --file subtasks.json   # 批量挂到父任务 1 下
python zentao.py tasks assign --id 1 --to minjian
python zentao.py tasks update --id 1 --pri 1
python zentao.py tasks update --id 1 --desc "单行描述"
python zentao.py tasks update --id 1 --desc-file desc.txt     # 多行描述走文件（优先于 --desc）
python zentao.py tasks start --id 1                   # 开始
python zentao.py tasks finish --id 1 --consumed 16    # 完成
python zentao.py tasks close --id 1                   # 关闭
python zentao.py users list
```

`tasks.json`（batch-create）：`[{"name":"...","estimate":16,"estStarted":"2026-08-24","deadline":"2026-09-07","pri":2,"type":"devel"}, ...]`

### 3.2 作为库使用 <a id="lib"></a>

```python
import sys
sys.path.insert(0, r"D:\Develop\bms\deploy\tools\zentao")
from zentao_client import ZentaoClient, ZentaoError
import zentao_tasks as tasks
import zentao_executions as executions

c = ZentaoClient()          # 凭据自动读 deploy/.env
for ex in executions.list_(c, project=1):
    print(ex["id"], ex["name"])

created = tasks.batch_create(c, execution=3, tasks=[
    {"name": "接口测试", "type": "devel", "pri": 2, "estimate": 16,
     "estStarted": "2026-08-24", "deadline": "2026-09-07"},
])
```

## 4. API 端点总表 <a id="endpoints"></a>

来源：禅道 21.x 容器源码（`/apps/zentao/api/v1/entries/` 与 `config/apiv1.php`）逐一核对。

| 资源 | 方法/路径 | 必填/要点 |
| --- | --- | --- |
| Token | `POST /tokens` | body `{account,password}` |
| 产品 | `GET /products`、`GET /products/:id`、`POST /products`、`PUT /products/:id`、`DELETE /products/:id` | 创建必填 `name`（`code` 21.x 下会被清空，可省略） |
| 项目 | `GET /projects`、`POST /projects`、`PUT /projects/:id`、`DELETE /projects/:id` | 创建必填 `name,begin,end,products`（products 为产品 ID 数组）；类型 `model`: scrum/kanban/waterfall |
| 迭代 | `GET /executions?status=all`（全量）、`GET /executions/:id`、`POST /executions?project={id}`、`PUT /executions/:id`、`DELETE /executions/:id` | 创建必填 `name,begin,end`；**`project` 走 URL 参数**；`/projects/:id/executions` 只返回项目根执行（子迭代不出现），不要用它列迭代 |
| 需求 | `GET /products/:id/stories`、`GET /stories/:id`、`POST /stories?product={id}`、`PUT /stories/:id`、`DELETE /stories/:id` | 创建必填 `title,spec,pri,category`，且 **`reviewer` 必须传数组**（22.5 踩坑 #7，不传/传字符串触发服务端 `array_filter` TypeError）；category 枚举：feature/interface/performance/safe/experience/improve/other；REST `DELETE /stories/:id` 22.5 已验证可用（读回 `deleted=true`） |
| 任务（列表/编辑） | `GET /executions/:id/tasks`、`GET /tasks/:id`、`PUT /tasks/:id`、`DELETE /tasks/:id` | 编辑字段含 name/desc/pri/estimate/left/assignedTo/estStarted/deadline/status 等；`desc` 支持多行文本（CLI 可 `--desc`/`--desc-file`）；**`DELETE /tasks/:id` 有 bug 不生效（踩坑 #13），删除用 `zentao_web.delete_task`/CLI `tasks web-delete`（单 `--id`/批量 `--ids`），或通用 `zentao_web.web_delete(module,id)`** |
| 任务（批量创建） | `POST /executions/:id/tasks/batchCreate` | **唯一创建入口**；body `{"tasks":[{name,type,...}]}`；每项必填 `estStarted,deadline`；**子任务：父任务 ID 走 URL 参数 `?task={id}`**（body 写 `parent` 被覆盖无效）；body 不接受 `assignedTo`（建后走 `assignto` 指派） |
| 任务动作 | `POST /tasks/:id/assignto`（必填 `assignedTo,left`）、`/start`、`/pause`、`/restart`、`/finish`（必填 `currentConsumed,realStarted,finishedDate`）、`/close`、`/active`、`/estimate` | — |
| 用户 | `GET /users`、`GET /users/:id`、`POST /users`、`DELETE /users/:id` | 创建必填 `account,password,realname,role,gender`（**`gender` 不传报「『性别』不能为空」**，取值 m/f；22.5 实测可用，明文密码直接生效）；REST `DELETE /users/:id` 22.5 已验证可用 |

通用约定：

- 列表响应：`{"page":1,"total":N,"limit":100,"<资源key>":[...]}`；工具包 `fetch_all()` 取全量（见踩坑 #15/#16 的全局分页怪癖）。
- 错误：HTTP 4xx/5xx + JSON `{"error": ...}` 或 `{"error":{字段:文案}}`；工具包统一抛 `ZentaoError`（含状态码与原文）。
- **过滤**：API 不支持服务端过滤参数（`assignedTo/status/name` 等传了被忽略，踩坑 #15）；用工具包 `search`（取全 + `zentao_search.filter_items` 客户端筛）。

## 5. 踩坑记录（实测） <a id="pitfalls"></a>

| # | 坑 | 现象 | 正确做法 |
| --- | --- | --- | --- |
| 1 | 认证头 | `Authorization: Bearer <token>` 返回 Unauthorized | 用请求头 `Token: <token>` |
| 2 | 迭代创建 project 参数 | `POST /executions` body 带 `project` 报「所属项目不能为空」 | `project` 从 **URL 参数**传：`/executions?project={id}`（源码 `setPost('project', $projectID)` 会覆盖 body 值） |
| 3 | 任务创建走错入口 | `POST /tasks/:id`（或 `/tasks`）返回 **200 空体**、任务未创建 | `/tasks/:id` 路由到单数 entry（无 post 方法）静默失败；必须走 `POST /executions/{id}/tasks/batchCreate` |
| 4 | 任务必填日期 | 批量创建缺 `estStarted/deadline` 时静默失败 | 每项必须带 `estStarted`、`deadline`（建议用迭代起止日期） |
| 5 | 指派必填 left | `assignto` 缺 `left` 报「《预计剩余》不能为空」 | body 带 `left`（未开始的任务取 estimate） |
| 6 | 完成任务必填 | `finish` 缺 `currentConsumed/realStarted/finishedDate` 报错 | 三个字段都传（工具包默认今天） |
| 7 | 需求创建 reviewer 必须传数组 | 22.5：`POST /stories` 不传 `reviewer`（或传字符串）时，REST 入口把 `$_POST['reviewer']` 默认成空字符串，服务端 `array_filter($_POST['reviewer'])`（`module/story/zen.php:1254`）直接抛 TypeError，返回 PHP 报错页、需求未创建；旧版本（21.x）现象为 200 空体静默失败 | `reviewer` 传**数组**（账号名或用户 ID 均可，如 `["minjian"]`），工具包 `zentao_stories.create` 已内置（默认当前登录账号，可 `reviewer=`/CLI `--reviewer` 覆盖） |
| 8 | 用户创建 gender 必填 | 22.5：`POST /users` 缺 `gender` 报「『性别』不能为空」；旧版本文档曾记为「需会话 rand 拼盐、建议走 Web」——22.5 已不需要，明文密码直接生效 | 传 `account,password,realname,role,gender`（gender 取 m/f），工具包 `zentao_users.create` 已封装（gender 未传时本地直接报错，不打 API）；REST `DELETE /users/:id` 同版已验证可用 |
| 9 | 批量创建响应 | 单条创建也走 batchCreate，返回 `{"task":{id:{...}}}`（**dict 按 id 键**，非数组） | 工具包 `batch_create` 已统一解包为任务列表（兼容 dict/list） |
| 10 | 迭代列表少数据 | `GET /projects/:id/executions` 只返回项目根执行（如 id=2），M0~M15 子迭代不出现 | 列迭代统一用 `GET /executions?status=all`（工具包已按 project 内存过滤） |
| 11 | 子任务父级走 URL 参数 | body 里写 `parent` 被忽略，建出的任务 `parent=0` | 父任务 ID 走 **URL 参数** `?task={id}`（源码 `buildTasksForBatchCreate` 内 `$task->parent=$taskID` 强制覆盖 body）；工具包 `batch_create(parent=…)` / CLI `--parent` 已封装 |
| 12 | batchCreate 不接受指派 | body 带 `assignedTo` 被忽略，建出任务 `assignedTo=''` | 建任务后逐个走 `POST /tasks/:id/assignto`（必填 `assignedTo,left`）指派 |
| 13 | 任务删除 API 失效 | `DELETE /tasks/:id` 返回 `{"message":"success"}`，但任务仍在、`deleted=False` | 禅道 21.x entry 参数错位（`$control->delete(0,$taskID,'true')`），实为空操作；**删除改用工具包 `zentao_web.delete_task` / CLI `tasks web-delete`**（单 `--id`、批量 `--ids` 复用同一登录会话），或通用 `zentao_web.web_delete(module,id)`（Web 会话调 `m={模块}&t=ajax&f=delete&{模块}ID={id}`，走正确 controller，真正生效）；`delete` 接口保留但不可靠 |
| 14 | Web 登录必须用 GET | POST body 提交 `account/password` 会被返回登录页（登录未建立） | 用 **GET 参数**登录：`GET /index.php?m=user&t=json&f=login&account=..&password=..`，成功返回 `{status:success, token, user}` 并种下会话 cookie `zentaosid`，之后即可带 cookie 调 Web 端点；工具包 `zentao_web.WebSession` 已封装 |
| 15 | API 不支持服务端过滤 | 列表接口带 `assignedTo/status/name/pri/parent` 等查询参数，**全被忽略**（传了仍返回全量，21.x 实测） | 过滤走「取全量 + 客户端筛」：工具包 `search`（`fetch_all` + `zentao_search.filter_items`），维度 name(模糊)/assigned_to/status/pri/parent/deadline_from/deadline_to/est_from/est_to |
| 16 | 全局 `/tasks` 分页怪癖 | `GET /tasks` 的 `limit` 参数失效、`page` 被当作「返回条数」（`page=1`→1 条、`page=86`→全量 86 条）；普通 `list` 只拿到 1 条（`total=86`）；其它端点（`/products`、`/projects`、`/executions`、`/executions/:id/tasks`）`limit` 正常 | 取全量统一走工具包 `fetch_all`：先 `limit=10000`，条数 < total 再 `page=10000`，取条数多者；`list_all` 仍可用于 limit 正常的端点 |
| 17 | `assignedTo` 是字典 | 任务/需求的 `assignedTo` 返回 `{id,account,avatar,realname}` 字典（非账号字符串），直接字符串比对匹配不到 | 过滤时取 `account` 字段比对（`zentao_search._assignee` 已兼容 dict/字符串） |

## 6. 典型场景 <a id="scenarios"></a>

### 6.1 初始化项目结构（产品 → 项目 → 迭代 → 任务）

本项目已完成（2026-08-21）：产品「BMS 基础管理系统」、项目「BMS 开发」、迭代 M0~M15、80 个阶段任务已指派 minjian。新建业务项目可照此流程：

```bash
python zentao.py products create --name "新产品" 
python zentao.py projects create --name "新项目" --begin 2026-09-01 --end 2026-12-31 --products <产品id>
python zentao.py executions create --project <项目id> --name "迭代一" --begin 2026-09-01 --end 2026-09-30
python zentao.py tasks batch-create --execution <迭代id> --file tasks.json
```

### 6.2 任务状态批量维护（AI 日常）

```python
import sys
sys.path.insert(0, r"D:\Develop\bms\deploy\tools\zentao")
from zentao_client import ZentaoClient
import zentao_tasks as tasks

c = ZentaoClient()
for t in tasks.list_(c, execution=3):        # 迭代 3 全部任务
    if t["status"] == "wait":
        tasks.start(c, t["id"])              # 开始
    # tasks.finish(c, t["id"], consumed=8)   # 完成（自动带日期）
```

### 6.3 里程碑进度核对

迭代 `M0~M15`（id 3~18）对应《[总体项目规划](../../规划/总体项目规划.md)》里程碑；`GET /executions/:id/tasks` 统计各状态数量即可核算进度（工具包 `tasks.list_`）。

### 6.4 批量补充任务描述（按项目文档回填 desc）

任务描述（`desc`）支持多行文本。批量回填时按任务建文本文件，用 `--desc-file` 逐个更新；更新后读回校验 `desc` 与源文件一致：

```bash
# 单任务单行
python zentao.py tasks update --id 1 --desc "准备期（M0）：环境与工具链就绪"
# 单任务多行（内容存 desc-1.txt）
python zentao.py tasks update --id 1 --desc-file desc-1.txt
# 读回校验
python zentao.py tasks get --id 1
```

作为库批量回填（2026-08-21 已对 M0 迭代 4 个任务执行）：

```python
import sys
sys.path.insert(0, r"D:\Develop\bms\deploy\tools\zentao")
from zentao_client import ZentaoClient
import zentao_tasks as tasks

c = ZentaoClient()
for task_id, desc in DESC.items():      # {任务id: 描述文本}，内容取自项目文档
    tasks.update(c, task_id, desc=desc)
    assert tasks.get(c, task_id)["desc"].strip() == desc.strip()
```

> 描述内容以《[总体项目规划](../../规划/总体项目规划.md)》WBS 与《[开发部署规划](../../规划/开发部署规划.md)》对应阶段为准，回填后任务卡即可自解释。

### 6.5 创建子任务（父任务拆解）

在父任务下建子任务：父任务 ID 走 `--parent`（URL 参数 `?task=`），body 里写 `parent` 无效（踩坑 #11）。建完后再指派（body 不接受 `assignedTo`，踩坑 #12）：

```bash
# 单个子任务
python zentao.py tasks create --execution 3 --parent 1 --name "mjbk Ubuntu 基础" \
  --estimate 4 --begin 2026-08-24 --end 2026-09-07 --to minjian
# 批量子任务（subtasks.json 同 tasks.json 格式），统一挂到父任务 1
python zentao.py tasks batch-create --execution 3 --parent 1 --file subtasks.json
```

作为库批量拆解 + 指派：

```python
import sys
sys.path.insert(0, r"D:\Develop\bms\deploy\tools\zentao")
from zentao_client import ZentaoClient
import zentao_tasks as tasks

c = ZentaoClient()
created = tasks.batch_create(c, execution=3, parent=1, tasks=[
    {"name": "mjbk Ubuntu 基础", "type": "devel", "pri": 2, "estimate": 4,
     "estStarted": "2026-08-24", "deadline": "2026-09-07"},
    {"name": "Docker Engine 与 ufw", "type": "devel", "pri": 2, "estimate": 2,
     "estStarted": "2026-08-24", "deadline": "2026-09-07"},
])
for t in created:                                  # body 不含 assignedTo，需补指派
    tasks.assign(c, t["id"], "minjian")
```

> 2026-08-21 已对 M0 任务 1「开发服务器环境与工具链就绪」拆解 6 个子任务（id 85~90，工时 4/2/4/3/2/1 合计 16h 与父任务一致，均指派 minjian）。

### 6.6 删除资源（task 走 Web 会话，story/user REST 已可用）

删除方式按资源区分（22.5 实测）：

| 资源 | 推荐方式 | 说明 |
| --- | --- | --- |
| 任务 task | `zentao_web`（Web 会话） | `DELETE /tasks/:id` 有参数错位 bug（踩坑 #13），返回 success 但不生效 |
| 需求 story | REST `DELETE /stories/:id` | 22.5 已验证，读回 `deleted=true`；Web 删除备用（需加 `confirm=yes`，见下） |
| 用户 user | REST `DELETE /users/:id` | 22.5 已验证，返回 `{"message":"success"}` |
| 产品/项目/迭代 | REST 或 Web | 未逐一复测，REST 优先、失败转 Web |

任务删除（走 Web 会话，踩坑 #14 的 GET 登录；删除端点 `index.php?m={模块}&t=ajax&f=delete&{模块}ID={id}`）：

```bash
python zentao.py tasks web-delete --id 82         # 单个，读回 deleted=True 确认
python zentao.py tasks web-delete --ids 82 83 84  # 批量，复用同一登录会话（只登录一次）
python zentao.py stories delete --id 5            # 需求：REST 删除（22.5 可用）
python zentao.py users delete --id 2              # 用户：REST 删除（22.5 可用）
python zentao.py stories web-delete --id 5        # 通用 Web 删除（备用）
```

> Web 删除注意：22.5 的 `story::delete` 默认 `confirm=no` 只返回确认弹窗（响应 `fail`），必须加 **`confirm=yes`** 参数才真正删除（`index.php?m=story&t=ajax&f=delete&storyID={id}&confirm=yes`）；task 的 `delete` 无此确认步骤。

作为库调用：

```python
import sys
sys.path.insert(0, r"D:\Develop\bms\deploy\tools\zentao")
from zentao_client import ZentaoClient
import zentao_tasks as tasks
import zentao_web as web

c = ZentaoClient()
# 任务删除（单 id 或 id 列表），读回 deleted 确认
r = tasks.web_delete(c, 82)        # {user, results:[{taskID, success, deleted, ...}]}
assert all(x["deleted"] is True for x in r["results"]), r
r = tasks.web_delete(c, [82, 83])  # 批量，复用同一登录会话

# 通用删除（任意资源，无读回确认）
r = web.web_delete(c, "story", 5)        # {module, id, user, httpStatus, success, response}
r = web.web_delete_many(c, "story", [5, 6])  # 批量，复用同一登录会话
```

> Web 删除走的是普通 controller（如 `task::delete($taskID)`，参数正确、真正生效，含级联删子任务）；REST 的 `taskEntry::delete` 参数错位删 0，不生效。2026-08-21 已用此法删除测试任务 82/83/84，并验证批量链路（单次登录删 3 条、幂等重删均正常）。

### 6.7 按条件查询资源（search，客户端过滤）

API 不支持服务端过滤（踩坑 #15）、全局 `/tasks` 分页有怪癖（踩坑 #16），查询统一走工具包 `search`：取全量 + `zentao_search.filter_items` 客户端筛。支持维度：`name`（模糊，匹配 `name` 或 `title`）、`assigned_to`、`status`、`pri`、`parent`、`deadline_from/deadline_to`、`est_from/est_to`（日期区间含边界）：

```bash
python zentao.py tasks search --name 开发                          # 名称模糊（全局 86 条中筛）
python zentao.py tasks search --assigned-to minjian --status doing # 指派人 + 状态组合
python zentao.py tasks search --parent 1                           # 任务 1 的子任务
python zentao.py tasks search --pri 1 --deadline-from 2026-09-01   # 优先级 + 截止区间
python zentao.py tasks search --execution 3 --name 接口             # 限定迭代 3 内查
python zentao.py stories search --product 1 --name 用户             # 需求（name 匹配 title）
python zentao.py products search --name BMS
```

作为库调用：

```python
import sys
sys.path.insert(0, r"D:\Develop\bms\deploy\tools\zentao")
from zentao_client import ZentaoClient
import zentao_tasks as tasks

c = ZentaoClient()
for t in tasks.search(c, assigned_to="minjian", status="wait"):
    print(t["id"], t["name"], t["deadline"])
```

> 2026-08-21 实测：全局 `tasks search --name 开发` 命中 2 条（#1/#90）、`--parent 1` 命中 6 条子任务（#85~90）、`--assigned-to minjian` 命中 86 条（assignedTo 为字典，取 account 比对，踩坑 #17）；各资源 `list` 取全（/tasks=86、/executions/3/tasks=10、/executions=16）均正常。

## 7. 参考 <a id="ref"></a>

| 资源 | 网址 | 说明 |
| --- | --- | --- |
| 禅道 API 文档 | https://www.zentao.net/book/api/1397.html | 官方 API 配置与常见问题（官方文档版本与本文档实测（22.5）有出入时以本文档为准） |
| 禅道 Docker 部署 | https://www.zentao.net/book/zentaopms/docker-1111.html | 官方镜像部署说明 |
| 禅道官网 | https://www.zentao.net/ | 产品与社区 |

项目内关联：工具包 `deploy/tools/zentao/`（README.md）、《[禅道部署使用说明](../开发服务器/禅道部署使用说明.md)》、《[禅道技术介绍](../知识档案/工程化与质量/禅道技术介绍.md)》、《[总体项目规划](../../规划/总体项目规划.md)》里程碑与 WBS。

> 依《文档生成规范》编写 · 记录 2026-08-21 实测（禅道 22.5，easysoft/zentao:latest 滚动镜像，mjbk 192.168.0.107:8070）
