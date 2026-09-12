# 依赖锁定与 Python 3.14 兼容验证详细设计

> 项目骨架 · 01 工程骨架 · 子任务 06 · 详细设计

[文档首页](../../../../../../文档首页.md) › [06 依赖锁定与 Python 3.14 兼容验证](../01_工程骨架_06_依赖锁定与Python3.14兼容验证.md) › 01 详细设计　|　[← 任务文档](../01_工程骨架_06_依赖锁定与Python3.14兼容验证.md)

## 1. 概述 <a id="overview"></a>

- **目标**：验证 Python 3.14.4 与 backend 全量依赖（运行 + 开发）的兼容性，固化 `uv.lock` 可复现锁定，并把**验证矩阵与兼容结论**落到 `backend/README.md`「依赖与版本」节；不兼容时执行整体回退 3.13 口径。
- **范围**：依赖矩阵（安装 + import 冒烟 + 版本登记）、Celery / SpiffWorkflow 临时环境安装冒烟、dmPython 连 mjbk 达梦 5236 实测 `SELECT 1`、结论落档与状态回写；不改业务代码、不新增运行时依赖。
- **依据**：需求 [01-6](../../../../需求/01_需求_工程骨架.md#r01-6)、《总体项目规划》「风险管理」节风险表、《开发部署规划》「分阶段落地计划」节、《项目规划说明》「技术栈」「后端核心」「环境与配置」节。

## 2. 现状与差距 <a id="gap"></a>

| 现状 | 差距 |
| --- | --- |
| 运行/开发依赖已全量落 `pyproject.toml` + `uv.lock`（01-02 起；后续新增 `sortedcontainers`、`fakeredis[lua]`）× 锁文件变更触发 CI 基础镜像自动重建（05-1） | 清单与锁定已就位；**验证矩阵未登记** |
| `pytest` 全量在 Python 3.14.4 下全绿（含 sortedcontainers / fakeredis / lupa） | 未形成逐依赖「版本 + import」矩阵与结论 |
| Celery / SpiffWorkflow 属阶段四占位未安装 | 需按需求做**安装冒烟**（不写入锁定依赖） |
| dmPython 已安装（2.5.38）且 import OK | **未做真实连接实测**（mjbk 达梦 5236 `SELECT 1`） |
| `backend/README.md` 无「依赖与版本」节 | 结论无落点 |

## 3. 验证方法设计 <a id="method"></a>

- **环境**：开发机 Python 3.14.4（uv 0.12.7）；mjbk 达梦 DM8 5236（凭据运行时读取本地凭据文档，不入库）。
- **矩阵口径**（逐依赖）：
  1. 版本：`importlib.metadata.version(<dist>)` 记录实锁版本；
  2. 安装：锁定环境 `uv sync --frozen` 可复现（01-02 起持续验证）；
  3. 导入：`import <module>` 冒烟（dist → module 映射见实施记录）；
  4. 行为验证：`uv run pytest` 全量（现有 69+ 用例）与覆盖率 100% 作为整体行为证据。
- **Celery / SpiffWorkflow**：`uv run --with celery --with SpiffWorkflow` 临时环境安装并 import（**不写入**项目锁定依赖）；登记版本与结论。
- **dmPython 实测**：`dmPython.connect(user=SYSDBA, ...)` → `SELECT 1`，记录版本、实例地址（泛化）与结果。
- **判定与回退**：全部通过 → **保持 3.14**；任一核心依赖不兼容 → 整体回退 3.13（`.python-version`、`requires-python>=3.13`、重新 `uv lock`、迁移后 `uv run pytest` 全绿、同步更新规划文档）。

## 4. 结论落点 <a id="output"></a>

- `backend/README.md` 新增「依赖与版本」节：依赖清单（版本 + 用途，分组运行/开发）、Python 3.14 验证矩阵结论、dmPython 实测说明、回退口径与触发条件。
- 回退未发生时，《项目规划说明》「技术栈」「环境与配置」节 与《开发部署规划》「分阶段落地计划」节不改动（口径未变）。

## 5. 测试设计与用例 <a id="tests"></a>

| 验证项 | 方法 | 结果登记 |
| --- | --- | --- |
| 依赖安装/导入矩阵 | 脚本逐项收集版本 + import | 01_06 测试记录 |
| 全量行为回归 | `uv run pytest` + `--cov` | 复用现有 69+ 用例（回归） |
| Celery / SpiffWorkflow | `uv run --with` 安装 + import | 测试记录 |
| dmPython 连接实测 | mjbk 达梦 5236 `SELECT 1` | 测试记录 |
| 结论一致性 | README「依赖与版本」节核对 | 任务完成标准 |

## 6. 实施步骤 <a id="steps"></a>

1. 依赖矩阵收集（版本 + import）与锁定复现检查。
2. Celery / SpiffWorkflow 临时环境冒烟。
3. dmPython 达梦连接实测（本地凭据，不回显、不入库）。
4. `backend/README.md` 增「依赖与版本」节（清单 + 矩阵结论 + 回退口径）。
5. 测试/实施记录；任务、需求、计划、父任务与总览状态回写。
6. `check-base` 校验与提交。

## 7. 验收映射 <a id="accept-map"></a>

| 完成标准 | 验证方式 |
| --- | --- |
| `uv lock` + `uv sync` 通过 | `uv sync --frozen` 复现命令 |
| 验证矩阵全部登记 | 矩阵输出 + 测试记录 |
| 含达梦连接实测结果 | dmPython `SELECT 1` 输出 |
| 兼容结论落 `backend/README.md` 并回写《项目规划说明》 | README 节核对；未回退时规划不改动、在记录中说明 |

## 8. 边界与开放项 <a id="boundary"></a>

- Celery / SpiffWorkflow 仅安装冒烟，**不代表阶段四功能验收**（接入时再按模块验证）。
- 达梦实测为连通性（`SELECT 1`），SQLAlchemy 方言接入在 02-5（含同步驱动口径修订）。
- 未启用 Python 3.14 free-threading 构建；启用后复跑微基准（01-3-2 边界）。
- CI 基础镜像重建依赖锁哈希（05-1），本任务不重复实现。

## 9. 对齐记录 <a id="align"></a>

| # | 事项 | 结论 |
| --- | --- | --- |
| 1 | 矩阵口径 | 逐依赖版本 + import 冒烟；行为验证复用全量 pytest（回归） |
| 2 | Celery/SpiffWorkflow | `uv run --with` 临时环境冒烟，不写入锁定依赖 |
| 3 | dmPython 实测 | 本地 gitignore 凭据运行时读取，不回显、不入库；连 mjbk 达梦 5236 `SELECT 1` |
| 4 | 回退口径 | 未发生则不修改规划文档；触发时按既定 3.13 流程执行 |
| 5 | 锁文件联动 | 锁变更触发 CI 基础镜像重建（05-1），本任务只登记关联 |

> 本文档依《文档生成规范》编写 · 关键决策逐项确认
