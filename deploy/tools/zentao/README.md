# 禅道 API 工具包

BMS 项目禅道（ZenTao 开源版 21.x，mjbk 192.168.0.107:8070）REST API 的 Python 封装。

## 文件

| 文件 | 说明 |
| --- | --- |
| `zentao_client.py` | 核心客户端：token 认证、通用请求、自动分页、.env 凭据读取 |
| `zentao_products.py` / `zentao_projects.py` / `zentao_executions.py` / `zentao_stories.py` / `zentao_tasks.py` / `zentao_users.py` | 各资源操作（列表/查看/创建/更新/删除；任务含批量创建/指派/开始/完成/关闭） |
| `zentao.py` | 命令行入口 |

## 快速上手

```bash
# 凭据：deploy/.env 配置（不入库）
#   ZENTAO_API_URL=http://192.168.0.107:8070
#   ZENTAO_API_ACCOUNT=minjian
#   ZENTAO_API_PASSWORD=<管理员密码>

python zentao.py tokens                        # 获取 token
python zentao.py executions list --project 1   # 项目 1 下的迭代
python zentao.py tasks list --execution 3      # 迭代 3 的任务
python zentao.py tasks batch-create --execution 3 --file tasks.json
python zentao.py tasks assign --id 1 --to minjian
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
```

## 已知踩坑（详见《禅道API使用说明.md》）

- 认证头用 `Token: <token>`（不是 Bearer）
- 迭代创建 project 走 URL 参数；任务创建必须走 batchCreate 批量入口
- 任务必填 estStarted/deadline；指派必填 left；完成必填 currentConsumed/realStarted/finishedDate
- 需求创建必填 title/spec/pri/category（category 枚举 7 类）
- 创建用户 API 需会话 rand 拼盐，建议走 Web 界面
