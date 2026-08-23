# 01-5 frontend-mobile 工程初始化

> 项目骨架 · 01 工程骨架 · 子任务 01-5

[文档首页](../../../../文档首页.md) › [01 工程骨架](../01_工程骨架.md) › 01-5 frontend-mobile 工程初始化　|　[← 父任务](../01_工程骨架.md)

## 1. 任务信息 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 编号 | 01-5 |
| 父任务 | [01 工程骨架](../01_工程骨架.md) |
| 对应需求 | [01-5](../../需求/01_需求_工程骨架.md#r01-5) |
| 禅道任务 | — |
| 工时（重估） | 2h |
| 依赖 | 01-1（monorepo 骨架） |
| 负责人 | minjian |
| 状态 | 未开始 |
| 完成日期 | — |

## 2. 任务内容 <a id="content"></a>

1. 技术基线：Vue 3 + Vite + TypeScript + Vant（移动端 H5）；双工程独立——与 frontend 各自 package.json / lock 与 ESLint/Prettier/TS 配置，互不共享；`.nvmrc` 固定 20.19
2. `src/` 目录：api（复用同款 Axios 基线封装）、router、stores、views（默认首页）、components、i18n、utils
3. 工程配置：vite.config.ts（代理 `/api` → backend）；postcss rem/px 视口适配基线 + 安全区 `env(safe-area-inset-*)` 变量占位
4. 默认页展示 backend 连通状态（同 01-4 验收方式）

## 3. 完成标准 <a id="accept"></a>

`npm ci`、`npm run dev`、`npm run build`、ESLint、`vitest run` 全通过；移动端视口（375×667）默认页布局正常。

## 4. 参考文档 <a id="ref"></a>

- 《项目规划说明》2.2/4
- 《前端开发规范》第 2/8 节
- 《命名规范》第 9 节

> 本文档依《文档生成规范》编写 · 生成日期：2026-08-23
