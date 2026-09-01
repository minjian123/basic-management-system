# 06 依赖锁定与 Python 3.14 兼容验证

> 项目骨架 · 01 工程骨架 · 子任务 06

[文档首页](../../../../文档首页.md) › [01 工程骨架](../01_工程骨架.md) › 06 依赖锁定与 Python 3.14 兼容验证　|　[← 父任务](../01_工程骨架.md)

## 1. 任务信息 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 编号 | 06 |
| 父任务 | [01 工程骨架](../01_工程骨架.md) |
| 对应需求 | [01-6](../../需求/01_需求_工程骨架.md#r01-6) |
| 工时（重估） | 3h |
| 依赖 | 02（backend pyproject 骨架） |
| 负责人 | minjian |
| 状态 | 未开始 |
| 完成日期 | — |

## 2. 任务内容 <a id="content"></a>

1. 运行时依赖清单落位：fastapi、uvicorn[standard]、pydantic v2 + pydantic-settings、sqlalchemy>=2.0、alembic、aiosqlite、aiomysql、psycopg[binary]、dmPython、structlog、redis、python-multipart、httpx；Celery/SpiffWorkflow/authlib/slowapi 等仅登记占位不安装
2. `uv.lock` 提交仓库，`uv sync` 全量可复现；依赖升级走 Renovate（pep621 口径）
3. Python 3.14 验证矩阵（逐依赖安装 + import 冒烟，结论登记表格）：dmPython 连 mjbk 达梦 5236 实测 `SELECT 1`；任一核心依赖不兼容 → 整体回退 3.13（.python-version、requires-python、重新 uv lock）
4. 结论落 `backend/README.md`「依赖与版本」节；回退时同步更新《项目规划说明》2.1/17 与《开发部署规划》第 10 节

## 3. 完成标准 <a id="accept"></a>

`uv lock` + `uv sync` 通过；验证矩阵全部登记（含达梦连接实测结果）；兼容结论落 backend/README.md 并回写《项目规划说明》；回退发生时 `uv run pytest` 在目标版本全绿。

## 4. 参考文档 <a id="ref"></a>

- 《项目规划说明》2.1/3.1/17
- 《开发部署规划》第 10 节
- 《总体项目规划》第 10 节

> 本文档依《文档生成规范》编写 · 生成日期：2026-08-23
