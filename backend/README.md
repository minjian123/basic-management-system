# BMS 后端（backend）

> FastAPI 后端工程（**阶段一已交付**：分层目录 + 后端基座（接口占位）+ 配置 / 日志 / 健康检查真实落地）

## 项目简介

BMS 平台后端服务：Python 3.14 + FastAPI + uvicorn + Pydantic v2 + SQLAlchemy 2.0（异步）+ Alembic。阶段一交付：monorepo 分层目录、L0 根基类与集合体系、模块基类（仓储 / 服务 / 请求响应 / ORM）、core 横切基座（异常体系 + 配置 / 安全 / 日志）、跨阶段基座与能力域基座**接口占位**（应用可启动、依赖注入可解析、占位可断言）、配置管理 / 日志体系 / 健康检查（`/healthz` `/readyz`）真实实现。机制类真实实现随首个落库阶段（认证 / RBAC）回补，待办见《[项目骨架计划](../bms文档/项目/01_项目骨架/计划/01_计划_项目骨架.md)》「后续阶段待办」节。

## 快速启动

前置：Python 3.14（uv 管理）。

```bash
cd backend
uv sync
uv run python -m bms_platform          # 各服务启动入口（读 config 的 [server] host/port；SIGTERM 先摘流再优雅收尾）
# 其他服务：python -m bms_identity / bms_tenant / bms_org / bms_file / bms_notification / bms_search / bms_ai / bms_report
# 本地并行多服务时用 BMS_SERVER__PORT 覆盖端口（每服务独立配置归 06_需求）
# 或：uv run uvicorn bms_platform.asgi:app --port 8000
# 验证：/healthz 返回 {"status":"ok","service":"platform","version":"..."}；/readyz 就绪（依赖不可达为 503）；/docs Swagger
uv run pytest   # 全量用例（工作区根；含 Kiwi TCMS 用例 ID 标注）
# 工程级范围：进入某工程目录 `uv run pytest` 只跑该工程（如 cd services/org / cd libs/bms_core），不落根全量

# 服务运行镜像（按服务参数化；构建上下文 backend/，锁文件一致、非目标服务源码不入镜像）
# CI 由服务子流水线 service-build / service-release 构建推送（deploy/ci/templates/backend-service.yml）
docker build --provenance=false --build-arg SERVICE=platform -f backend/Dockerfile backend/ -t bms-platform:dev
docker run --rm -p 8000:8000 bms-platform:dev        # 平台库需先迁移；容器编排 / 回滚见下
# 服务编排 / 一键部署 / 回滚 / 健康门禁（09_02，在部署机 deploy/ 目录）：
#   python3 scripts/tools/deploy/release.py --deploy-dir ~/deploy bootstrap
#   python3 scripts/tools/deploy/release.py --deploy-dir ~/deploy deploy --service platform --tag <sha 或 vX.Y.Z>
#   python3 scripts/tools/deploy/release.py --deploy-dir ~/deploy rollback --service platform
# 详见《服务编排与发布部署使用说明》（bms文档/资料/开发服务器/linux/）

# 本地门禁（与 CI 同口径）
uv run ruff check . && uv run ruff format --check . && uv run pyright
uv run pytest -q --cov=bms_core --cov=bms_platform --cov=bms_identity --cov=bms_tenant --cov=bms_org --cov=bms_file --cov=bms_notification --cov=bms_search --cov=bms_ai --cov=bms_report --cov-branch --cov-fail-under=70   # 覆盖率门禁 ≥ 70%
uv run python -m ops.check_modules                            # 模块注册清单校验
cd .. && python3 scripts/tools/base-check/check-base.py        # 基座自检（须在仓库根）
python3 scripts/tools/base-check/check-service-boundaries.py  # 服务边界护栏（共享库 / 服务依赖、分层单向、表 / 表前缀跨服务唯一）
python3 scripts/tools/check-docs/check-status.py              # 需求 / 任务 / 计划状态一致性
python3 scripts/tools/preflight/check-preflight.py            # 一键本地预检（上述门禁本地化，推送前跑；--fast 秒级只跑静态 / 基座）
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
├── pyproject.toml    # 工作区根（[tool.uv.workspace] 成员 + dev 依赖 + ruff / pyright / pytest 配置）
├── uv.lock           # 依赖锁定（必须提交）
├── config.toml       # 配置基线（分区与关键键，逐项注释；不含密钥）
├── config.dev.toml   # dev 环境覆盖（日志 console/DEBUG、CORS 放行本地前端）
├── config.test.toml  # test 环境覆盖（日志 json/INFO、CORS 空）
├── config.prod.toml  # prod 环境覆盖（日志 json/WARNING、CORS 空）
├── .env.example      # 全部 BMS_ 应用键模板（复制为 .env 使用，密钥留空）
├── alembic.ini       # 迁移配置（三链，分链版本目录）
├── alembic/          # 迁移脚本（按数据源分链：platform / tenant / archive）
├── scripts/          # 开发期脚本（new_service.py 服务脚手架）
├── README.md         # 本文件
├── typings/          # 局部类型存根（sortedcontainers / fakeredis，pyright stubPath）
├── benchmarks/       # 微基准（bench_collections.py，手动执行、CI 不跑）
├── ops/              # 运维脚本：check_modules / check_plugins / migrate_tenants / init_tenant / test_db / db_admin / seed_*
├── libs/bms_core/    # 共享基座库（各服务复用；包 bms_core，src 布局）
│   ├── pyproject.toml
│   ├── src/bms_core/
│   │   ├── application.py  # 服务应用装配基座（service_lifespan + BaseServiceApplicationFactory）
│   │   ├── core/     # L0 根基类 · 集合体系（有序 / 并发 / Redis）· 中间层基类 · core 横切（配置 / 异常 / 安全 / 日志 / 序列化 / 锁 / 雪花 ID / 上下文 / 资源）
│   │   ├── api/      # 接口层基座（路由基类 / 依赖 / 中间件 / 异常处理器 / 探针）
│   │   ├── db/       # 数据访问底座（引擎 / 会话 / 读写路由 / 租户 / 引擎注册表 / 工作单元 / 迁移链）
│   │   ├── repositories/  # 仓储基类（契约 / 内存 / 作用域 / DB 实现）
│   │   ├── services/ # 服务基类（含事务扩展）+ 模块注册表
│   │   ├── schemas/  # 契约基类 BaseSchema + 分页 / 排序 / 游标 / 统一响应
│   │   ├── models/   # ORM 基类 BaseModel + 平台基础模型（sys_tenant / sys_module）
│   │   └── <能力域>/ # 横切能力域（cache / lock / health / storage / tracing / … 契约与实现）
│   └── tests/        # 基座库测试（不依赖具体服务应用）
└── services/         # 9 个服务工程（一服务一工程一库；02_03 拆分）
    ├── platform/       # 平台地基 / 配置服务（服务目录 / 插件 / 字典 / 图标 / 偏好 / 查询方案 / 代码校验 + demo 样板）
    ├── identity/       # 认证与身份服务（验证码）
    ├── tenant/         # 租户与配置服务
    ├── org/            # 组织主数据服务
    ├── file/           # 文件服务
    ├── notification/   # 通知服务
    ├── search/         # 检索服务
    ├── ai/             # AI 服务
    └── report/         # 报表打印服务
        └── <各服务>/   # pyproject.toml + src/bms_<服务>/（main / asgi + api / services / repositories / models / schemas）+ tests/
```

> 新增服务用 `python scripts/new_service.py <服务名>` 生成同构骨架；分层职责、依赖方向（服务只依赖共享库与自身、共享库不依赖服务、服务之间不互相 import）与目录登记见《[后端开发规范](../bms文档/规范/后端开发规范.md)》。

## 文档导航

- 仓库根 [README](../README.md)
- 《[后端开发规范](../bms文档/规范/后端开发规范.md)》·《[后端基类清单](../bms文档/后端基类清单.md)》
- 《[架构设计 · 后端基础类体系](../bms文档/设计/架构设计/04_架构设计_后端基础类体系.md)》
- 阶段一：[需求总览](../bms文档/项目/01_项目骨架/需求/00_需求_项目骨架.md) · [任务基线](../bms文档/项目/01_项目骨架/任务/04_CI与阶段验收/04_CI与阶段验收.md) · [排期计划](../bms文档/项目/01_项目骨架/计划/01_计划_项目骨架.md) · [阶段测试报告](../bms文档/项目/01_项目骨架/01_测试报告_项目骨架.md)
- 《[项目规划说明](../bms文档/规划/项目规划说明.md)》
