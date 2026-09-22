# monorepo 多服务工程与共享基座库实施记录

> 后端基座与服务化地基 · 02 多服务骨架与仓库 · 01 monorepo 多服务工程与共享基座库 · 实施记录

[文档首页](../../../../../../文档首页.md) › [01 monorepo 多服务工程与共享基座库](../02_多服务骨架与仓库_01_monorepo 多服务工程与共享基座库.md) › 01 实施　|　[详细设计](../设计/01_详细设计_01_monorepo 多服务工程与共享基座库.md) · [测试记录](../测试/01_测试_01_monorepo 多服务工程与共享基座库.md)

## 1. 实施信息 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 任务 | [01 monorepo 多服务工程与共享基座库](../02_多服务骨架与仓库_01_monorepo 多服务工程与共享基座库.md) |
| 对应需求 | [02-1](../../../../需求/02_需求_多服务骨架与仓库.md#r02-1) |
| 详细设计 | [01_详细设计_01_monorepo 多服务工程与共享基座库](../设计/01_详细设计_01_monorepo 多服务工程与共享基座库.md) |
| 实施日期 | 2026-09-22 |
| 实施人 | minjian |
| 实施环境 | 开发机（Ubuntu，Python 3.14.4 / uv 0.12.7，工作区 `.venv`） |
| 提交 | 设计与实施 / 测试记录与代码分开提交（`docs(02_01)` / `feat(02_01)`） |
| 结论 | 完成 |

## 2. 实施概览 <a id="overview"></a>

```mermaid
flowchart LR
    A["Kiwi 用例登记（先登记后编码）"] --> B["建 uv 工作区 + bms_core / bms_platform 工程骨架"]
    B --> C["git mv 代码入 libs / services + 全量 import 改写"]
    C --> D["测试随工程拆分 + 双 conftest"]
    D --> E["config / migration 路径常量 + 硬编码 parents 修正"]
    E --> F["服务边界护栏脚本 + 服务脚手架脚本"]
    F --> G["CI / Dockerfile / 工具配置适配"]
    G --> H["门禁全绿 + 独立构建 + 登记回写与记录"]
```

## 3. 实施过程 <a id="process"></a>

1. **Kiwi 用例登记（先登记后编码）**：登记 1 条策展用例覆盖全部断言面，平台回读编号 **1204**；登记输入 `scripts/kiwi/cases/2026-09-22_阶段二02-01_monorepo多服务工程与共享基座库.json`。
2. **工作区与工程骨架**：`backend/pyproject.toml` 改为 uv 工作区根（虚拟工程，`[tool.uv.workspace] members = ["libs/*", "services/*"]` + dev 依赖 + ruff / pyright / pytest 配置）；新增 `libs/bms_core/pyproject.toml`（包 `bms-core`，src 布局，hatchling）与 `services/platform/pyproject.toml`（包 `bms-platform`，依赖 `bms-core` 工作区源）；`uv sync` 装配两成员。
3. **代码物理搬迁**：`git mv app libs/bms_core/src/bms_core`；`main.py` / `asgi.py` / `__init__.py`、业务路由（demo / dict / org / notification / icon / print / codecheck / preference / listing / globalsearch / chat / tenant / file / captcha / modules / plugins / query_scheme / search / router）、demo 五层（models / repositories / services / schemas）、平台业务模型（system / ai / demo）迁入 `services/platform/src/bms_platform`；接口层基座（base / errors / middleware / health / deps）留共享库 `bms_core/api`。
4. **全量 import 重命名**：按「模块前缀字典」逐文件将 `app.*` 改写为 `bms_core.*` / `bms_platform.*`（源码 / 测试 / `alembic` / `ops`），删除旧 `app` 包，不留 shim。
5. **测试随工程**：按「是否依赖服务应用 / `client` 夹具 / 契约支持模块」拆分——`libs/bms_core/tests`（61 文件，含 alembic / db / integration / ops / schemas / repositories 等）+ `services/platform/tests`（72 文件，含 api / 契约 / 插件装配 / 各能力域应用级用例）；各建 `conftest.py`（基座库侧不依赖服务应用、不提供 `client`）；服务测试树加包结构以支持 `tests.contracts.support` 导入。
6. **路径常量与硬编码修正**：`bms_core/core/config.py` 的 `_CONFIG_DIR` 与 `bms_core/db/migration.py` 的 `BACKEND_ROOT` 由硬编码层级改为**向上搜根**（分别找 `config.toml` / `alembic.ini`）；`migration._MODEL_MODULES` 仅保留库内链表模型；修正 7 处测试硬编码 `parents[N]` 与扫描 `app/` 的路径。
7. **服务边界机器护栏**：新增 `scripts/tools/base-check/check-service-boundaries.py`（四项规则 + `--self-test`）；套内 `test_module_boundary` 改写为扫描 `libs` / `services` 双包；`check-backend-base.py` 扫描路径改 `backend/libs/**` + `backend/services/**`，错误码路径与自检样例同步。
8. **服务脚手架**：新增 `backend/scripts/new_service.py`（含 `scripts/__init__.py`），生成独立工程骨架（pyproject + 五层 + 入口 + 冒烟用例）；命名 / 保留名 / 重名校验。
9. **CI 与镜像适配**：`.gitlab-ci.yml` 后端各 job 补 `uv sync --frozen`（工作区成员装入预建 venv 之外）、`--cov=app` → `--cov=bms_core --cov=bms_platform`、三库集成用例路径改 `libs/bms_core/tests/integration`、swagger 入口改 `bms_platform.main`；`deploy/ci/Dockerfile.backend` 改 `--no-install-workspace` 并复制成员 pyproject。
10. **门禁与构建**：`uv run pytest` → 898 passed / 36 skipped；覆盖率 96%（≥ 70% 门禁）；`ruff check` / `ruff format --check` / `pyright` 全绿；`uv build --package bms-core|bms-platform` 各自出 wheel。
11. **登记回写与记录**：见 §6 与测试记录。

## 4. 问题与处置 <a id="issues"></a>

| 问题 | 现象 | 处置 |
| --- | --- | --- |
| import 改写误伤同名变量 | 正则把 `app.add_middleware` / `app.state` / `app.include_router` 等 FastAPI 实例属性当成模块，改写为 `bms_core.add_middleware`（291 处），启动报 `NameError: name 'bms_core' is not defined` | 二次修复：`bms_core.<未知标识符>` / `bms_platform.<未知标识符>` 还原为 `app.<属性>`（仅作用于非已知模块名），75 文件修正；以 `import bms_platform.asgi` 与应用构造为准 |
| 配置目录定位失效 | `_CONFIG_DIR` 原 `parents[2]` 在 src 布局下指向 `src/`，配置校验报 `app / database / server 缺失` | 改为向上搜根（首个含 `config.toml` 的祖先目录） |
| 迁移工程根定位失效 | `BACKEND_ROOT` 原 `parents[2]` 指向 `src/`，Alembic 配置定位错误 | 改为向上搜根（首个含 `alembic.ini` 的祖先目录）；登记落点单测覆盖 |
| `bms_core` 缺 `__init__.py` | 首版为命名空间包，pyright 严格模式报 `__version__` 未知 | 新增 `libs/bms_core/src/bms_core/__init__.py`（库版本） |
| 基座对账扫描越界到测试 | `check-backend-base.py` 改扫 `backend/libs` 后把测试辅助类（`Entity` / `Nested` / `Point` / `RegistryContract`）当作基座类报未登记 | `index_classes` 跳过 `tests` 目录 |
| pyright 暴露 ops 历史类型问题 | 将 `ops` 纳入 `include` 后暴露 7 处既有类型错误（与本任务无关） | `include` 定为 `["libs", "services"]`（与改造前 `app` / `tests` 范围对齐，tests 已在两工程内） |
| 测试硬编码路径漂移 | 7 处 `Path(__file__).parents[N]` 与内联扫描 `app/` 在搬迁后失效（结构护栏 / null 落点 / CI 变量一致 / 提供者直连等） | 逐处按新层级修正并把扫描目标指向 `bms_core` / 双包 |
| ruff 归类漂移 | 新增 `bms_core/__init__.py` 后 ruff 将 `bms_core` 归为第一方，import 排序触发 252 处 I001 | `[tool.ruff.lint.isort] known-first-party` 显式声明自有包；`ruff check --fix` + `ruff format` 统一 |

## 5. 验证结果 <a id="verify"></a>

| 验证项 | 命令 | 结果 |
| --- | --- | --- |
| 全量用例 | `uv run pytest -q` | 898 passed / 36 skipped（跳过为真库 / 外部服务 env 守卫） |
| 覆盖率 | `uv run pytest -q --cov=bms_core --cov=bms_platform --cov-branch` | 总体 **96%**（≥ 70% 门禁） |
| 静态检查 | `uv run ruff check .` / `uv run ruff format --check .` / `uv run pyright` | 全通过（0 error） |
| 独立构建 | `uv build --package bms-core` / `uv build --package bms-platform` | 各自产出 wheel + sdist |
| 应用启动 | `python -c "import bms_platform.asgi"` | 正常构造应用 |
| 基座对账 | `python3 scripts/tools/base-check/check-backend-base.py [--self-test]` | 通过（继承链 381 条 / 基座类 84 / 平台码 32 / 迁移链 2） |
| 服务边界护栏 | `python3 scripts/tools/base-check/check-service-boundaries.py [--self-test]` | 通过；自检三项（放行 / 拦截 / 合规）全通过 |
| 文档基座校验 | `check-base.py` / `check-links.py` | 通过（174 文档一致 / 0 断链） |

## 6. 登记回写 <a id="registry"></a>

| 落点 | 内容 |
| --- | --- |
| 《后端基类清单》 | 代码位置 `app/…` → 包根相对 `bms_core/…`；§1 补「代码路径口径（2026-09-22 工作区化）」 |
| 《后端开发规范》 | §2「目录与分层职责」目录树改工作区结构（libs / services）+ 依赖方向与服务脚手架口径 |
| 《架构设计 · 总体架构》 | 「工程结构（Monorepo）」补后端工作区落点（libs / services / 共享库边界） |
| 《架构设计 · 后端基础类体系》 | 「微服务形态」注补共享基座库落点 |
| 计划 | §1 工时台账与计数、§2 已完成表（02_01 行）、§3 移除 02_01、§4 甘特调整 |
| 任务 / 父任务 | 任务 01 状态与完成日期；父任务域总览子任务表一致 |
| Kiwi TCMS | 用例 **1204**（含工作区 / 共享库 / 平台服务 / 全量重命名 / 测试组织 / 边界护栏 / 脚手架覆盖范围） |
| 测试资产仓 | 登记输入 `scripts/kiwi/cases/2026-09-22_阶段二02-01_monorepo多服务工程与共享基座库.json` |
| 实施 / 测试记录 | 本文件与[测试记录](../测试/01_测试_01_monorepo 多服务工程与共享基座库.md) |

## 7. 偏差与遗留 <a id="deviations"></a>

- **偏差（已闭环）**：① import 改写误伤变量属性（二次修复）；② 路径常量硬编码层级改向上搜根；③ pyright `include` 范围按既有基线收敛（不含 ops）；④ ruff 第一方包归类显式声明（均已在设计 §4 / §5 与本节登记）。
- **遗留（归口）**：① 业务模块按限界上下文拆分为多服务 → **02_03**；② 每服务独立配置与迁移链 → **06_需求（数据拓扑升级）**；③ 数据所有权与跨库访问硬校验、父-子流水线与按服务发布 → **05_02 / 09_需求**；④ `ops` 暂留 `backend/` 根、不属任何工程（运维脚本归属后续再定）；⑤ 平台基础模型 `SysTenant` / `SysModule` 暂随共享库（服务边界定案时评估所有权）；⑥ `bms_core` 当前承载全部横切能力域，服务拆分后按服务裁剪装配范围（本任务不做按服务裁剪）。

> 依《文档生成规范》编写 · 与《测试记录》配套
