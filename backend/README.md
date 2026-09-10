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
├── app/
│   ├── __init__.py   # 暴露 __version__
│   ├── main.py       # 应用工厂：聚合路由 + 根路由
│   ├── core/         # 配置 / 安全 / 异常（占位，02 域填充）
│   ├── api/          # 路由：health（/healthz）+ demo（/api/v1/demos）
│   ├── models/       # ORM 模型（base 占位、demo 内存模型）
│   ├── schemas/      # Pydantic 模型（common 占位、demo 请求/响应）
│   ├── services/     # 业务服务（demo_service，内存实现）
│   ├── repositories/ # 数据访问（demo_repository，内存字典）
│   ├── db/           # 引擎 / 会话（占位，02-5 填充）
│   ├── tasks/        # Celery 任务占位
│   ├── ws/           # Socket.IO 占位
│   └── i18n/         # 国际化占位
└── tests/
    ├── conftest.py   # ASGITransport 客户端夹具
    └── api/          # 接口测试：test_main / test_health / test_demo
```

## 文档导航

- 仓库根 [README](../README.md)
- 《[后端开发规范](../bms文档/规范/后端开发规范.md)》（02 起遵循）
- 《[项目规划说明](../bms文档/规划/项目规划说明.md)》
