# monorepo 多服务工程与共享基座库详细设计

> 后端基座与服务化地基 · 02 多服务骨架与仓库 · 01 monorepo 多服务工程与共享基座库 · 详细设计

[文档首页](../../../../../../文档首页.md) › [01 monorepo 多服务工程与共享基座库](../02_多服务骨架与仓库_01_monorepo 多服务工程与共享基座库.md) › 01 详细设计　|　[父任务：多服务骨架与仓库](../../02_多服务骨架与仓库.md) · [本阶段需求](../../../../需求/02_需求_多服务骨架与仓库.md) · [排期计划](../../../../计划/01_计划_后端基座与服务化地基.md)

## 1. 概述 <a id="overview"></a>

- **目标**：把 `backend/` 从「单一 Python 包 `app`」改造为 **monorepo 多服务工程**——根为 uv 工作区，`libs/bms_core/` 承载**共享基座库**（core 横切 + 数据访问底座 + 模块基类 + 全部横切能力域契约与实现 + 服务化语义基座预留位），`services/platform/` 承载**首个平台地基服务**（应用入口 + 接口层 + 平台业务模块），二者物理隔离、可分别构建；服务内按 api / services / repositories / models / schemas 分层且依赖单向；服务之间只经公开契约或事件；新增机器护栏与 CI 接线，使「共享库可复用、无重复实现、依赖单向无循环」可执行验证。
- **依据**：《微服务演进规划》「目标架构与服务清单」「仓库形态」「阶段与排期影响」「与现状差异及迁移」节；《架构设计 · 总体架构》「工程结构（Monorepo）」「分层视图」「进程模型」节；《架构设计 · 后端基础类体系》「微服务形态」注；《后端开发规范》「目录与分层职责」「后端基座体系（强制）」节；需求 [02-1](../../../../需求/02_需求_多服务骨架与仓库.md#r02-1)。
- **范围（本任务）**：
  1. **uv 工作区与工程骨架**：`backend/pyproject.toml` 改为工作区根（虚拟工程 + 共享工具与 dev 依赖配置），`libs/bms_core` 与 `services/platform` 各自独立 `pyproject.toml`（src 布局），可分别 `uv build`。
  2. **共享基座库抽取**：现 `app/` 的**基座内核**迁入 `bms_core`（core / db / repositories 基类 / services 基类 / schemas 基类 / models 基类与平台基础模型 / api 基座 / 全部横切能力域）。
  3. **平台服务落地**：现 `app/` 的应用入口、接口路由与平台业务模块迁入 `bms_platform`（api 全量 + main/asgi + demo 五层示例 + 平台业务模型）。
  4. **全量 import 重命名**：`app.*` → `bms_core.*` / `bms_platform.*`（源码、测试、`alembic/`、`ops/` 一并改写），删除旧 `app` 包，不留兼容 shim。
  5. **测试随工程走**：基座库测试 `libs/bms_core/tests/`、服务测试 `services/platform/tests/`，各自独立 `conftest.py`，根 `pytest` 汇总门禁。
  6. **边界机器护栏**：新增 `scripts/tools/base-check/check-service-boundaries.py`（共享库不得依赖服务、服务不得互相 import、服务内分层方向单向），接入 CI；基座对账脚本扫描路径改为 `libs/**` + `services/**`。
  7. **服务脚手架脚本**：新增 `backend/scripts/new_service.py`，按同一骨架生成新服务工程（供 02_03 与后续加服务复用）。
  8. **工程适配**：`alembic/` `ops/` `config*.toml` 暂留 `backend/` 根，仅改 import 与路径常量；CI 后端 job 与 CI 基础镜像 Dockerfile 适配工作区。
- **不含（明确归口，见第 8 节）**：现有单体按限界上下文拆分为多个服务（02_03）；每服务独立配置与迁移链（06_需求）；数据所有权硬校验与 CI 越界度量（05_02）；父-子流水线与按服务构建发布（09_需求）；服务运行与探针（02_02）。

## 2. 现状与差距 <a id="gap"></a>

| 关注点 | 现状 | 差距（本任务目标） |
| --- | --- | --- |
| 仓库形态 | `backend/` 单 `pyproject.toml` + 单包 `app/`；所有代码同进程同包 | uv 工作区：`libs/bms_core/` + `services/platform/` 各自独立工程 |
| 共享基座库 | 无独立库，基座与业务同包 `app` | 基座内核对齐为 `bms_core` 可安装包，各服务复用 |
| 服务工程 | 无服务概念，`app` 即唯一应用 | `bms_platform` 服务工程存在，服务内五层分层就位 |
| import 根 | 全量 `app.*`（源码 ~250 文件、测试 ~133 文件、`ops`/`alembic` 若干） | 全量改写为 `bms_core.*` / `bms_platform.*`，删除旧包 |
| 测试组织 | 单 `backend/tests/`（导入 `app.main`） | 随工程走：`libs/bms_core/tests` + `services/platform/tests` |
| 边界护栏 | 无「服务边界 / 共享库反向依赖」机器护栏 | 新增护栏脚本 + CI，完成标准可执行验证 |
| 基座对账 | `check-backend-base.py` 扫描 `backend/app/**` | 扫描 `backend/libs/**` + `backend/services/**`，自检样例同步 |
| CI / 镜像 | job 直跑 `uv run`，镜像 `uv sync --no-install-project` | 适配工作区（镜像 `--no-install-workspace`、job 补 `uv sync`、`--cov` 改包名） |
| 迁移 / 运维 / 配置 | 在 `backend/` 根，import `app.*` | 暂留原位，import 与 `BACKEND_ROOT` 等路径常量适配 |

## 3. 交付物清单 <a id="tree"></a>

目标目录结构（**新** = 新增，**迁** = 由 `app/` 迁入，**暂留** = 保持位置仅改内部引用）：

```text
backend/
├── pyproject.toml                 # 改：工作区根（[tool.uv.workspace] + dev 依赖 + ruff/pyright/pytest）
├── uv.lock                        # 改：工作区锁（成员依赖合并）
├── alembic.ini                    # 暂留
├── alembic/                       # 暂留（env.py import 改 bms_core）
├── benchmarks/  typings/          # 暂留
├── config.toml  config.*.toml     # 暂留
├── ops/                           # 暂留（import 改 bms_core / bms_platform）
├── scripts/
│   └── new_service.py             # 新：服务脚手架脚本
├── libs/
│   └── bms_core/                  # 新：共享基座库工程（包 bms-core）
│       ├── pyproject.toml         #   新：独立工程（src 布局）
│       ├── src/bms_core/
│       │   ├── __init__.py        #   新：库版本
│       │   ├── core/              #   迁：根系 / 集合 / 横切 / 配置 / 异常 / 日志 / 插件 / 工厂 / 资源
│       │   ├── db/                #   迁：引擎 / 会话 / 路由 / 租户 / 迁移 / 建删库 / 同步门面
│       │   ├── repositories/      #   迁：Base* 与 ordering（不含 demo_repository）
│       │   ├── services/          #   迁：Base* 与 module_registry（不含 demo_service）
│       │   ├── schemas/           #   迁：基类 / 分页 / 游标 / 过滤 / 排序 / 各域契约（不含 demo）
│       │   ├── models/            #   迁：base（BaseModel）+ platform（SysTenant / SysModule）
│       │   ├── api/               #   迁：base / errors / middleware / health / deps（接口层基座）
│       │   └── <横切能力域>/       #   迁：archive audit cache captcha chat circuit codecheck dashboard dict
│       │                          #       events fallback fieldtype globalsearch health i18n icon idempotency
│       │                          #       idp listing llm lock masking metrics notification notify oauth org
│       │                          #       outbound password permission preference print query ratelimit replay
│       │                          #       scope search session sharding storage tasks tenant tracing transfer
│       │                          #       workflow ws
│       └── tests/                 #   新：基座库测试（原 tests 中不依赖服务的用例迁入）
└── services/
    └── platform/                  # 新：平台地基服务工程（包 bms-platform）
        ├── pyproject.toml         #   新：独立工程（src 布局，依赖 bms-core）
        ├── src/bms_platform/
        │   ├── __init__.py        #   新：服务版本
        │   ├── main.py            #   迁：应用工厂（ApplicationFactory + lifespan）
        │   ├── asgi.py            #   迁：ASGI 入口（uvicorn bms_platform.asgi:app）
        │   ├── api/               #   迁：业务路由 + router.py 聚合（captcha chat codecheck demo dict file icon
        │   │                      #       modules notification org plugins preference print query_scheme search tenant）
        │   ├── services/          #   迁：demo_service.py（服务五层示例）
        │   ├── repositories/      #   迁：demo_repository.py
        │   ├── models/            #   迁：system.py / ai.py / demo.py（平台业务与骨架表模型）
        │   └── schemas/           #   迁：demo.py
        └── tests/                 #   新：服务测试（原 tests 中依赖 app.main/api 的用例迁入）
```

## 4. 领域设计 <a id="design"></a>

### 4.1 工程布局与工作区 <a id="layout"></a>

```text
backend/pyproject.toml            工作区根（虚拟工程，无 [project]）
  ├── [tool.uv.workspace] members = ["libs/*", "services/*"]
  ├── [dependency-groups] dev     pytest / ruff / pyright / fakeredis / allure / minio / kiwitcms
  └── [tool.ruff] [tool.pyright] [tool.pytest.ini_options]   共享工具配置
libs/bms_core/pyproject.toml      包 bms-core（依赖 fastapi/sqlalchemy/pydantic/structlog/redis/…）
services/platform/pyproject.toml  包 bms-platform（依赖 bms-core + fastapi/uvicorn；工作区源引用）
```

- **可分别构建**：`uv build --package bms-core` / `uv build --package bms-platform` 各自出 wheel；`uv sync` 默认把两成员以可编辑方式装入工作区 `.venv`，故 pytest / `python -m ops` / uvicorn 均可直接 import，无需额外 `PYTHONPATH`。
- **包名与导入根**：`bms_core` / `bms_platform`（沿用 `bms_` 前缀，避免与标准库 `platform` 冲突）；服务工程目录名 `platform` 与包名 `bms_platform` 对应。
- **pyright 路径**：src 布局下 pyright 需 `extraPaths = ["libs/bms_core/src", "services/platform/src"]` 方能解析跨工程导入；`include` 扩为 `libs` / `services` / `tests`（根 tests 已不存在，改为各工程内）。
- **pytest 收集**：`testpaths = ["libs/bms_core/tests", "services/platform/tests"]`；`pythonpath = ["."]` 保留（`ops` 为未安装的根脚本区，供测试导入）；`--cov=bms_core --cov=bms_platform`。

### 4.2 共享基座库边界 <a id="core-boundary"></a>

**判据**：`bms_core` 是「除业务模块与入口外的一切基座」——基类体系、数据访问底座、横切能力域（契约与实现）、平台基础模型与接口层基座；**`bms_core` 不得 import 任何 `bms_platform` 或 `services/*` 包**（反向依赖禁止，护栏断言）。

| 归属 | 内容 |
| --- | --- |
| `bms_core`（共享基座库） | `core`、`db`、`repositories`（Base* + ordering）、`services`（Base* + `module_registry`）、`schemas`（基类与各能力域契约，除 demo）、`models`（base / platform）、`api`（base / errors / middleware / health / deps）、全部横切能力域目录 |
| `bms_platform`（平台服务） | `main` / `asgi` / `__init__`、`api`（业务路由 + 聚合 + demo 路由）、`services/demo_service`、`repositories/demo_repository`、`models`（system / ai / demo）、`schemas/demo` |

- **平台基础模型随库的原因**：`db/tenant_source.py` 需 `SysTenant`（租户解析底座）、`services/module_registry.py` 与迁移元数据需 `SysModule`；二者是平台级基础设施模型，暂随库承载，服务边界定案（02_03）时再评估所有权。
- **骨架表模型（`system.py` / `ai.py`）随服务**：仅迁移元数据引用，未进任何迁移链表集，不产生反向依赖；随服务承载更贴合「业务模型归服务」。
- **能力域及其实现随库**：`dict` / `listing` / `org` / `notification` / `print` / `icon` / `codecheck` / `globalsearch` / `chat` / `tenant` / `preference` 等横切基座的**契约与默认/真实实现、自带 schemas 与 models** 随库；其**对外接口路由**随服务（服务负责组装与暴露）。

### 4.3 import 映射与改写口径 <a id="import-map"></a>

全量改写按「模块前缀字典」逐文件替换（非无差别 `app.` → `bms_core.`）：

| 原前缀 | 新前缀 |
| --- | --- |
| `app.main` / `app.asgi` / `app.api.<业务路由>` / `app.api.router` / `app.services.demo_service` / `app.repositories.demo_repository` / `app.models.{system,ai,demo}` / `app.schemas.demo` | `bms_platform.*` |
| `app.api.{base,errors,middleware,health,deps}` / `app.core` / `app.db` / `app.repositories`（含 `demo_repository` 外的全部）/ `app.services`（含 `demo_service` 外的全部）/ `app.schemas`（含 `demo` 外的全部）/ `app.models.{base,platform}` / 全部横切能力域 | `bms_core.*` |

- **补丁脚本**：以「按文件内引用的目标模块决定前缀」的 Python 脚本执行 `git mv` 后统一改写；改毕以 `python -c "import …"` 与应用启动冒烟为准，测试全绿即证。
- **删除旧包**：`backend/app/` 迁空后删除，不留 `app` shim（避免双命名期）。
- **路径常量**：`db/migration.py` 的 `BACKEND_ROOT` 由 `parents[2]` 调整为相对 `bms_core` 包定位 `backend/` 的新层级（`libs/bms_core/src/bms_core/db/migration.py` → `backend/` 为 `parents[4]`），并单测断言其指向含 `alembic.ini` 的目录。

### 4.4 服务运行与接口层 <a id="service-wiring"></a>

- **入口**：`bms_platform/main.py` 保留 `ApplicationFactory` + `lifespan` 语义，装配来源改 `bms_core.core.assembly` 等库内基座；`bms_platform/asgi.py` 暴露模块级 `app`（`uvicorn bms_platform.asgi:app`）。
- **接口层基座与业务路由分离**：`BaseRouter` / 异常处理器 / 公共中间件 / 健康探针 / 依赖提供者（`deps.py`）归 `bms_core.api`，供所有服务复用；具体业务路由归 `bms_platform.api`，经 `router.py` 登记聚合后挂 `/api/v1`。
- **不改行为**：本任务只做物理搬迁与命名，路由前缀、响应体、中间件顺序、探针口径、插件装配全部保持一致（由既有测试全绿证明）。

### 4.5 测试组织与 conftest 拆分 <a id="tests"></a>

- **归属判定**：单个测试文件若有 import 落到 `bms_platform`（`main` / `asgi` / 业务路由 / demo）或使用 `client` 夹具，则归 `services/platform/tests/`；其余归 `libs/bms_core/tests/`。
- **conftest**：两份各一套——
  - 服务侧 `conftest.py`：沿用现有夹具（`isolate_settings` / `platform_db` / `reset_request_context` / `client`，其中 `client` 经 `bms_platform.main` 构造应用）。
  - 基座库侧 `conftest.py`：提供 `isolate_settings` / `reset_request_context` / `platform_db`（经 `ops.seed_tenant` 播种平台库，不依赖服务应用），**不提供 `client`**。
- **根 pytest 汇总**：`testpaths` 同时覆盖两工程，CI 一条命令跑全量；覆盖率按包名汇总。
- **`ops` / `alembic` 测试**：`tests/ops`、`tests/alembic` 仅依赖库与根脚本区，归基座库测试（`ops` 属平台运维脚本区、非服务包）。

### 4.6 服务边界机器护栏 <a id="guard"></a>

新增 `scripts/tools/base-check/check-service-boundaries.py`（与 `check-backend-base.py` 同目录、同风格，支持 `--self-test`）：

| # | 规则 | 断言口径 |
| --- | --- | --- |
| 1 | 共享库不得依赖服务 | `bms_core` 源码 import 中不得出现 `bms_platform` 或其余服务包名 |
| 2 | 服务不得互相 import | 任一 `services/*/src/*` 包不得 import 另一服务包 |
| 3 | 服务内分层单向 | `api → services → repositories → models/schemas`；反向（如 `models` import `api`）即失败；`models` 不得 import `api/services/repositories` |
| 4 | 服务只经共享库与自身 | 服务可 import `bms_core.*` 与自身包，不得 import 其它 `services/*` |

- **接入 CI**：`base-integrity` job 增跑该脚本 + `--self-test`。
- **与后续衔接**：05_02「数据所有权与边界硬校验」在本护栏之上加表前缀 / 跨库访问维度；本任务只做进程与包级边界。

### 4.7 服务脚手架脚本 <a id="scaffold"></a>

`backend/scripts/new_service.py`：`python -m scripts.new_service <服务名>`（或直接 `python scripts/new_service.py <服务名>`）按同一骨架生成：

```text
services/<name>/
├── pyproject.toml                 # 包 bms-<name>，依赖 bms-core
├── src/bms_<name>/
│   ├── __init__.py                # 服务版本
│   ├── main.py                    # 最小 ApplicationFactory（含 /healthz 走共享库探针）
│   ├── api/{__init__,router}.py   # 路由聚合挂载
│   ├── services/  repositories/  models/  schemas/（含 __init__.py 与分层 docstring）
└── tests/conftest.py  tests/test_service_boot.py
```

- 服务名校验：snake_case、非保留名、未与既有服务冲突；生成即 `uv sync` 可运行。
- 脚本自身有单测（生成到临时目录并断言文件齐备、可 import）。

### 4.8 工程适配（alembic / ops / CI / 镜像） <a id="engineering"></a>

| 项 | 处理 |
| --- | --- |
| `alembic/env.py` | import `app.core.*` → `bms_core.core.*`；模型注册经 `bms_core.db.migration` |
| `ops/*` | import 改 `bms_core.*`；`check_plugins.py` 的 `app.main` → `bms_platform.main` |
| `db/migration.py` | `_MODEL_MODULES` 去掉 demo（迁服务）与 system/ai（迁服务）；`BACKEND_ROOT` 层级修正 |
| CI 后端 job | 各 job `cd backend` 后补 `uv sync --frozen`（工作区成员需装入镜像预建 venv 之外）；`--cov=app` → `--cov=bms_core --cov=bms_platform`；`ruff check .` / `pyright` 覆盖新目录 |
| CI 基础镜像 `Dockerfile.backend` | `uv sync --frozen --no-install-project` → `--no-install-workspace`（成员源码未入镜像，运行时由 job `uv sync` 装入） |
| e2e / swagger / 三库 job | 同上补 `uv sync --frozen`；其余命令不变 |
| `.gitlab-ci.yml` 触发路径 | `backend/**/*` 已覆盖，无需改 |

## 5. 失败分支与边界 <a id="failures"></a>

| 场景 | 处理 |
| --- | --- |
| 工作区根无 `[project]` | uv 支持虚拟工作区根；`uv sync` 装配全部成员，`uv run` 正常 |
| 服务 import 另一服务内部实现 | `check-service-boundaries.py` 失败（规则 2/4），CI 拦截 |
| `bms_core` import 服务 | 护栏失败（规则 1），CI 拦截 |
| 服务内反向依赖（如 models→api） | 护栏失败（规则 3），CI 拦截 |
| `db/migration.py` 找不到 `backend/` | `BACKEND_ROOT` 单测断言其下存在 `alembic.ini`；层级修正后通过 |
| 迁移元数据缺 `sys_task` / `ai_chat_log` | 二者未进任何链表集，移除模型模块登记不影响迁移；用例断言链元数据仅含链表集 |
| 测试归错工程（用了服务夹具却落库侧） | 归并口径 + 双 conftest；全量 pytest 收集即暴露（fixture 未找到 / import 失败） |
| CI 镜像 venv 缺工作区成员 | job 补 `uv sync --frozen`；镜像改 `--no-install-workspace` |
| 「无重复实现」无法机器判定 | 以「基座内核对齐为单一可安装库、服务只引用不复制」守恒：护栏规则 1 禁服务反向、人工核对交付清单 |

## 6. 测试设计与验收映射 <a id="tests"></a>

用例先登记 Kiwi TCMS（本任务登记 **1 条**，编号以平台回读为准，见第 9 节）。

| Kiwi | 用例 | 类型 | 断言要点 |
| --- | --- | --- | --- |
| 见 §9 | 多服务工程与共享基座库 | 单元 + 集成 | 见下表 |
| 见 §9 | 工作区与工程可分别构建 | 集成 | 工作区成员解析出 `bms_core` / `bms_platform`；两包可 `import` 与元数据可读 |
| 见 §9 | 共享库反向依赖与服务互相依赖护栏 | 单元 | 构造违规样例触发护栏（规则 1~4），合规样例放行（`--self-test`） |
| 见 §9 | 服务脚手架 | 单元 | 生成到临时目录后目录/文件齐备、可 import、命名非法被拒 |
| 见 §9 | 应用装配与路由不变 | 集成 | `bms_platform` 应用可构造、lifespan 通过、探针与既有路由口径不变 |
| 见 §9 | 既有回归 | 单元 | 全量 `pytest` / `ruff` / `pyright` 全绿（搬迁无回归） |

验收映射：

| 完成标准（需求 02-1） | 验证方式 |
| --- | --- |
| 多服务工程可分别构建 | 工作区解析 + 两包 import / 元数据用例（第 6 节） |
| 共享基座库被复用且无重复实现 | `bms_platform` 依赖并复用 `bms_core`；护栏规则 1 禁反向；交付清单核对 |
| 服务内分层依赖单向、无循环 | 护栏规则 3（分层方向）+ 规则 2/4（跨服务） |
| `pytest` / `ruff` / `pyright` 全绿 | 门禁命令（见第 9 节） |

## 7. 登记落点 <a id="registry-writeback"></a>

| 落点 | 内容 |
| --- | --- |
| 《后端基类清单》 | 分层总览与各节代码位置 `app/…` → `libs/bms_core/src/bms_core/…`（接口层基座 → `bms_core/api/`）；新增 monorepo 工程结构说明 |
| 《后端开发规范》 | §2「目录与分层职责」目录树改为工作区结构（libs/services），补服务工程分层与依赖方向口径 |
| 《架构设计 · 总体架构》 | 「工程结构（Monorepo）」补后端工作区具体形态（libs/services 与共享库边界） |
| 《架构设计 · 后端基础类体系》 | 「微服务形态」注补共享基座库落点 |
| 计划 | §1 工时台账；§2 已完成表（02_01 行）；§3 移除 02_01；§4 甘特移除已完成节点 |
| 任务 / 父任务 | 状态两处一致（需求文档不承载进度） |
| Kiwi TCMS | 登记本任务用例并回读编号 |
| 实施 / 测试记录 | 任务目录 `实施/`、`测试/` 各一份 |
| 测试资产仓 | `scripts/kiwi/cases|exports/` 对应用例与导出 |

## 8. 边界与开放项 <a id="boundary"></a>

- **归 02_03**：现有单体按限界上下文拆分为多个服务（能力域与业务模块迁出 `bms_core`）、服务目录登记。
- **归 06_需求**：每服务独立配置与迁移链（database-per-service 的工程侧细化）。
- **归 05_02 / 09_需求**：数据所有权与跨库访问硬校验、父-子流水线与按服务构建发布。
- **开放项**：`bms_core` 当前承载全部横切能力域契约与实现，服务拆分（02_03）后按服务裁剪实际装配范围（本任务不做按服务裁剪）；平台基础模型（`SysTenant` / `SysModule`）暂随库，所有权随服务边界定案评估；`ops` 暂留 `backend/` 根、不属任何工程，后续随运维脚本归属再定。
- **不改**：路由前缀与响应体、中间件顺序、插件装配语义、探针口径、迁移链路与表集、四库方言行为。

## 9. 实施步骤 <a id="steps"></a>

```mermaid
flowchart LR
    A["Kiwi 用例登记（先登记后编码）"] --> B["建工作区根 + bms_core / bms_platform 工程骨架"]
    B --> C["git mv 代码入 libs / services + 全量 import 改写"]
    C --> D["测试随工程拆分 + 双 conftest"]
    D --> E["alembic / ops / 路径常量适配"]
    E --> F["边界护栏脚本 + 服务脚手架脚本"]
    F --> G["CI / Dockerfile / 工具配置适配"]
    G --> H["门禁全绿 + 申请启动冒烟"]
    H --> I["登记回写 + 实施/测试记录 + 提交"]
```

1. 读《KiwiTCMS 部署使用说明》「用例约定」节，登记本任务用例并**回读编号**。
2. 建工作区根 `pyproject.toml`、`libs/bms_core/pyproject.toml`、`services/platform/pyproject.toml`。
3. `git mv` 迁源码到 `libs/bms_core/src/bms_core`，按映射改写 import；建 `bms_platform` 包并迁入口 / 路由 / demo / 平台模型。
4. 测试按口径拆分并落双 conftest；删根 `tests/`。
5. `alembic/env.py`、`ops/*`、`db/migration.py` 路径常量与 import 适配。
6. 新增 `scripts/tools/base-check/check-service-boundaries.py`（含 `--self-test`）与 `backend/scripts/new_service.py`。
7. `.gitlab-ci.yml`（`uv sync` / `--cov` / 护栏）与 `deploy/ci/Dockerfile.backend` 适配。
8. 门禁：`uv run pytest -q --cov=bms_core --cov=bms_platform --cov-branch` / `uv run ruff check .` / `uv run ruff format --check .` / `uv run pyright`；基座校验与边界护栏。
9. 应用启动冒烟（`uv run python -m uvicorn bms_platform.asgi:app` 或 TestClient）。
10. 登记回写 + 实施 / 测试记录 + 提交（代码与文档分开）。

关键命令：

```bash
cd backend
uv sync --frozen                 # 装配工作区成员（bms_core / bms_platform）
uv run pytest -q --cov=bms_core --cov=bms_platform --cov-branch
uv run ruff check . && uv run ruff format --check . && uv run pyright
python3 ../scripts/tools/base-check/check-backend-base.py
python3 ../scripts/tools/base-check/check-service-boundaries.py
python3 ../scripts/tools/base-check/check-service-boundaries.py --self-test
uv build --package bms-core && uv build --package bms-platform
```

## 10. 决策记录（对齐记录） <a id="align"></a>

| # | 事项 | 结论（逐项确认） |
| --- | --- | --- |
| 1 | 本任务交付边界 | **骨架 + 抽库 + 1 个平台服务**（业务模块进一步拆分留 02_03） |
| 2 | 物理布局 | **`libs/` + `services/` + uv workspace**，每工程独立 pyproject（src 布局） |
| 3 | 共享库包名与导入根 | **`bms_core`**（服务包 `bms_platform`） |
| 4 | 抽取程度 | **基座内核全抽**：core + db + 模块基类 + 全部横切能力域契约与实现 + 跨阶段基座契约 |
| 5 | 首批服务工程 | **平台服务 + 服务脚手架脚本** |
| 6 | import 迁移方式 | **一次性全量重命名**，删旧 `app` 包，无 shim |
| 7 | 测试组织 | **随工程走**（libs/bms_core/tests + services/platform/tests，根 pytest 汇总） |
| 8 | alembic / ops / config 归属 | **暂留 backend 根**，仅改 import 与路径常量 |
| 9 | 边界护栏 | **新增并接入 CI**（`check-service-boundaries.py`） |

## 11. 参考文档 <a id="ref"></a>

- [架构设计 · 总体架构](../../../../../../设计/架构设计/03_架构设计_总体架构.md)「工程结构（Monorepo）」「进程模型」节
- [架构设计 · 后端基础类体系](../../../../../../设计/架构设计/04_架构设计_后端基础类体系.md)「微服务形态」注
- [微服务演进规划](../../../../../../规划/微服务演进规划.md)「目标架构与服务清单」「仓库形态」「与现状差异及迁移」节
- [后端开发规范](../../../../../../规范/后端开发规范.md)「目录与分层职责」「后端基座体系（强制）」节
- [后端基类清单](../../../../../../后端基类清单.md)
- [需求 02-1：monorepo 多服务工程与共享基座库](../../../../需求/02_需求_多服务骨架与仓库.md#r02-1)
- [KiwiTCMS 部署使用说明](../../../../../../资料/开发服务器/linux/KiwiTCMS部署使用说明.md)「用例约定」节

> 本文档依《[文档生成规范](../../../../../../规范/文档生成规范.md)》编写 · 关键决策逐项确认
