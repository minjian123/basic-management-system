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
```

## 目录结构

```text
backend/
├── .python-version   # 固定 Python 3.14
├── pyproject.toml    # uv 项目声明
├── uv.lock           # 依赖锁定（必须提交）
├── README.md         # 本文件
└── app/
    ├── __init__.py   # 暴露 __version__
    └── main.py       # FastAPI 应用工厂 create_app() + /healthz
```

## 文档导航

- 仓库根 [README](../README.md)
- 《[后端开发规范](../bms文档/规范/后端开发规范.md)》（02 起遵循）
- 《[项目规划说明](../bms文档/规划/项目规划说明.md)》
