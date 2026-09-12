# 依赖锁定与 Python 3.14 兼容验证实施记录

> 项目骨架 · 01 工程骨架 · 子任务 06 · 实施记录 01

[文档首页](../../../../../../文档首页.md) › [06 依赖锁定与 Python 3.14 兼容验证](../01_工程骨架_06_依赖锁定与Python3.14兼容验证.md) › 01 实施记录　|　[详细设计 →](../设计/06_详细设计_01_依赖锁定与Python3.14兼容验证.md)

## 1. 实施信息 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 任务 | [06 依赖锁定与 Python 3.14 兼容验证](../01_工程骨架_06_依赖锁定与Python3.14兼容验证.md) |
| 对应需求 | [01-6](../../../../需求/01_需求_工程骨架.md#r01-6) |
| 详细设计 | [06_详细设计_01_依赖锁定与Python3.14兼容验证](../设计/06_详细设计_01_依赖锁定与Python3.14兼容验证.md) |
| 实施日期 | 2026-09-10 |
| 实施人 | minjian |
| 实施环境 | 开发机（Ubuntu）；Python 3.14.4（uv 0.12.7）；开发环境达梦 DM8 实例（5236）；npm 无需 |
| 提交 | —（随本批提交，见仓库 git log） |
| 结论 | 全量依赖 3.14 安装/导入通过、Celery/SpiffWorkflow 临时冒烟通过、dmPython 连达梦 `SELECT 1` 通过；**保持 Python 3.14** |

## 2. 实施概览 <a id="overview"></a>

```mermaid
flowchart LR
    A[锁定复现检查] --> B[全量依赖矩阵（版本+import）]
    B --> C[Celery/SpiffWorkflow 临时冒烟]
    C --> D[dmPython 达梦实测]
    D --> E[结论落 backend/README]
    E --> F[记录与状态回写]
```

## 3. 实施过程 <a id="process"></a>

### 3.1 锁定与复现

- `uv.lock` 持续提交（01-02 起，后续新增 `sortedcontainers`、`fakeredis[lua]` 均入库）；`uv sync --frozen` 在当前环境可复现；
- 锁文件变更触发 CI 基础镜像自动重建（05-1 基础镜像按 lock 哈希 label）——本任务登记关联，不重复实现。

### 3.2 依赖矩阵（版本 + import）

- 逐项收集 `importlib.metadata.version` 并 import 冒烟，覆盖运行依赖 15 项（fastapi 0.141.1 … sortedcontainers 2.4.0）与开发依赖 6 项（pytest 9.1.1 … fakeredis 2.38.0 + lupa 2.8）；
- 结果：**全部 import OK**（矩阵表见 `backend/README.md`「依赖与版本」节与[测试记录 §3](../测试/06_测试_01_依赖锁定与Python3.14兼容验证.md#run)）。

### 3.3 Celery / SpiffWorkflow 临时冒烟

- `UV_DEFAULT_INDEX=清华源 uv run --with celery --with SpiffWorkflow python -c "import celery, SpiffWorkflow"`；
- 结果：Celery **5.6.3**、SpiffWorkflow **3.2.0** 安装 + import 通过（临时环境，不写入锁定依赖）。

### 3.4 dmPython 达梦实测

- 凭据从本地 gitignore 凭据文档/mjbk `~/deploy/.env` 读取（不回显、不入库），运行时通过临时文件传入；
- `dmPython.connect(user=SYSDBA, ...)` → `SELECT 1` 返回 `1`，实测通过。

### 3.5 结论落档与回写

- `backend/README.md` 新增「依赖与版本」节：依赖清单（版本 + 用途）、矩阵结论、dmPython 实测说明、回退口径；
- 未触发回退，故《项目规划说明》「技术栈」「环境与配置」节 与《开发部署规划》「分阶段落地计划」节不改动。

## 4. 问题与处置 <a id="issues"></a>

| # | 问题 / 现象 | 原因 | 处置 | 落点 |
| --- | --- | --- | --- | --- |
| 1 | 本地 `deploy/.env` 无达梦口令，实测需凭据 | 口令由达梦部署随机生成，存于 mjbk `~/deploy/.env` | 从远端取回并回填各仓库 `deploy/.env`（gitignore；不回显、不入库） | 本记录 |
| 2 | 凭据探测脚本在 backend 工作目录下相对路径失效 | 脚本内用了相对 `bms文档/...` | 改为绝对路径 | 本记录 |
| 3 | Celery / SpiffWorkflow 不在锁定依赖 | 规划为阶段三占位 | 用 `uv run --with` 临时环境冒烟，不动 `uv.lock` | 设计 §3 |

## 5. 验证结果 <a id="verify"></a>

| 验证点（完成标准） | 方法 | 结果 |
| --- | --- | --- |
| `uv lock` + `uv sync` 通过 | `uv sync --frozen` | 通过（锁文件复现） |
| 验证矩阵全部登记 | 版本 + import 脚本 | 通过（全部 OK） |
| Celery / SpiffWorkflow 安装冒烟 | `uv run --with` | 通过（5.6.3 / 3.2.0） |
| 含达梦连接实测结果 | dmPython `SELECT 1` | 通过（返回 1） |
| 兼容结论落 `backend/README.md` | README 节核对 | 通过（保持 3.14） |
| 回退口径 | 未触发；触发条件已写入 README | 通过 |
| Kiwi 用例 | Case 27 登记与映射 | 通过 |

## 6. 偏差与遗留 <a id="deviation"></a>

- 矩阵版本为 2026-09-10 快照，日常以 `uv.lock` 为准；依赖升级由 Renovate 走 MR。
- Celery / SpiffWorkflow 仅安装冒烟，**不代表阶段三功能验收**。
- 达梦实测为连接级 `SELECT 1`；SQLAlchemy 方言与同步驱动封装口径在 02-5 落地（先修订架构 09/后端规范第 8 节）。
- 未启用 Python 3.14 free-threading 构建，启用后复跑并发微基准（01-3-2 边界）。

> 本文档依《文档生成规范》编写 · 按《任务文档规范》「实施文档（任务执行记录）」节实施文档结构组织
