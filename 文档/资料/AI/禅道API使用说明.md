# 禅道 API 使用说明

> 禅道（ZenTao 21.x）REST API 与 BMS 工具包使用指南 · 2026-08-21

[文档首页](../../文档首页.md) › [资料](../工具/Ubuntu安装部署使用说明.md) › 禅道 API 使用说明　|　[开发服务器：禅道部署 →](../开发服务器/禅道部署使用说明.md)

## 1. 目的与范围 <a id="purpose"></a>

本文档固化禅道开源版 21.x REST API（`/api.php/v1`）的调用方法与**实测踩坑**，并说明 BMS 项目配套 Python 工具包（`deploy/tools/zentao/`）的用法，供后继 AI 与开发者直接使用，**无需重新摸索**。

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
| `zentao_client.py` | 核心客户端 `ZentaoClient`：token 认证、通用请求、自动分页、.env 凭据读取 |
| `zentao_products.py` / `zentao_projects.py` / `zentao_executions.py` / `zentao_stories.py` / `zentao_tasks.py` / `zentao_users.py` | 各资源操作 |
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
python zentao.py tasks list --execution 3             # 迭代 3 的任务
python zentao.py tasks create --execution 3 --name "接口测试" --estimate 16 --begin 2026-08-24 --end 2026-09-07 --to minjian
python zentao.py tasks batch-create --execution 3 --file tasks.json
python zentao.py tasks assign --id 1 --to minjian
python zentao.py tasks update --id 1 --pri 1
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
| 需求 | `GET /products/:id/stories`、`GET /stories/:id`、`POST /stories?product={id}`、`PUT /stories/:id`、`DELETE /stories/:id` | 创建必填 `title,spec,pri,category`；category 枚举：feature/interface/performance/safe/experience/improve/other |
| 任务（列表/编辑） | `GET /executions/:id/tasks`、`GET /tasks/:id`、`PUT /tasks/:id`、`DELETE /tasks/:id` | 编辑字段含 name/pri/estimate/left/assignedTo/estStarted/deadline/status 等 |
| 任务（批量创建） | `POST /executions/:id/tasks/batchCreate` | **唯一创建入口**；body `{"tasks":[{name,type,...}]}`；每项必填 `estStarted,deadline` |
| 任务动作 | `POST /tasks/:id/assignto`（必填 `assignedTo,left`）、`/start`、`/pause`、`/restart`、`/finish`（必填 `currentConsumed,realStarted,finishedDate`）、`/close`、`/active`、`/estimate` | — |
| 用户 | `GET /users`、`GET /users/:id` | 创建接口需会话 rand 拼盐，**建议走 Web 界面** |

通用约定：

- 列表响应：`{"page":1,"total":N,"limit":100,"<资源key>":[...]}`，`limit` 最大 100；工具包 `list_all()` 自动翻页。
- 错误：HTTP 4xx/5xx + JSON `{"error": ...}` 或 `{"error":{字段:文案}}`；工具包统一抛 `ZentaoError`（含状态码与原文）。

## 5. 踩坑记录（实测） <a id="pitfalls"></a>

| # | 坑 | 现象 | 正确做法 |
| --- | --- | --- | --- |
| 1 | 认证头 | `Authorization: Bearer <token>` 返回 Unauthorized | 用请求头 `Token: <token>` |
| 2 | 迭代创建 project 参数 | `POST /executions` body 带 `project` 报「所属项目不能为空」 | `project` 从 **URL 参数**传：`/executions?project={id}`（源码 `setPost('project', $projectID)` 会覆盖 body 值） |
| 3 | 任务创建走错入口 | `POST /tasks/:id`（或 `/tasks`）返回 **200 空体**、任务未创建 | `/tasks/:id` 路由到单数 entry（无 post 方法）静默失败；必须走 `POST /executions/{id}/tasks/batchCreate` |
| 4 | 任务必填日期 | 批量创建缺 `estStarted/deadline` 时静默失败 | 每项必须带 `estStarted`、`deadline`（建议用迭代起止日期） |
| 5 | 指派必填 left | `assignto` 缺 `left` 报「《预计剩余》不能为空」 | body 带 `left`（未开始的任务取 estimate） |
| 6 | 完成任务必填 | `finish` 缺 `currentConsumed/realStarted/finishedDate` 报错 | 三个字段都传（工具包默认今天） |
| 7 | 需求创建静默失败 | `POST /stories` 返回 200 空体（`null`）、需求未创建；Web 表单方式需完整登录（验证码），API token 不能直接用于 Web 会话 | **21.x 实测限制**：story 的创建走 Web 界面（产品 → 需求 → 添加需求）；列表/查看/更新/删除 API 正常 |
| 8 | 用户创建复杂 | API 需 `password1/password2` 与 session rand 拼盐、verifyPassword 等 | 建号走 Web 界面（组织 → 用户 → 添加用户） |
| 9 | 批量创建响应 | 单条创建也走 batchCreate，返回 `{"task":[...]}`（数组包装） | 工具包已解包为任务列表 |
| 10 | 迭代列表少数据 | `GET /projects/:id/executions` 只返回项目根执行（如 id=2），M0~M15 子迭代不出现 | 列迭代统一用 `GET /executions?status=all`（工具包已按 project 内存过滤） |

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

## 7. 参考 <a id="ref"></a>

| 资源 | 网址 | 说明 |
| --- | --- | --- |
| 禅道 API 文档 | https://www.zentao.net/book/api/1397.html | 官方 API 配置与常见问题（21.x 部分接口与本文档实测有出入时以本文档为准） |
| 禅道 Docker 部署 | https://www.zentao.net/book/zentaopms/docker-1111.html | 官方镜像部署说明 |
| 禅道官网 | https://www.zentao.net/ | 产品与社区 |

项目内关联：工具包 `deploy/tools/zentao/`（README.md）、《[禅道部署使用说明](../开发服务器/禅道部署使用说明.md)》、《[禅道技术介绍](../知识档案/工程化与质量/禅道技术介绍.md)》、《[总体项目规划](../../规划/总体项目规划.md)》里程碑与 WBS。

> 依《文档生成规范》编写 · 记录 2026-08-21 实测（禅道 21.x，mjbk 192.168.0.107:8070）
