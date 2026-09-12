# 03 backend 分层目录与职责测试记录

> 项目骨架 · 01 工程骨架 · 子任务 03 · 测试记录（用例、执行结果、问题与覆盖率）

[文档首页](../../../../../../文档首页.md) › [03 任务文档](../01_工程骨架_03_backend分层目录与职责.md) › 01 测试记录　|　[← 01 工程骨架](../../01_工程骨架.md)　[详细设计 →](../设计/03_详细设计_01_backend分层目录与职责.md)　[实施记录 →](../实施/03_实施_01_backend分层目录与职责.md)

## 1. 测试信息 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 任务 | [03 backend 分层目录与职责](../01_工程骨架_03_backend分层目录与职责.md) |
| 对应需求 | [01-3](../../../../需求/01_需求_工程骨架.md#r01-3) |
| 详细设计 | [03 详细设计_01](../设计/03_详细设计_01_backend分层目录与职责.md) |
| 实施记录 | [03 实施记录](../实施/03_实施_01_backend分层目录与职责.md) |
| 测试日期 | 2026-09-10 |
| 测试人 | minjian |
| 测试环境 | 开发机（Ubuntu）；Python 3.14.4（uv 0.12.7）；本地服务端口 8000；Kiwi TCMS（mjbk:8060） |
| Kiwi 用例 | 本任务新增 Case 3–10（demo 全量 CRUD）；Case 1（根路由）、Case 2（`/healthz`）回归；产品「BMS 基础管理系统」/ 分类「平台骨架」 |
| 结论 | 10/10 用例通过；CRUD 全链路接口实测符合契约；覆盖率 100%（110 语句） |

## 2. 测试范围与用例 <a id="scope"></a>

**范围**：本任务「分层骨架 + demo 走通」——分层目录与职责 docstring 的可用性证明、`/healthz` 迁移回归、根路由回归、demo 四件套（api→service→repository）全量 CRUD 与失败分支。不含：数据库落库（03 域）、统一响应/异常体细化（02-3）、认证与权限（阶段四）。

**用例清单**（先登记 Kiwi TCMS、后写自动化代码）：

| Kiwi ID | 用例 | 类型 | 自动化文件 | 结果 |
| --- | --- | --- | --- | --- |
| 1 | 根路由返回应用名与版本（GET /）——回归 | 接口冒烟 | `tests/api/test_main.py::test_root_returns_app_info` | 通过 |
| 2 | 健康检查 /healthz 存活（迁移回归） | 接口冒烟 | `tests/api/test_health.py::test_healthz_returns_ok` | 通过 |
| 3 | demo 创建（POST /api/v1/demos） | 接口 | `tests/api/test_demo.py::test_create_demo_returns_created` | 通过 |
| 4 | demo 列表（GET /api/v1/demos） | 接口 | `tests/api/test_demo.py::test_list_demos_returns_items` | 通过 |
| 5 | demo 按 ID 查询（GET /api/v1/demos/{id}） | 接口 | `tests/api/test_demo.py::test_get_demo_by_id` | 通过 |
| 6 | demo 更新（PUT /api/v1/demos/{id}） | 接口 | `tests/api/test_demo.py::test_update_demo_name` | 通过 |
| 7 | demo 删除（DELETE /api/v1/demos/{id}） | 接口 | `tests/api/test_demo.py::test_delete_demo` | 通过 |
| 8 | demo 查询不存在返回 404（GET） | 接口失败分支 | `tests/api/test_demo.py::test_get_missing_demo_returns_404` | 通过 |
| 9 | demo 更新不存在返回 404（PUT） | 接口失败分支 | `tests/api/test_demo.py::test_update_missing_demo_returns_404` | 通过 |
| 10 | demo 删除不存在返回 404（DELETE） | 接口失败分支 | `tests/api/test_demo.py::test_delete_missing_demo_returns_404` | 通过 |

接口级实测（联调补充）：`uvicorn` 启动后依次执行 `/api/v1/demos` 创建/列表/查询/更新/删除及删除后 404。

## 3. 执行记录与结果 <a id="run"></a>

**自动化用例**：

```bash
cd backend
uv run pytest -q
# 10 passed in 0.08s
```

**CRUD 全链路实测（`curl` 摘要）**：

| 操作 | 实测结果 |
| --- | --- |
| GET 列表（空） | `{"code":0,"message":"ok","data":[]}` |
| POST 创建 | `{"code":0,…,"data":{"id":1,"name":"实测 A"}}` |
| GET 列表 | 含 `id=1` 一项 |
| GET 详情 | 与创建一致 |
| PUT 更新 | 名称更新为「实测 B」 |
| DELETE | `data:null`；删除后 GET 返回 404 |
| `/healthz` / `/` / `/docs` | 200（回归） |

**质量门禁（辅助）**：`uv run ruff check .` 通过；`uv run pyright` 0 errors。

**结果汇总**：用例通过率 10/10（100%）；CRUD 成功与失败分支全部覆盖；Kiwi 用例登记与代码 `kiwi_id` 一一对应。

## 4. 问题与处置 <a id="issues"></a>

| # | 问题 / 现象 | 原因 | 处置 | 落点 |
| --- | --- | --- | --- | --- |
| 1 | 首轮覆盖率 96%、`demo_repository` 92%（update/delete 不存在分支未覆盖） | 用例清单缺失败分支 | 补登记 Kiwi Case 9/10 并新增两条用例，覆盖率回到 100% | 设计 §9、实施记录 §4 |

## 5. 覆盖率 <a id="coverage"></a>

```bash
uv run pytest --cov=app --cov-report=term-missing -q
```

| 范围 | 语句 | 未覆盖 | 覆盖率 |
| --- | --- | --- | --- |
| `app/main.py` | 14 | 0 | 100% |
| `app/api/*`、`app/schemas/demo.py`、`app/services/demo_service.py`、`app/models/demo.py` | 70 | 0 | 100% |
| `app/repositories/demo_repository.py` | 26 | 0 | 100% |
| 占位模块（docstring-only） | 0 | 0 | 100% |
| **合计** | **110** | **0** | **100%** |

口径：任务级覆盖率快照；补齐失败分支前与补齐后分别为 96% / 100%（见 §4）。覆盖率门禁（核心 ≥ 80% / 整体 ≥ 70%）随 05-1 接入 CI。

## 6. 偏差与遗留 <a id="deviations"></a>

- 用例数由设计初稿 6 条扩为 8 条（补失败分支），已回写设计。
- demo 内存实现为占位：03 域落库后替换 `DemoRepository`，测试用例不变。
- 404 响应 body 为 FastAPI 默认结构，只断言状态码；02-3 统一异常处理器接管后如需调整在设计修订同步。
- Allure 报告与 Kiwi 结果导入留 05-4；认证/权限/越权类用例待阶段四。

> 本文档依《文档生成规范》编写 · 按《任务文档规范》「测试文档（任务测试记录）」节测试文档结构组织
