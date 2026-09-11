# 03 backend 分层目录与职责实施记录

> 项目骨架 · 01 工程骨架 · 子任务 03 · 实施记录（实做内容、问题与处置、验证与遗留）

[文档首页](../../../../../../文档首页.md) › [03 任务文档](../01_工程骨架_03_backend分层目录与职责.md) › 01 实施记录　|　[← 01 工程骨架](../../01_工程骨架.md)　[详细设计 →](../设计/03_详细设计_01_backend分层目录与职责.md)

## 1. 实施信息 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 任务 | [03 backend 分层目录与职责](../01_工程骨架_03_backend分层目录与职责.md) |
| 对应需求 | [01-3](../../../../需求/01_需求_工程骨架.md#r01-3) |
| 详细设计 | [03 详细设计_01](../设计/03_详细设计_01_backend分层目录与职责.md) |
| 实施日期 | 2026-09-10 |
| 实施人 | minjian |
| 实施环境 | 开发机（Ubuntu）；Python 3.14.4（uv 0.12.7）；本地端口 8000；Kiwi TCMS（mjbk:8060） |
| 提交 | —（随本批提交，见仓库 git log） |
| 结论 | 分层目录与职责 docstring、路由聚合（`/api/v1`）、demo 四件套（内存 CRUD）与全量测试完成；验证全部通过 |

## 2. 实施概览 <a id="overview"></a>

```mermaid
flowchart LR
    A[Kiwi 用例登记] --> B[分层目录与职责 docstring]
    B --> C[占位文件 + alembic 占位]
    C --> D[demo 四件套（内存）]
    D --> E[路由聚合与 health 迁移]
    E --> F[tests/api 重组与用例]
    F --> G[README 更新]
    G --> H[验证与提交]
```

| 步骤 | 内容 | 结果 |
| --- | --- | --- |
| 1 | Kiwi 登记 demo 全量 CRUD 用例 | 首轮 Case 3–8；补分支后 Case 9/10（共 8 条） |
| 2 | 10 个分层目录与职责 docstring | 完成 |
| 3 | 8 个占位文件 + `alembic/README.md` | 完成 |
| 4 | demo 四件套（models/schemas/repositories/services，内存） | 完成 |
| 5 | `api/health.py`（迁入）、`api/demo.py`、`api/router.py`、`main.py` 聚合 | 完成 |
| 6 | `tests/api/` 重组 + demo 用例（8 条） | `pytest` 10 通过 |
| 7 | README（backend + 根）目录树同步 | 完成 |
| 8 | 验证（ruff / pyright / pytest / CRUD 实测） | 全部通过 |

## 3. 实施过程 <a id="process"></a>

### 3.1 Kiwi TCMS 用例登记（先登记再写代码）

沿用产品「BMS 基础管理系统」/ 用例分类「平台骨架」，首轮登记 demo 六条（Case 3–8：创建、列表、按 ID 查询、更新、删除、查询不存在）；复跑覆盖率发现 update/delete 的「不存在」失败分支未覆盖，补登记 Case 9/10（更新不存在 404、删除不存在 404）。既有 Case 1（根路由）、Case 2（`/healthz`）作为回归用例沿用。

### 3.2 分层目录与职责 docstring

建 `core / api / models / schemas / services / repositories / db / tasks / ws / i18n` 十个包，各层 `__init__.py` 按设计 §4 写入职责与禁止项（api 只做参数校验与路由分发、services 事务边界、repositories 数据访问、models/schemas 禁止业务逻辑等）。

### 3.3 占位文件

8 个占位模块仅 docstring + TODO（`core/config|security|exceptions`、`models/base`、`schemas/common`、`db/engine|session`、`api/deps`）；新增 `alembic/README.md` 目录占位（迁移体系由 03-6 交付）。

### 3.4 demo 四件套（内存实现）

- `models/demo.py`：`Demo` dataclass（id/name）
- `schemas/demo.py`：`DemoCreateRequest` / `DemoUpdateRequest` / `DemoResponse`（字段 1–64 字符）
- `repositories/demo_repository.py`：字典存储 + 自增 ID（list/get/create/update/delete，接口与数据库实现对齐）
- `services/demo_service.py`：业务服务（调用仓库，事务边界 TODO 随数据库接入）

### 3.5 路由聚合与 health 迁移

- `/healthz` 自 `main.py` 迁入 `app/api/health.py`（行为不变）
- `app/api/demo.py`：`APIRouter(prefix="/demos", tags=["demo"])` 五端点，统一响应占位 `{code:0, message:"ok", data}`，不存在抛 `HTTPException(404)`
- `app/api/router.py`：`api_router`（业务，挂 `/api/v1`）+ `health_router`（探针，根路径）
- `main.py`：保留根路由；`app.state.demo_service` 初始化（每应用实例独立）；`include_router(api_router, prefix="/api/v1")` 与 `include_router(health_router)`

### 3.6 测试重组与用例

`tests/test_main.py` 迁入 `tests/api/` 并拆分为 `test_main.py`（根路由，Case 1）与 `test_health.py`（Case 2）；新增 `test_demo.py`（Case 3–10 共 8 条，全部标注 `kiwi_id`）。

### 3.7 验证与提交

`uv run pytest`（10 通过）、`uv run ruff check .`、`uv run pyright`（0 错误）、`uvicorn` + `curl` CRUD 全链路实测（见 [§5 验证结果](#verify)）；随后形成本批提交（等用户指令）。

## 4. 问题与处置 <a id="issues"></a>

| # | 问题 / 现象 | 原因 | 处置 | 落点 |
| --- | --- | --- | --- | --- |
| 1 | 覆盖率 96%、`demo_repository` 92%（lines 58/73 未覆盖） | 首轮设计用例只含 GET 不存在，缺 update/delete 的失败分支（《测试规范》要求成功 + 失败分支） | 补登记 Kiwi Case 9/10 并新增两条用例；覆盖率回到 100%；设计 §9/§10/§12 回写 | 设计 §9 |
| 2 | 停止 uvicorn 后台任务后端口 8000 短暂仍被占用 | `uv run` 包装进程退出滞后 | 按端口定位 PID 清理并确认释放；后续同类操作沿用「停任务 + 端口确认」 | 本记录 |

## 5. 验证结果 <a id="verify"></a>

| 验证点（任务完成标准） | 方法 | 结果 |
| --- | --- | --- |
| 目录树与需求清单逐项一致 | 对照需求 01-3 清单 | 通过（10 层 + 占位 + demo + tests/api） |
| 各层 docstring 职责与禁止项 | 逐层核对 | 通过 |
| demo 四件套 + 路由走通 | `pytest` + `curl` CRUD | 通过（创建/列表/查询/更新/删除/404 全链路符合契约） |
| `uv run ruff check .` | 命令 | 通过（All checks passed） |
| `uv run pyright` | 命令 | 通过（0 errors） |
| `uv run pytest` | 命令 | 通过（10 passed） |
| 覆盖率 | `pytest --cov=app` | 通过（110 语句 100%） |
| Kiwi 用例关联 | 平台登记 + 代码 `kiwi_id` 标注 | 通过（本任务 8 条：Case 3–10） |

## 6. 偏差与遗留 <a id="deviations"></a>

- 无设计偏差（用例数 6 → 8 已回写设计 §9/§10/§12）。
- demo 内存实现为占位：03 域落库时替换 `DemoRepository` 实现（接口签名稳定，上层不改）。
- 404 响应 body 为 FastAPI 默认结构；02-3 统一异常处理器接管后如需调整断言，在设计修订中同步。
- Allure 报告与 Kiwi 执行结果导入留 05-4；覆盖率流水线门禁随 05-1；认证与权限相关用例待阶段二。

> 本文档依《文档生成规范》编写 · 按《任务文档规范》「实施文档（任务执行记录）」节实施文档结构组织
