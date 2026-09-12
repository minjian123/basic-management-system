# 依赖锁定与 Python 3.14 兼容验证测试记录

> 项目骨架 · 01 工程骨架 · 子任务 06 · 测试记录 01

[文档首页](../../../../../../文档首页.md) › [06 依赖锁定与 Python 3.14 兼容验证](../01_工程骨架_06_依赖锁定与Python3.14兼容验证.md) › 01 测试记录　|　[实施记录 →](../实施/06_实施_01_依赖锁定与Python3.14兼容验证.md)　[详细设计 →](../设计/06_详细设计_01_依赖锁定与Python3.14兼容验证.md)

## 1. 测试信息 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 任务 | [06 依赖锁定与 Python 3.14 兼容验证](../01_工程骨架_06_依赖锁定与Python3.14兼容验证.md) |
| 对应需求 | [01-6](../../../../需求/01_需求_工程骨架.md#r01-6) |
| 详细设计 | [06_详细设计_01_依赖锁定与Python3.14兼容验证](../设计/06_详细设计_01_依赖锁定与Python3.14兼容验证.md) |
| 实施记录 | [01 实施记录](../实施/06_实施_01_依赖锁定与Python3.14兼容验证.md) |
| 测试日期 | 2026-09-10 |
| 测试人 | minjian |
| 测试环境 | 开发机（Ubuntu）；Python 3.14.4（uv 0.12.7）；开发环境达梦 DM8 实例（5236） |
| Kiwi 用例 | 本任务新增 Case 27（依赖锁定与 Python 3.14 兼容矩阵） |
| 结论 | 矩阵全部通过；Celery/SpiffWorkflow 冒烟通过；dmPython `SELECT 1` 通过；回归 69 passed；保持 Python 3.14 |

## 2. 测试范围与用例 <a id="scope"></a>

**范围**：Python 3.14.4 下全量运行/开发依赖的安装与 import 冒烟、Celery/SpiffWorkflow 临时环境安装冒烟、dmPython 连接达梦 `SELECT 1`、锁文件复现与全量回归。不含：SQLAlchemy 三方言接入（02-5）、Celery/SpiffWorkflow 功能验收（阶段四）、free-threading 构建。

| Kiwi ID | 用例 | 类型 | 执行方式 | 结果 |
| --- | --- | --- | --- | --- |
| 27 | 依赖锁定与 Python 3.14 兼容矩阵（运行/开发依赖 import、Celery/SpiffWorkflow 冒烟、dmPython 实测） | 环境·兼容 | 矩阵脚本 + `uv run --with` + dmPython 脚本 | 通过 |
| — | 全量行为回归 | 单元·接口 | `uv run pytest --cov=app --cov-branch` | 通过（69 passed、2 skipped） |

## 3. 执行记录与结果 <a id="run"></a>

**依赖矩阵（Python 3.14.4，2026-09-10 快照）**：

| 依赖 | 版本 | import |
| --- | --- | --- |
| fastapi | 0.141.1 | OK |
| uvicorn | 0.52.4 | OK |
| pydantic / pydantic-settings | 2.13.5 / 2.15.0 | OK |
| sqlalchemy | 2.0.52 | OK |
| alembic | 1.19.2 | OK |
| aiosqlite / aiomysql | 0.22.1 / 0.3.2 | OK |
| psycopg | 3.3.5 | OK |
| dmPython | 2.5.38 | OK |
| structlog | 26.1.0 | OK |
| redis | 8.1.0 | OK |
| python-multipart | 0.0.32 | OK |
| httpx | 0.28.1 | OK |
| sortedcontainers | 2.4.0 | OK |
| fakeredis / lupa | 2.38.0 / 2.8 | OK |
| pytest / pytest-asyncio / pytest-cov | 9.1.1 / 1.4.0 / 7.1.0 | OK |
| ruff / pyright | 0.16.6 / 1.1.411 | 工具（无需 import） |

**Celery / SpiffWorkflow 冒烟**：

```bash
UV_DEFAULT_INDEX=清华源 uv run --with celery --with SpiffWorkflow python -c "import celery, SpiffWorkflow"
# celery 5.6.3 import OK；SpiffWorkflow 3.2.0 import OK（临时环境，不写入 uv.lock）
```

**dmPython 达梦实测**：

```text
dmPython.connect(user=SYSDBA, 开发环境达梦实例 5236) → SELECT 1 => 1
# 凭据运行时读取（本地 gitignore），不回显、不入库
```

**回归**：

```text
uv run pytest --cov=app --cov-branch -q
# 69 passed, 2 skipped（integration 需环境注入）；TOTAL 842 语句 0 缺失、行 100%、分支 99%（1 处 partial）
```

## 4. 问题与处置 <a id="issues"></a>

| # | 问题 / 现象 | 原因 | 处置 | 落点 |
| --- | --- | --- | --- | --- |
| 1 | 达梦口令本地缺失导致初测失败 | 口令生成于部署时并存 mjbk `~/deploy/.env` | 取回回填 `deploy/.env`（gitignore）后实测通过 | [实施记录 §4](../实施/06_实施_01_依赖锁定与Python3.14兼容验证.md#issues) |

## 5. 覆盖率 <a id="coverage"></a>

| 范围 | 语句 | 未覆盖 | 行覆盖 | 分支覆盖 |
| --- | --- | --- | --- | --- |
| `backend/app`（全量） | 842 | 0 | 100% | 99%（1 处 partial，非门禁阻断） |

口径：`uv run pytest --cov=app --cov-branch`；CI 门禁阈值（整体 ≥ 70%）由 05-1 执行。

## 6. 偏差与遗留 <a id="deviations"></a>

- 矩阵为 2026-09-10 快照，后续以 `uv.lock` 为准；升级走 Renovate MR。
- Celery / SpiffWorkflow 仅安装冒烟，功能验证随阶段四。
- 达梦为连接级实测；SQLAlchemy 方言接入与同步驱动封装随 02-5（先修订架构 09/后端规范 §8）。
- free-threading 构建未启用，启用后复跑并发微基准。

> 本文档依《文档生成规范》编写 · 按《任务文档规范》「测试文档（任务测试记录）」节测试文档结构组织
