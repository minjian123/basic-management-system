# 禅道 API 工具包

BMS 项目禅道（ZenTao 开源版 21.x，mjbk 192.168.0.107:8070）REST API 的 Python 封装。

## 文件

| 文件 | 说明 |
| --- | --- |
| `zentao_client.py` | 核心客户端：token 认证、通用请求、取全 `fetch_all`（兼容分页怪癖）、.env 凭据读取 |
| `zentao_products.py` / `zentao_projects.py` / `zentao_executions.py` / `zentao_stories.py` / `zentao_tasks.py` / `zentao_users.py` | 各资源操作（列表/查看/搜索/创建/更新/删除；任务含批量创建/指派/开始/完成/关闭） |
| `zentao_search.py` | 客户端过滤 `filter_items`（API 不支持服务端过滤，取全量后按名称/指派人/状态/优先级/父任务/日期筛） |
| `zentao_web.py` | Web 会话（GET 登录 + 调 Web 端点），通用 Web 删除 `web_delete(module,id)` / 批量 `web_delete_many` / 任务删除 `delete_task`（REST 失效操作走这里） |
| `zentao.py` | 命令行入口 |

## 快速上手

```bash
# 凭据：deploy/.env 配置（不入库）
#   ZENTAO_API_URL=http://192.168.0.107:8070
#   ZENTAO_API_ACCOUNT=minjian
#   ZENTAO_API_PASSWORD=<管理员密码>

python zentao.py tokens                        # 获取 token
python zentao.py executions list --project 1   # 项目 1 下的迭代
python zentao.py tasks list --execution 3      # 迭代 3 的任务（取全）
python zentao.py tasks search --name 接口       # 按名称模糊查（全局取全后客户端筛）
python zentao.py tasks search --assigned-to minjian --status doing
python zentao.py tasks search --parent 1       # 某父任务下的子任务
python zentao.py tasks search --deadline-from 2026-09-01 --deadline-to 2026-09-30
python zentao.py stories search --product 1 --name 用户   # 需求（name 匹配 title）
python zentao.py tasks batch-create --execution 3 --file tasks.json
python zentao.py tasks create --execution 3 --parent 1 --name "子任务" --estimate 4 --begin 2026-08-24 --end 2026-09-07 --to minjian
python zentao.py tasks batch-create --execution 3 --parent 1 --file subtasks.json   # 批量挂到父任务 1
python zentao.py tasks assign --id 1 --to minjian
python zentao.py tasks web-delete --id 1       # REST delete 有 bug，删除走 Web 会话
python zentao.py tasks web-delete --ids 82 83 84  # 批量删除（复用同一登录会话）
python zentao.py stories web-delete --id 5     # 通用 Web 删除（story/product/project/execution 同）
python zentao.py tasks update --id 1 --desc "单行描述"
python zentao.py tasks update --id 1 --desc-file desc.txt   # 多行描述走文件（优先于 --desc）
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

## 已知踩坑（详见《禅道API使用说明.md》）

- 认证头用 `Token: <token>`（不是 Bearer）
- 迭代创建 project 走 URL 参数；任务创建必须走 batchCreate 批量入口
- 任务必填 estStarted/deadline；指派必填 left；完成必填 currentConsumed/realStarted/finishedDate
- 需求创建必填 title/spec/pri/category（category 枚举 7 类）
- 创建用户 API 需会话 rand 拼盐，建议走 Web 界面
- 子任务：父任务 ID 走 `--parent`（URL 参数 `?task=`），body 写 `parent` 无效
- batchCreate 的 body 不接受 `assignedTo`，建任务后走 `assign` 指派
- `delete` 接口在 21.x 有参数错位 bug（空操作却返回 success）；**删除用 `tasks web-delete`**（`zentao_web` 经 Web 会话调 Web 端点，真正生效）：
  - 单个 `--id X`；批量 `--ids X Y Z`（复用同一登录会话，只登录一次，也避免触发登录锁定）
  - 通用删除 `web_delete(module,id)` / `web_delete_many(module,ids)`（`zentao_web.py`，story/product/project/execution 同端点约定 `m={模块}&t=ajax&f=delete&{模块}ID={id}`）
- Web 会话登录必须用 **GET 参数**（`m=user&t=json&f=login&account=..&password=..`），POST body 会被返回登录页
- **API 不支持服务端过滤**：`assignedTo`/`status`/`name` 等查询参数传了全被忽略（实测）；过滤走 `search`（取全量 + `zentao_search.filter_items` 客户端筛）
- **全局 `/tasks` 分页怪癖**：`limit` 失效、`page` 被当作"返回条数"（`page=86` 才返回全部 86 条），普通 `list` 只拿到 1 条；取全量统一走 `fetch_all`（先 `limit=大数`，不足再 `page=大数`）
- **`assignedTo` 是字典**（`{id,account,realname,...}`）非字符串，过滤时取 `account` 字段比对
