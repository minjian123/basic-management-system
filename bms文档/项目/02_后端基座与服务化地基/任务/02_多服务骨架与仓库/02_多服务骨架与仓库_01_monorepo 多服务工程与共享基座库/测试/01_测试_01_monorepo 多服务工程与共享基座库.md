# monorepo 多服务工程与共享基座库测试记录

> 后端基座与服务化地基 · 02 多服务骨架与仓库 · 01 monorepo 多服务工程与共享基座库 · 测试记录

[文档首页](../../../../../../文档首页.md) › [01 monorepo 多服务工程与共享基座库](../02_多服务骨架与仓库_01_monorepo 多服务工程与共享基座库.md) › 01 测试　|　[详细设计](../设计/01_详细设计_01_monorepo 多服务工程与共享基座库.md) · [实施记录](../实施/01_实施_01_monorepo 多服务工程与共享基座库.md)

## 1. 测试信息 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 任务 | [01 monorepo 多服务工程与共享基座库](../02_多服务骨架与仓库_01_monorepo 多服务工程与共享基座库.md) |
| 对应需求 | [02-1](../../../../需求/02_需求_多服务骨架与仓库.md#r02-1) |
| 测试日期 | 2026-09-22 |
| 测试人 | minjian |
| Kiwi 用例 | **1204**（1 条策展用例，覆盖下列断言面） |
| 结论 | 通过 |

## 2. 测试环境 <a id="env"></a>

- 开发机（Ubuntu，Python 3.14.4 / uv 0.12.7）；工作区 `.venv`（`uv sync` 装配 `bms_core` / `bms_platform` 两成员）。
- 默认用例走 SQLite 内存 / 临时库；真库 / 外部服务用例 env 守卫跳过（本任务无真库依赖）。

## 3. 用例覆盖 <a id="coverage"></a>

| Kiwi | 用例 / 文件 | 类型 | 断言要点 |
| --- | --- | --- | --- |
| 1204 | `libs/bms_core/tests/core/test_workspace_layout.py` | 单元 | 工作区成员可解析（`bms_core` 导入 + `bms_platform` spec）；`libs/bms_core` / `services/platform` / 脚手架脚本骨架就位 |
| 1204 | `libs/bms_core/tests/ops/test_new_service.py` | 单元 | 脚手架生成目录齐备（pyproject + 五层 + 入口 + 冒烟用例）；生成件可导入并构造应用（依赖 `bms_core` 真实解析）；非法名 / 保留名 / 重名被拒 |
| 1204 | `libs/bms_core/tests/crosscut/test_module_boundary.py` | 单元 | 共享库不依赖服务；服务内分层单向；跨包私有引用拦截；扫描样本量自检（≥ 100 文件） |
| 1204 | `scripts/tools/base-check/check-service-boundaries.py --self-test` | 单元 | 护栏拦截自检：服务依赖共享库放行 / 共享库依赖服务拦截 / 合规导入放行 |
| — | 既有全量回归（`libs/bms_core/tests` + `services/platform/tests`） | 单元 + 集成 | 搬迁与重命名无行为回归（装配 / 路由 / 探针 / 迁移链 / 能力域契约） |

### 3.1 工作区与共享库复用 <a id="workspace"></a>

- `bms_core` 与 `bms_platform` 均可导入（`import bms_core` / `importlib.util.find_spec("bms_platform")`）；两包可独立 `uv build`。
- 服务经工作区源依赖 `bms-core`，接口层基座（`bms_core.api`）与能力域由服务复用、无重复实现；护栏规则 1 断言共享库无反向依赖。

### 3.2 边界与分层护栏 <a id="guard"></a>

- 脚本四项规则在真实工作区扫描通过（0 违规）；`--self-test` 三项（放行 / 拦截 / 合规）全部符合预期。
- 套内 `test_module_boundary` 扫描 `libs` + `services` 双包，覆盖源文件数满足自检阈值。

## 4. 门禁结果 <a id="gates"></a>

| 验证项 | 命令 | 结果 |
| --- | --- | --- |
| 全量用例 | `uv run pytest -q` | **898 passed / 36 skipped**（31s） |
| 覆盖率 | `uv run pytest -q --cov=bms_core --cov=bms_platform --cov-branch` | 总体 **96%**（≥ 70% 门禁） |
| lint | `uv run ruff check .` | 通过 |
| 格式化 | `uv run ruff format --check .` | 通过 |
| 类型检查 | `uv run pyright` | 0 error / 0 warning |
| 基座对账 | `python3 scripts/tools/base-check/check-backend-base.py` | 通过（继承链 381 / 基座类 84 / 平台码 32 / 迁移链 2） |
| 护栏自检 | `python3 scripts/tools/base-check/check-service-boundaries.py --self-test` | 通过 |
| 文档基座 | `python3 scripts/tools/base-check/check-base.py` / `check-links.py` | 通过 |
| 独立构建 | `uv build --package bms-core` / `--package bms-platform` | 各自产出 wheel + sdist |

## 5. 问题与处置 <a id="issues"></a>

测试期暴露的问题（import 改写误伤、路径常量漂移、测试硬编码路径、pyright 范围、ruff 归类）与处置见[实施记录](../实施/01_实施_01_monorepo 多服务工程与共享基座库.md) §4；修正后全量回归通过。

## 6. 偏差与遗留 <a id="deviations"></a>

- 无本任务范围内的未闭环测试偏差。
- 遗留归口同[实施记录](../实施/01_实施_01_monorepo 多服务工程与共享基座库.md) §7：业务拆分（02_03）、按服务配置与迁移（06）、数据所有权与流水线（05_02 / 09）、`ops` 与平台基础模型归属、按服务裁剪装配范围。

> 依《文档生成规范》编写 · 与《实施记录》配套
