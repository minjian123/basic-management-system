# ruff 技术介绍

> lint + format 一体化代码规范工具 · BMS 后端质量门禁第一关

[文档首页](../../../文档首页.md) › [知识档案](../技术栈知识档案总览.md) › [工程化与质量](../技术栈知识档案总览.md#eng) › ruff 技术介绍　|　[← 返回总览](../技术栈知识档案总览.md)

---

## 1. 技术概述 <a id="overview"></a>

**ruff** 是 Astral 公司（《[uv](uv技术介绍.md)》同厂）出品的
Python 代码检查（lint）与格式化（format）一体化工具，用 Rust 实现，
速度比传统的 flake8 / black / isort 组合快一到两个数量级，
一条命令同时完成"查问题"和"改格式"两件事。

- **定位**：BMS 后端唯一代码规范工具，取代 flake8 / black / isort 三件套。
- **版本**：快速迭代，版本锁定在 uv.lock / 工具配置中统一管理。
- **许可**：MIT，OSI 认证开源。
- **语言**：Rust 实现，单二进制分发，无需解释器依赖。

## 2. 核心概念与原理 <a id="principles"></a>

| 概念 | 说明 |
| --- | --- |
| lint（检查） | `ruff check`：静态扫描代码问题——未用变量、未定义名、可读性、安全风险等，按规则集分类 |
| format（格式化） | `ruff format`：自动重排代码风格（缩进、换行、引号），风格与 black 兼容，无需人工争论格式 |
| 规则集（Rule） | 以代码标识引用：E/F（pycodestyle/pyflakes 基础规则）、I（isort 导入排序）、N（pep8-naming 命名）、UP（pyupgrade 现代化语法）、B（bugbear 易错点）、SIM（simplify 简化）等 |
| pyproject.toml 配置 | 集中写在 `[tool.ruff]` 段：选择启用哪些规则集、排除哪些目录，与依赖声明同文件管理 |
| 自动修复（--fix） | 可自动修的问题一键修复（如未用导入、排序），不可自动修的问题只提示人工处理 |
| pre-commit 集成 | 提交前自动跑检查，问题代码进不了仓库（本项目 CI 门禁为主，此方式可选） |
| VS Code 扩展 | 官方扩展在编辑器中实时标红并支持保存即修（Alt+Shift+F 格式化） |
| 忽略（noqa） | 个别确需例外的地方用 `# noqa: 规则码` 注释豁免，并写明理由 |
| 缓存 | 增量检查结果缓存，二次运行毫秒级返回，CI 提速明显 |

## 3. 在 BMS 项目中的用途 <a id="usage"></a>

- 作为《[项目规划说明](../../../规划/项目规划说明.md#stack-eng)》2.3 节指定的代码规范工具，替换 flake8 / black / isort（选型依据见《[项目规划说明](../../../规划/项目规划说明.md#sel-eng)》3.3 节）。
- 配置收进 `pyproject.toml` 的 `[tool.ruff]` 段，随《[uv](uv技术介绍.md)》统一管理，不额外引入配置文件。
- CI 前端门禁：MR 流水线第一道关卡就是后端 ruff 检查，不通过直接失败（见《[项目规划说明](../../../规划/项目规划说明.md#sel-ops)》3.4 节）。
- 本地命令（Windows PowerShell 与 Linux 通用）：

```bash
uv run ruff check .           # 检查全部代码
uv run ruff check . --fix     # 自动修复可修问题
uv run ruff format .          # 格式化全部代码
```

- 与《[pyright](pyright技术介绍.md)》分工明确：ruff 管"风格与低级错误"，pyright 管"类型正确性"，两个工具都在 CI 门禁内。
- 提交前自查：跑 `uv run ruff check .` 无输出即为通过，避免 CI 排队浪费。

## 4. 选型对比 <a id="compare"></a>

| 方案 | 优点 | 缺点 | 结论 |
| --- | --- | --- | --- |
| **ruff（选中）** | lint + format 一体化、速度极快、单一配置源 | 个别冷门规则移植不全（可忽略） | 性能与工程化收益全面占优，唯一选择 |
| flake8 + black + isort | 传统标配、资料多 | 三个工具配置割裂、逐个跑、慢 | 已被 ruff 替代，不采用 |
| pylint | 规则多、可自定义检查深度 | 慢、误报多、与 formatter 无整合 | 重且冗余，不采用 |
| black 单独 | 格式化标杆、零配置 | 只格式化不检查问题 | ruff format 已兼容 black 风格，无需单独引入 |

## 5. 常见问题与注意事项 <a id="pitfalls"></a>

- **行宽冲突**：`ruff format` 按 88 字符默认行宽排版，若在 lint 里开 E501（行过长）会与其冲突，二者口径保持一致。
- **--fix 需人工复核**：自动修复大体安全，但涉及删除导入、改字符串引号等变更，提交前扫一眼 diff。
- **排除第三方代码**：vendored / 生成的代码（如 alembic 脚本、迁移产物）放 `extend-exclude`，别让机器生成代码过 lint。
- **版本漂移**：本地与 CI 的 ruff 版本不一致会导致"本地通过、CI 报错"，工具版本纳入锁文件（uv.lock）管理。
- **规则取舍**：默认规则集已够用；团队确需调整在 `[tool.ruff]` 中显式声明，不要靠 `# noqa` 大量豁免。
- **与 formatter 混用其他工具**：不要再用 black/isort 格式化同一目录，两套规则会互相打架。

## 6. 学习与参考资料 <a id="learn"></a>

| 资源 | 网址 | 说明 |
| --- | --- | --- |
| ruff 官方文档 | https://docs.astral.sh/ruff/ | 安装、配置、lint/format 用法权威说明 |
| ruff 规则目录 | https://docs.astral.sh/ruff/rules/ | 全部规则代码与说明，配置取舍时查阅 |
| ruff GitHub 仓库 | https://github.com/astral-sh/ruff | 源码、issue 与发布说明 |
| ruff（PyPI） | https://pypi.org/project/ruff/ | pip / uv 安装入口 |
| ruff VS Code 扩展 | https://marketplace.visualstudio.com/items?itemName=charliermarsh.ruff | 编辑器内实时检查与格式化（Pylance 之外装这个即可） |

## 7. 项目内关联文档 <a id="related"></a>

| 文档 | 说明 |
| --- | --- |
| 《[项目规划说明](../../../规划/项目规划说明.md#stack-eng)》2.3 节 | 技术栈：代码规范 = ruff |
| 《[项目规划说明](../../../规划/项目规划说明.md#sel-eng)》3.3 节 | 选型说明：lint + format 一体化、性能极高 |
| 《[项目规划说明](../../../规划/项目规划说明.md#sel-ops)》3.4 节 | CI 流水线：ruff 为后端第一道门禁 |
| 《[uv 技术介绍](uv技术介绍.md)》 | 统一以 `uv run ruff ...` 执行，配置共用 pyproject.toml |
| 《[pyright 技术介绍](pyright技术介绍.md)》 | 类型检查与 ruff 分工：风格 vs 类型 |
| 《[后端开发规范](../../../规范/后端开发规范.md)》 | 编码约定与规范的落地执行工具 |

---

> 依《[文档生成规范](../../../规范/文档生成规范.md)》编写 · 生成日期：2026-08-19