# 01-4 frontend 工程初始化

> 项目骨架 · 01 工程骨架 · 子任务 01-4

[文档首页](../../../../文档首页.md) › [01 工程骨架](../01_工程骨架.md) › 01-4 frontend 工程初始化　|　[← 父任务](../01_工程骨架.md)

## 1. 任务信息 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 编号 | 01-4 |
| 父任务 | [01 工程骨架](../01_工程骨架.md) |
| 对应需求 | [01-4](../../需求/01_需求_工程骨架.md#r01-4) |
| 工时（重估） | 3h |
| 依赖 | 01-1（monorepo 骨架） |
| 负责人 | minjian |
| 状态 | 未开始 |
| 完成日期 | — |

## 2. 任务内容 <a id="content"></a>

1. 技术基线：Vue 3 + Vite + TypeScript（strict）、Element Plus、SCSS、npm 管理
2. `package.json` 依赖清单：vue、vue-router@4、pinia、axios、element-plus、vue-i18n、socket.io-client；dev：vite、typescript、vue-tsc、eslint + eslint-plugin-vue、prettier、vitest、@vue/test-utils、openapi-typescript；`.nvmrc` 固定 20.19
3. `src/` 目录：api（http.ts Axios 实例 + types.ts 占位 + 模块.ts）、router（动态路由骨架）、stores（useUserStore 等占位）、views（默认首页）、layouts（基础壳）、components、i18n（index + zh-CN/en-US）、utils
4. 工程配置：vite.config.ts（@ 别名、代理 `/api` → `http://localhost:8000`）；`.env.development`；ESLint + Prettier；`ApiResponse<T>`/`PageResponse<T>` 手写基类
5. Axios 基线：请求拦截器预留 Bearer token 位（仅存内存）、响应拦截器统一处理 `{code, message, data}`；401/会话失效 TODO 占位（阶段二接入）

## 3. 完成标准 <a id="accept"></a>

`npm ci` 通过；`npm run dev` 默认页显示 backend `/` 返回的 name/version（代理与响应解析链路通）；`npm run build`、`vue-tsc`、ESLint、`vitest run`（1 条冒烟用例）全通过；`node -v` ≥ 20.19。

## 4. 参考文档 <a id="ref"></a>

- 《项目规划说明》2.2/17
- 《前端开发规范》第 2/3/10 节
- 《命名规范》第 9 节

> 本文档依《文档生成规范》编写 · 生成日期：2026-08-23
