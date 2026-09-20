# BMS 后端（backend）

> FastAPI 后端工程（**阶段一已交付**：分层目录 + 后端基座（接口占位）+ 配置 / 日志 / 健康检查真实落地）

## 项目简介

BMS 平台后端服务：Python 3.14 + FastAPI + uvicorn + Pydantic v2 + SQLAlchemy 2.0（异步）+ Alembic。阶段一交付：monorepo 分层目录、L0 根基类与集合体系、模块基类（仓储 / 服务 / 请求响应 / ORM）、core 横切基座（异常体系 + 配置 / 安全 / 日志）、跨阶段基座与能力域基座**接口占位**（应用可启动、依赖注入可解析、占位可断言）、配置管理 / 日志体系 / 健康检查（`/healthz` `/readyz`）真实实现。机制类真实实现随首个落库阶段（认证 / RBAC）回补，待办见《[项目骨架计划](../bms文档/项目/01_项目骨架/计划/01_计划_项目骨架.md)》「后续阶段待办」节。

## 快速启动

前置：Python 3.14（uv 管理）。

```bash
cd backend
uv sync
uv run uvicorn app.asgi:app --port 8000
# 验证：/healthz 返回 {"status":"ok"}；/readyz 就绪（依赖不可达为 503）；/docs Swagger
uv run pytest   # 全量用例（含 Kiwi TCMS 用例 ID 标注）

# 本地门禁（与 CI 同口径）
uv run ruff check . && uv run ruff format --check . && uv run pyright
uv run pytest -q --cov=app --cov-branch --cov-fail-under=70   # 覆盖率门禁 ≥ 70%
uv run python -m ops.check_modules                            # 模块注册清单校验
cd .. && python3 scripts/tools/base-check/check-base.py        # 基座自检（须在仓库根）
python3 scripts/tools/check-docs/check-status.py              # 需求 / 任务 / 计划状态一致性
```

## 依赖与版本

依赖由 `uv` 管理，版本以 `uv.lock` 锁定（必须提交）；Python 版本由 `.python-version` 固定（当前 **3.14**）。下表为 2026-09-10 验证时的锁定版本，日常以 `uv.lock` 为准。

**运行时依赖**：

| 依赖 | 版本 | 用途 |
| --- | --- | --- |
| fastapi | 0.141.1 | Web 框架 |
| uvicorn[standard] | 0.52.4 | ASGI 服务器 |
| pydantic / pydantic-settings | 2.13.5 / 2.15.0 | 校验与配置 |
| sqlalchemy | 2.0.52 | ORM |
| alembic | 1.19.2 | 数据库迁移 |
| aiosqlite / aiomysql | 0.22.1 / 0.3.2 | SQLite / MySQL 异步驱动 |
| psycopg[binary] | 3.3.5 | PostgreSQL 异步驱动 |
| dmPython | 2.5.38 | 达梦官方同步驱动 |
| structlog | 26.1.0 | 结构化日志 |
| redis | 8.1.0 | 缓存 / 有序集合封装（redis.asyncio） |
| python-multipart | 0.0.32 | 表单 / 文件上传 |
| httpx | 0.28.1 | HTTP 客户端与测试 |
| sortedcontainers | 2.4.0 | 有序集合基座（core/collections） |

**开发依赖**：pytest 9.1.1、pytest-asyncio 1.4.0、pytest-cov 7.1.0、ruff 0.16.6、pyright 1.1.411、fakeredis 2.38.0（含 lupa 2.8，Redis 封装测试）。

**Python 3.14 兼容验证（2026-09-10）**：

- 上列全部运行 / 开发依赖在 **Python 3.14.4** 安装并通过 import 冒烟；`uv run pytest` 全量用例通过（覆盖率 100%）。
- Celery 5.6.3、SpiffWorkflow 3.2.0 以 `uv run --with` **临时环境**安装并通过 import 冒烟（阶段二前仅验证，不写入锁定依赖）。
- dmPython 2.5.38 连接开发环境达梦 DM8 实例执行 `SELECT 1` 通过（凭据不入库，连接方式见内部部署文档）。
- **结论：保持 Python 3.14**（未触发回退）。若后续任一核心依赖在 3.14 不兼容：整体回退 3.13（`.python-version`、`requires-python>=3.13`、重新 `uv lock`、全量测试通过），并同步更新《项目规划说明》2.1/17 与《开发部署规划》第 10 节。

## 目录结构

```text
backend/
├── .python-version   # 固定 Python 3.14
├── pyproject.toml    # 元数据 + 依赖 + ruff / pyright / pytest 配置
├── uv.lock           # 依赖锁定（必须提交）
├── config.toml       # 配置基线（分区与关键键，逐项注释；不含密钥）
├── config.dev.toml   # dev 环境覆盖（日志 console/DEBUG、CORS 放行本地前端）
├── config.test.toml  # test 环境覆盖（日志 json/INFO、CORS 空）
├── config.prod.toml  # prod 环境覆盖（日志 json/WARNING、CORS 空）
├── .env.example      # 全部 BMS_ 应用键模板（复制为 .env 使用，密钥留空）
├── alembic.ini       # 迁移配置占位（落库阶段（认证 / RBAC）填充）
├── alembic/          # 迁移目录占位（落库阶段（认证 / RBAC）填充）
├── README.md         # 本文件
├── typings/          # 局部类型存根（sortedcontainers / fakeredis，pyright stubPath）
├── benchmarks/       # 微基准（bench_collections.py，手动执行、CI 不跑）
├── ops/              # 运维脚本：check_modules（模块注册清单）/ migrate_tenants / init_tenant / test_db（测试库流程，占位）
├── app/
│   ├── __init__.py   # 暴露 __version__
│   ├── main.py       # 应用工厂 create_app：中间件 / 异常处理器 / 路由 / 能力域装配（无模块级 app）
│   ├── core/         # L0 根基类 · 集合体系（有序 / 并发 / Redis）· 中间层基类 · core 横切（配置 / 异常 / 安全 / 日志 / 序列化 / 锁 / 雪花 ID / 上下文 / 资源）
│   ├── api/          # 聚合路由（demo / modules / health）+ 依赖 / 中间件 / 异常处理器
│   ├── models/       # ORM 模型：BaseModel + platform / system / demo（落库阶段填充）
│   ├── schemas/      # 契约基类 BaseSchema + 分页 / 排序 / 统一响应
│   ├── services/     # 服务基类（含事务扩展）+ 模块注册表 + demo 服务
│   ├── repositories/ # 仓储基类（契约 / 内存 / 作用域 / DB 骨架）+ demo 仓储
│   ├── db/           # 数据访问底座（引擎 / 会话 / 读写路由 / 租户 / 引擎注册表 / 工作单元，接口占位）
│   ├── health/       # 健康检查项注册表 + 真实探针（redis / database）
│   ├── cache/ scope/ sharding/ events/ tasks/ audit/
│   │                 # 六类跨阶段基座（缓存 Region / 数据范围 / 分片路由 / 事件 / 任务 / 审计），接口占位
│   ├── archive/ captcha/ circuit/ dashboard/ fallback/ fieldtype/ i18n/ idempotency/ idp/ llm/ lock/ masking/
│   ├── metrics/ notify/ oauth/ outbound/ password/ permission/ query/ ratelimit/ replay/ search/ session/
│   ├── storage/ tracing/ transfer/ workflow/ ws/
│   │                 # 补充扩展基座（需求 02-17 ~ 02-41），接口占位（Null 实现），真实实现随对应阶段回补
│   └── …             # 分层、基类与占位状态以《后端基类清单》为准
└── tests/
    ├── conftest.py   # ASGITransport 客户端夹具
    ├── api/ core/ repositories/ services/ schemas/   # 与 app/ 同构的单元与接口用例
    ├── db/ ops/      # 机制底座与运维脚本用例（占位断言、库清单一致性）
    ├── crosscut/     # 横切能力（限流 / 幂等 / 可观测性 / 权限等）用例
    └── integration/  # 真实外部服务集成用例（标 integration，未配环境变量即跳过）
```

## 文档导航

- 仓库根 [README](../README.md)
- 《[后端开发规范](../bms文档/规范/后端开发规范.md)》·《[后端基类清单](../bms文档/后端基类清单.md)》
- 《[架构设计 · 后端基础类体系](../bms文档/设计/架构设计/04_架构设计_后端基础类体系.md)》
- 阶段一：[需求总览](../bms文档/项目/01_项目骨架/需求/00_需求_项目骨架.md) · [任务基线](../bms文档/项目/01_项目骨架/任务/04_CI与阶段验收/04_CI与阶段验收.md) · [排期计划](../bms文档/项目/01_项目骨架/计划/01_计划_项目骨架.md) · [阶段测试报告](../bms文档/项目/01_项目骨架/01_测试报告_项目骨架.md)
- 《[项目规划说明](../bms文档/规划/项目规划说明.md)》
