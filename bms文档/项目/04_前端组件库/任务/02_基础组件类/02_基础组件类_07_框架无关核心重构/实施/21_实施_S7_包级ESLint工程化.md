# 框架无关核心重构 · S7 实施记录（包级 ESLint 工程化）

> 前端组件库 · 02 基础组件类 · 02-7 框架无关核心重构 · 收尾批次（S7）实施记录

[文档首页](../../../../../../文档首页.md) › [02-7 框架无关核心重构](../02_基础组件类_07_框架无关核心重构.md) › 01 实施　|　[← 任务文档](../02_基础组件类_07_框架无关核心重构.md)

## 1. 实施信息 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 阶段 | `02_07` 收尾批次 **S7 包级 ESLint 工程化**（2026-09-17 追加） |
| 实施日期 | 2026-09-17 |
| 实施人 | minjian |
| 环境 | Linux 开发机（mjpc）；Node v24.20.0；npm workspaces（core / vue / ui-ep / ui-vant） |
| 实测工时 | ≈1h |
| 结论 | 完成：四包各自 `eslint.config.js` + `lint` 脚本，根 `lint` / `check` 串联；CI `core-check` 自动覆盖；四包零告警 |

## 2. 交付物 <a id="deliverables"></a>

| 块 | 内容 |
| --- | --- |
| 根依赖 | `package.json` `devDependencies` 统一装：`@eslint/js` / `eslint` / `eslint-plugin-vue` / `vue-eslint-parser` / `typescript-eslint` / `@vue/eslint-config-prettier` / `prettier`（与 `apps/*` 同版本口径）；根锁文件更新 |
| 各包配置 | `packages/{core,vue,ui-ep,ui-vant}/eslint.config.js`：core 为 TS 规则集；三 Vue 包叠加 `eslint-plugin-vue`（flat/recommended）+ TS parser 于 SFC + `skip-formatting`（格式化规则交 Prettier，不在 ESLint 重复）；忽略 `node_modules` / `coverage` |
| 脚本 | 各包 `"lint": "eslint . --max-warnings 0"`；根 `lint`（四包聚合）与各包 `check`（typecheck + lint + test）串联；CI `core-check` 经 `npm run check` 自动覆盖 |
| 修复 | `packages/core/tests/guard-core-framework-agnostic.spec.ts`：护栏正则字符类内多余转义 `[\/]` → `[/]`（`no-useless-escape`） |
| 规范 | 《前端开发规范》§2「工程约定」新增「包级门禁（S7 工程化批次）」条 |

## 3. 验证结果 <a id="verify"></a>

| 命令 | 结果 |
| --- | --- |
| `npm run lint`（四包） | 全部通过（`eslint . --max-warnings 0`，零告警） |
| `npm run check` | core 11 / 65 + vue 4 / 13 + ui-ep 13 / 82 + ui-vant 16 / 82 全绿（含 lint 门禁） |

## 4. 问题与处置 <a id="issues"></a>

| # | 问题 | 处置 |
| --- | --- | --- |
| 1 | 包配置首跑产生 193 条告警（0 error），多为 `vue/max-attributes-per-line` / `vue/singleline-html-element-content-newline` 等格式化类规则 | 与 `apps/*` 同口径引入 `@vue/eslint-config-prettier/skip-formatting`（格式化交 Prettier）；重跑零告警 |
| 2 | core 护栏用例正则字符类 `[\/]` 触发 `no-useless-escape`（错误级） | 改 `[/]`（语义等价） |

## 5. 偏差与遗留 <a id="deviation"></a>

| # | 项 | 归口 / 去向 |
| --- | --- | --- |
| 1 | 包级 Prettier 脚本（`format`）未配（ESLint 已让位） | 如需统一格式化命令，随工程化需要再补（apps 已有 `format`） |
| 2 | 镜像随根锁变更重建 | 推送后 `ci-base-build` 自动重建（预期耗时增加），CI 跟盯 |

> 本文档依《[文档生成规范](../../../../../../规范/文档生成规范.md)》编写
