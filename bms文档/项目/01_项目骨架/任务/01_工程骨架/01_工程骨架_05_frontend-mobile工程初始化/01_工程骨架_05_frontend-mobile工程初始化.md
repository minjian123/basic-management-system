# 05 frontend-mobile 工程初始化

> 项目骨架 · 01 工程骨架 · 子任务 05

[文档首页](../../../../../文档首页.md) › [01 工程骨架](../01_工程骨架.md) › 05 frontend-mobile 工程初始化　|　[← 父任务](../01_工程骨架.md)

## 1. 任务信息 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 编号 | 05 |
| 父任务 | [01 工程骨架](../01_工程骨架.md) |
| 对应需求 | [01-5](../../../需求/01_需求_工程骨架.md#r01-5) |
| 工时（重估） | 2h |
| 依赖 | 01（monorepo 骨架）、02（backend 可启动，连通状态验证依赖） |
| 负责人 | minjian |
| 状态 | 未开始 |
| 完成日期 | — |

## 2. 任务内容 <a id="content"></a>

1. 技术基线：Vue 3 + Vite + TypeScript + Vant（移动端 H5）；双工程独立——与 frontend 各自 package.json / lock 与 ESLint/Prettier/TS 配置，互不共享；`.nvmrc` 固定 22；`.npmrc` 配 npmmirror 国内源，`package-lock.json` 提交仓库
2. `src/` 目录：api（复用同款 Axios 基线封装：统一响应 `{code, message, data}` 解析与 401 TODO 占位）、router、stores、views（默认首页）、components、i18n（预留错误码映射段 `error.{code}`）、utils
3. 工程配置：vite.config.ts（代理 `/api` → backend、`/docs` 不代理）；`.env.development`（`VITE_API_BASE=/api`）；postcss rem/px 视口适配基线 + 安全区 `env(safe-area-inset-*)` 变量占位
4. 默认页展示 backend 连通状态（同 04 验收方式）

## 3. 完成标准 <a id="accept"></a>

`npm ci`、`npm run dev`、`npm run build`、ESLint、`vitest run` 全通过；移动端视口（375×667）默认页布局正常，标题「BMS 基础管理系统」并显示 backend 连通状态；frontend-mobile/ 落地后 main 冒烟层前端 job（exists 激活，见 05-1）全绿。

## 4. 参考文档 <a id="ref"></a>

- [05_详细设计_01_frontend-mobile工程初始化](设计/05_详细设计_01_frontend-mobile工程初始化.md)（本任务详细设计，已定稿）
- [需求 01-5](../../../需求/01_需求_工程骨架.md#r01-5)（本任务对应需求）
- 《[项目规划说明](../../../../../规划/项目规划说明.md)》2.2/4
- 《[前端开发规范](../../../../../规范/前端开发规范.md)》第 2/8 节
- 《[命名规范](../../../../../规范/命名规范.md)》第 9 节
- [05-1 CI 流水线激活](../../05_CI与阶段验收/05_CI与阶段验收_01_CI流水线激活/05_CI与阶段验收_01_CI流水线激活.md)（前端 job exists 激活联动）

> 本文档依《文档生成规范》编写
