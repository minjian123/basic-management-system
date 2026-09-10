# backend 分层目录与职责详细设计

> BMS · 阶段一 / 03 任务 · 任务级详细设计（可落地、可逐项验收）

[文档首页](../../../../../文档首页.md) › [03 任务文档](../01_工程骨架_03_backend分层目录与职责.md) › 01 详细设计　|　[← 01 工程骨架](../../01_工程骨架.md)

## 1. 概述 <a id="overview"></a>

本文档是任务 [03 backend 分层目录与职责](../01_工程骨架_03_backend分层目录与职责.md) 的**详细设计**，粒度到「按序落地、逐条验收」，是任务级执行设计，位于 `bms文档/设计/` 全局粗设计之下一级。两者不一致时，以本文档为 03 的执行依据；不一致点记录于 [第 12 节](#align)。

上游依据（可追溯）：

- 《[项目规划说明](../../../../../规划/项目规划说明.md)》§4 项目目录结构
- 《[架构设计 · 总体架构](../../../../../设计/架构设计/03_架构设计_总体架构.md)》§5 monorepo 布局、§6 技术栈
- 《[后端开发规范](../../../../../规范/后端开发规范.md)》§2 目录与分层职责、§3 Python 编码规范、§4 模块组织、§5.1 统一响应、§6.1 RESTful 路径
- 《[命名规范](../../../../../规范/命名规范.md)》§3 项目与目录命名、§6 Python 命名
- 需求 [01-3](../../../需求/01_需求_工程骨架.md#r01-3)

与前后任务的关系：01（仓库根骨架）、02（backend 工程初始化：工厂基线、根路由、测试基线）已交付；03 建 `app/` 分层目录与职责 docstring、路由聚合（`/api/v1`）、示例模块 `demo`（四件套 + 路由走通）；02-1/02-3/02-4/02-5、03-2、03-6 在对应占位文件上填充实现。职责边界见 [第 8 节](#boundary)。

## 2. 现状与差距 <a id="gap"></a>

02 实施后的 backend 现状与 03 目标：

| 项 | 现状（02 交付） | 03 目标 | 动作 |
| --- | --- | --- | --- |
| `app/` 结构 | 仅 `__init__.py` + `main.py`（扁平） | `core/api/models/schemas/services/repositories/db/tasks/ws/i18n` 分层 + 各层 `__init__.py` 职责 docstring | 新建 |
| 端点定义 | 根路由与 `/healthz` 内联于 `main.py` | `/healthz` 迁至 `app/api/health.py`；业务路由经 `app/api/router.py` 聚合挂 `/api/v1`；根路由保留 `main.py` | 修改 |
| 分层占位文件 | 缺失 | `core/{config,security,exceptions}.py`、`models/base.py`、`schemas/common.py`、`db/{engine,session}.py`、`api/deps.py`（仅 docstring + TODO，归 02 域/03-2 填充） | 新建 |
| 示例模块 | 缺失 | `demo` 四件套（models/schemas/services/repositories）+ api 路由，内存 CRUD 走通 | 新建 |
| `alembic/` | 缺失（仅 `alembic.ini` 占位） | `alembic/README.md` 目录占位（迁移体系由 03-6 交付） | 新建 |
| `tests/` 结构 | `conftest.py` + `test_main.py` | 按 `tests/api/` 同构重组；新增 health 与 demo 全量用例 | 修改 |
| 路由注册 | 无序 | 模块内 `APIRouter(prefix="/demos", tags=["demo"])`，`api/router.py` 统一 include | 新建 |

## 3. 目标目录与交付物清单 <a id="tree"></a>

03 落地后的 `backend/` 相关结构：

```text
backend/
├── alembic/
│   └── README.md             # 迁移目录占位（03-6 填充 env.py / versions）
├── app/
│   ├── __init__.py           # 版本（保持）
│   ├── main.py               # 工厂：聚合路由挂载 + demo 服务状态 + 根路由（修改）
│   ├── core/
│   │   ├── __init__.py       # 层职责 docstring
│   │   ├── config.py         # 配置加载占位（02-1）
│   │   ├── security.py       # 安全占位（阶段二）
│   │   └── exceptions.py     # 异常体系占位（02-3）
│   ├── api/
│   │   ├── __init__.py       # 层职责 docstring
│   │   ├── deps.py           # 公共依赖占位（02-5）
│   │   ├── router.py         # 聚合注册：api_router（/api/v1）+ health_router（根）
│   │   ├── health.py         # /healthz（自 main.py 迁入，契约细化归 02-4）
│   │   └── demo.py           # demo 模块路由（/demos）
│   ├── models/
│   │   ├── __init__.py       # 层职责 docstring
│   │   ├── base.py           # BaseModel 占位（03-2）
│   │   └── demo.py           # demo 内存领域模型（dataclass）
│   ├── schemas/
│   │   ├── __init__.py       # 层职责 docstring
│   │   ├── common.py         # 统一响应模型占位（02-3）
│   │   └── demo.py           # DemoCreateRequest / DemoUpdateRequest / DemoResponse
│   ├── services/
│   │   ├── __init__.py       # 层职责 docstring
│   │   └── demo_service.py   # DemoService（内存实现）
│   ├── repositories/
│   │   ├── __init__.py       # 层职责 docstring
│   │   └── demo_repository.py # DemoRepository（内存字典实现）
│   ├── db/
│   │   ├── __init__.py       # 层职责 docstring
│   │   ├── engine.py         # 引擎工厂占位（02-5）
│   │   └── session.py        # 会话工厂与 get_db 占位（02-5）
│   ├── tasks/__init__.py     # Celery 任务占位
│   ├── ws/__init__.py        # Socket.IO 占位
│   └── i18n/__init__.py      # 语言包占位
└── tests/
    ├── conftest.py           # ASGITransport 客户端夹具（保持）
    └── api/
        ├── test_main.py      # 根路由（自 tests/ 迁入）
        ├── test_health.py    # /healthz
        └── test_demo.py      # demo 全量 CRUD 用例
```

交付物清单：分层目录与 `__init__.py`（10 个）、占位文件（8 个）、demo 四件套（5 个文件）、路由 3 个文件、`main.py` 修改、`alembic/README.md`、测试重组与新增 8 个文件。无空目录、无 `.gitkeep`（`tests/services/` 等随模块用例按需创建）。

## 4. 分层职责 docstring 设计 <a id="layers"></a>

每层 `__init__.py` 写明职责与禁止项（《后端开发规范》§2），文字固定如下：

```python
# core/__init__.py
"""core 层：配置、安全与异常等基础能力（横切关注点）。

职责：配置加载（config.py）、安全工具（security.py）、异常体系（exceptions.py）。
禁止：引用 api/services/repositories 的业务代码；不承载业务逻辑。
"""

# api/__init__.py
"""api 层：路由与参数校验，只做参数校验与路由分发。

职责：依赖注入（deps.py）、路由聚合（router.py）、模块路由（health/demo）。
禁止：直接操作模型、写业务逻辑；业务规则一律经 services 层。
"""

# models/__init__.py
"""models 层：SQLAlchemy ORM 模型（base.py 基类，模块文件 {模块}.py）。

职责：数据结构与映射定义。
禁止：写业务逻辑；查询与业务规则归 repositories/services。
"""

# schemas/__init__.py
"""schemas 层：Pydantic 请求/响应模型（common.py 统一响应，模块文件 {模块}.py）。

职责：请求校验与响应契约。
禁止：写业务逻辑；禁止直接返回 ORM 对象。
"""

# services/__init__.py
"""services 层：业务逻辑与事务边界（{模块}_service.py）。

职责：业务规则、事务边界（with session.begin()）、事件发布。
禁止：直接拼 SQL、绕过 repositories 访问数据。
"""

# repositories/__init__.py
"""repositories 层：数据访问与数据源/分片路由（{模块}_repository.py）。

职责：数据读写、数据源与分片路由、数据范围注入。
禁止：承载业务规则。
"""

# db/__init__.py
"""db 层：异步引擎、会话工厂与读写分离路由（engine.py / session.py）。

职责：数据库连接与会话生命周期。
禁止：写业务逻辑；会话禁止跨请求共享。
"""

# tasks/__init__.py
"""tasks：Celery 任务定义（占位，随对应阶段实现）。"""

# ws/__init__.py
"""ws：Socket.IO 连接与会话事件（占位，随对应阶段实现）。"""

# i18n/__init__.py
"""i18n：国际化语言包与运行时翻译（占位，随对应阶段实现）。"""
```

## 5. 占位文件设计 <a id="placeholders"></a>

仅模块 docstring + TODO，不定义符号（由对应任务填充）：

| 文件 | docstring 要点 |
| --- | --- |
| `core/config.py` | 配置加载（占位）：config.toml 分区、`BMS_` 环境变量覆盖与启动校验由任务 02-1 实现 |
| `core/security.py` | 安全工具（占位）：密码哈希、token 校验等随阶段二认证接入 |
| `core/exceptions.py` | 异常体系（占位）：BizError 与全局异常处理器由任务 02-3 实现 |
| `models/base.py` | ORM 基类（占位）：BaseModel（雪花 ID / 审计 / 软删除 / 乐观锁）由任务 03-2 实现 |
| `schemas/common.py` | 统一响应模型（占位）：ApiResponse / PageResponse 由任务 02-3 实现 |
| `db/engine.py` | 引擎工厂（占位）：多数据源引擎创建由任务 02-5 实现 |
| `db/session.py` | 会话工厂（占位）：async_sessionmaker 与 `get_db` 依赖由任务 02-5 实现 |
| `api/deps.py` | 公共依赖（占位）：`get_db` / redis 等依赖由任务 02-5 起实现 |

`alembic/README.md`：说明迁移体系（三套方言 `env.py`、`versions/`）由任务 03-6 交付。

## 6. 路由聚合与端点设计 <a id="router"></a>

**聚合（`app/api/router.py`）**：业务路由统一挂 `/api/v1`；探针与根路由保持根路径（`/healthz` 契约不前缀化）。

```python
api_router = APIRouter()          # main.py 挂载时加 prefix="/api/v1"
api_router.include_router(demo.router)

health_router = APIRouter()       # 探针挂根路径
health_router.include_router(health.router)
```

**`app/api/health.py`**：将 `main.py` 内联的 `/healthz` 原样迁入 `APIRouter()`（行为不变，契约细化归 02-4）。

**`app/api/demo.py`**：模块路由 `APIRouter(prefix="/demos", tags=["demo"])`，端点（成功统一 HTTP 200 + `{code:0, message:"ok", data:…}` 占位；02-3 换统一响应模型）：

| 方法 | 路径 | 请求 | 响应 data | 说明 |
| --- | --- | --- | --- | --- |
| POST | `/api/v1/demos` | `DemoCreateRequest` | `{id, name}` | 创建 |
| GET | `/api/v1/demos` | — | `[{id, name}, …]` | 列表 |
| GET | `/api/v1/demos/{demo_id}` | — | `{id, name}` | 详情；不存在 404 |
| PUT | `/api/v1/demos/{demo_id}` | `DemoUpdateRequest` | `{id, name}` | 更新；不存在 404 |
| DELETE | `/api/v1/demos/{demo_id}` | — | `null` | 删除；不存在 404 |

不存在时 `raise HTTPException(status_code=404, detail="demo 不存在")`（HTTP 语义透传；02-3 统一异常处理器接管后调整 body）。

**`app/main.py`（03 目标形态）**：`create_app()` 保留根路由 `GET /`，初始化 `app.state.demo_service = DemoService(DemoRepository())`（每应用实例独立，测试隔离；02-5 起改为依赖注入），并 `app.include_router(api_router, prefix="/api/v1")` 与 `app.include_router(health_router)`。

## 7. demo 示例模块设计（四件套） <a id="demo"></a>

**`models/demo.py`**：领域模型（内存占位，03 域落库时替换为 SQLAlchemy 模型）：

```python
@dataclass
class Demo:
    """demo 示例实体（内存实现）。"""

    id: int
    name: str
```

**`schemas/demo.py`**：`DemoCreateRequest(name: str, 1–64 字符)`、`DemoUpdateRequest(name)`、`DemoResponse(id, name)`（Pydantic v2，字段带 description）。

**`repositories/demo_repository.py`**：`DemoRepository`——字典存储 + 自增 ID，方法 `list / get / create / update / delete`；接口签名与数据库实现保持一致，03 域替换实现时不改上层。

**`services/demo_service.py`**：`DemoService(repository)`——`list_demos / get_demo / create_demo / update_demo / delete_demo`；事务边界的 TODO 注释（数据库接入后补 `with session.begin()`）。

**`api/demo.py`**：路由 5 端点 + 依赖 `get_demo_service(request)`（读 `request.app.state.demo_service`，返回类型注解 `DemoService`）；api 层只做参数校验与路由分发，不存在→404 的映射属 API 语义。

> 分层走通证明：请求路径 `api（校验/分发）→ service（业务规则）→ repository（数据访问）→ 返回`，01-03 验收以此为准。

## 8. 职责边界（03 vs 01/02/02 域/03-2/03-6） <a id="boundary"></a>

| 事项 | 归属 | 说明 |
| --- | --- | --- |
| 分层目录与职责 docstring、路由聚合 `/api/v1`、demo 四件套（内存）、tests/api 同构 | **03（本文档）** | 本任务交付 |
| 根骨架、工程初始化、工厂基线、测试夹具 | 01 / 02 | 已完成 |
| 配置加载、日志、统一响应/异常、健康检查契约 | 02-1 / 02-2 / 02-3 / 02-4 | 在 03 占位文件上实现 |
| SQLAlchemy 底座（engine/session/`get_db`） | 02-5 | 填充 `db/` 与 `api/deps.py` |
| `BaseModel` 基类与表规范 | 03-2 | 填充 `models/base.py` |
| Alembic 迁移体系（env.py / versions） | 03-6 | 替换 `alembic/README.md` 占位 |

> 原则：03 只搭骨架与示例，不实现 02 域能力；demo 的内存实现对上层接口稳定，03 域落库时只替换 repository 实现。

## 9. 测试设计（Kiwi 先行，全量 CRUD） <a id="tests"></a>

**测试结构**：`tests/api/test_main.py`（自 `tests/test_main.py` 迁入，根路由）、`tests/api/test_health.py`（`/healthz`，沿用 Kiwi Case 2）、`tests/api/test_demo.py`（demo 全量 CRUD）。

**用例清单**（先登记 Kiwi TCMS、再写代码；用例 ID 实施时分配并回填测试代码）：

| 拟登记用例 | 类型 | 断言要点 |
| --- | --- | --- |
| demo 创建 | 接口 | POST `/api/v1/demos` → 200、`code=0`、`data.id` 自增、`data.name` 一致 |
| demo 列表 | 接口 | 创建后 GET 列表包含该项；初始为空 |
| demo 按 ID 查询 | 接口 | GET `/{id}` → 200、data 与创建一致 |
| demo 更新 | 接口 | PUT `/{id}` → 200、名称变更；再查一致 |
| demo 删除 | 接口 | DELETE `/{id}` → 200；再查 404 |
| demo 查询不存在 | 接口 | GET `/{id}`（不存在）→ 404（只断言状态码，body 结构留 02-3 统一） |

**隔离性**：`conftest.py` 的 `client` 夹具每用例创建独立应用实例，`demo_service` 挂 `app.state` 随之隔离，无跨用例污染。

## 10. 实施步骤 <a id="steps"></a>

按序执行，每步附验证点：

1. **Kiwi 登记**：先登记 demo 全量 CRUD 用例（6 条）并取得用例 ID（沿用产品「BMS 基础管理系统」/ 分类「平台骨架」）。
2. **分层目录**：建 `core/api/models/schemas/services/repositories/db/tasks/ws/i18n` 与各层 `__init__.py` 职责 docstring（§3/§4）。
3. **占位文件**：写 8 个占位模块（§5）与 `alembic/README.md`。
4. **demo 四件套**：models/schemas/repositories/services（内存实现，§7）。
5. **路由**：新增 `api/health.py`（迁入 `/healthz`）、`api/demo.py`、`api/router.py`；`main.py` 接入聚合与 `app.state.demo_service`，保留根路由。
6. **测试**：重组 `tests/api/` 并把现有用例迁入；新增 `test_demo.py`（6 条，标注 `kiwi_id`）。
7. **更新 README**：backend 与根 README 目录树同步为 03 完成态。
8. **验证**：`uv run ruff check .`、`uv run pyright`、`uv run pytest`、`uvicorn` + `curl`（`/api/v1/demos` CRUD、`/healthz`、`/`、`/docs`）。
9. **提交**：经用户明确指令后再 `git commit`（遵循工作区根《AGENTS.md》提交纪律）。

## 11. 验收映射 <a id="accept-map"></a>

| 完成标准 | 设计落点 | 验证方法 |
| --- | --- | --- |
| 目录树与需求清单逐项一致 | §3 目标目录 | 对照需求 01-3 清单逐项核对 |
| 各层 `__init__.py` docstring 写明职责与禁止项 | §4 | 逐层人工核对 + 代码评审 |
| demo 四件套 + 路由注册走通 | §6/§7 | `pytest` 全量 CRUD 用例 + `curl` 实测 |
| （工程门禁）ruff / pyright / pytest | §9/§10 | 三条命令零错误退出 |

## 12. 风险与开放项 <a id="risk"></a>

| 风险 / 开放项 | 说明 | 处置 |
| --- | --- | --- |
| 内存 demo 与后续数据库实现切换 | 03 域前 demo 用内存仓库 | repository 接口签名固定（list/get/create/update/delete），替换实现不改上层 |
| 测试状态污染 | demo 数据在进程内存储 | `demo_service` 挂 `app.state`，每用例独立应用实例（夹具隔离） |
| 404 响应 body 结构 | 当前为 FastAPI 默认 `{"detail": …}` | 测试只断言 404 状态码；02-3 统一异常处理器接管后如需调整断言，在设计修订中同步 |
| `request.app.state` 类型（pyright strict） | `state` 动态属性 | 依赖函数返回类型标注 `DemoService`，必要时 `cast`；保持 pyright 0 错误 |
| Kiwi 用例 ID 待分配 | 先登记后写码 | 实施时登记 demo 6 条并回填 `kiwi_id`；测试记录中登记用例清单 |

## 13. 对齐记录 <a id="align"></a>

| # | 事项 | 定稿口径 | 落点 |
| --- | --- | --- | --- |
| 1 | 分层占位形态 | 占位文件**仅 docstring + TODO**，不定义符号（归 02/03 域任务填充） | §5 |
| 2 | demo 实现 | **内存字典 CRUD**，api→service→repository 真实走通；03 域替换 repository | §7 |
| 3 | 路由前缀 | 业务路由经聚合挂 **`/api/v1`**；`/healthz` 与根路由保持根路径 | §6 |
| 4 | 测试范围 | **全量 CRUD 用例**（6 条）+ 既有 2 条；用例**先登记 Kiwi 再写代码** | §9 |
| 5 | tests 同构 | 接口测试收 `tests/api/`；其余同构子目录随用例按需创建（不建空目录） | §3/§9 |
| 6 | alembic 占位 | `alembic/README.md` 目录占位，迁移体系由 03-6 交付 | §5 |

> 本文档依《文档生成规范》编写
