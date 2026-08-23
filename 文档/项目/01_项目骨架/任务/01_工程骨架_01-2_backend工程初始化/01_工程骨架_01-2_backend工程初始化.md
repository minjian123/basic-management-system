# 01-2 backend 工程初始化

> 项目骨架 · 01 工程骨架 · 子任务 01-2

[文档首页](../../../../文档首页.md) › [01 工程骨架](../01_工程骨架.md) › 01-2 backend 工程初始化　|　[← 父任务](../01_工程骨架.md)

## 1. 任务信息 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 编号 | 01-2 |
| 父任务 | [01 工程骨架](../01_工程骨架.md) |
| 对应需求 | [01-2](../../需求/01_需求_工程骨架.md#r01-2) |
| 禅道任务 | 135（父任务 129） |
| 工时（重估） | 3h |
| 依赖 | 01-1（monorepo 骨架） |
| 负责人 | minjian |
| 状态 | 未开始 |
| 完成日期 | — |

## 2. 任务内容 <a id="content"></a>

1. `backend/pyproject.toml`：uv 构建系统；`[project]` 元数据（name `bms-backend`、requires-python `>=3.14`）；dependencies 运行时依赖 + `[dependency-groups]` dev（pytest/pytest-asyncio/httpx/pytest-cov/ruff/pyright）；ruff/pyright 配置节（line-length 120、严格模式）
2. `.python-version` 固定 3.14；`config.toml` 占位；`alembic.ini` 占位
3. 应用工厂：`app/main.py` 导出 `create_app()`（集中创建 FastAPI 实例、注册中间件/路由/异常处理器/健康检查，lifespan 内加载配置与日志）；启动入口 `uvicorn app.main:create_app --factory`；`app/__init__.py` 暴露 `__version__`
4. FastAPI 实例基线：title「BMS 基础管理系统」、版本 `__version__`、`/docs` 与 `/openapi.json` 可用；根路由 `GET /` 返回 `{code: 0, message: "ok", data: {name, version}}`
5. 测试基线：`tests/` + `conftest.py`（httpx ASGITransport 客户端 fixture）

## 3. 完成标准 <a id="accept"></a>

`uv sync` 通过；`uv run uvicorn app.main:create_app --factory` 启动无报错，`/docs`、`/openapi.json`、`/` 三端点 200；`uv run ruff check .` 与 `uv run pyright` 无错误；`uv run pytest` 通过（含 1 条根路由冒烟用例）。

## 4. 参考文档 <a id="ref"></a>

- 《项目规划说明》2.1/17
- 《后端开发规范》第 2 节
- 《命名规范》第 6 节

> 本文档依《文档生成规范》编写 · 生成日期：2026-08-23
