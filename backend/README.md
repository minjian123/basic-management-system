# BMS 后端（backend）

> FastAPI 后端工程（阶段一最小可启动占位，02 / 03 细化为完整分层）

## 项目简介

BMS 平台后端服务：Python 3.14 + FastAPI + uvicorn（后续按阶段引入 Pydantic v2、SQLAlchemy 2.0 异步、Alembic 等）。阶段一先交付最小可启动占位，配置 / 日志 / 异常 / 健康检查 / 数据底座在 02、03 细化。

## 快速启动

前置：Python 3.14（uv 管理）。

```bash
cd backend
uv sync
uv run uvicorn app.main:create_app --factory --port 8000
# 验证：访问 http://127.0.0.1:8000/healthz 返回 {"status":"ok"}
uv run pytest   # 冒烟用例（含 Kiwi TCMS 用例 ID 标注）
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
├── config.toml       # 配置占位（02-1 填充）
├── alembic.ini       # 迁移配置占位（03-6 填充）
├── alembic/          # 迁移目录占位（03-6 填充）
├── README.md         # 本文件
├── typings/          # 局部类型存根（sortedcontainers / fakeredis，pyright stubPath）
├── benchmarks/       # 微基准（bench_collections.py，手动执行、CI 不跑）
├── app/
│   ├── __init__.py   # 暴露 __version__
│   ├── main.py       # 应用工厂：聚合路由 + 404 临时处理器
│   ├── core/         # 根基类/有序集合/并发集合/Redis 封装 + 配置/安全/异常占位
│   ├── api/          # 路由：health（/healthz）+ demo（/api/v1/demos）
│   ├── models/       # ORM 模型（base 占位、demo 内存模型）
│   ├── schemas/      # Pydantic 模型（base 基类、common 占位、demo 请求/响应）
│   ├── services/     # 业务服务（base_service 基类 + demo_service）
│   ├── repositories/ # 数据访问（base_repository 基类 + demo_repository）
│   ├── db/           # 引擎 / 会话（占位，02-5 填充）
│   ├── tasks/        # Celery 任务占位
│   ├── ws/           # Socket.IO 占位
│   └── i18n/         # 国际化占位
└── tests/
    ├── conftest.py   # ASGITransport 客户端夹具
    ├── api/          # 接口测试：test_main / test_health / test_demo
    ├── core/         # 根基类/集合/并发/Redis 测试
    ├── integration/  # 真实外部服务集成用例（标 integration，随 05-02 执行）
    ├── repositories/ # 基类测试：test_base_repository
    ├── services/     # 基类测试：test_base_service
    └── schemas/      # 基类测试：test_base_schema
```

## 文档导航

- 仓库根 [README](../README.md)
- 《[后端开发规范](../bms文档/规范/后端开发规范.md)》（02 起遵循）
- 《[项目规划说明](../bms文档/规划/项目规划说明.md)》
