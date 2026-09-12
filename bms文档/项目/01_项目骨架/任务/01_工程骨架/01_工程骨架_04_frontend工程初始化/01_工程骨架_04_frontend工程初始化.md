# 04 frontend 工程初始化

> 项目骨架 · 01 工程骨架 · 子任务 04

[文档首页](../../../../../文档首页.md) › [01 工程骨架](../01_工程骨架.md) › 04 frontend 工程初始化　|　[← 父任务](../01_工程骨架.md)

## 1. 任务信息 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 编号 | 04 |
| 父任务 | [01 工程骨架](../01_工程骨架.md) |
| 对应需求 | [01-4](../../../需求/01_需求_工程骨架.md#r01-4) |
| 工时（重估） | 15h（重估：自有 3h + 嵌套子任务「前端基础类」6h、「前端公共组合式与工具基座」6h） |
| 依赖 | 01（monorepo 骨架）、02（backend 可启动，代理连通验证依赖） |
| 负责人 | minjian |
| 状态 | 已完成 |
| 完成日期 | 2026-09-10 |

## 2. 子任务清单 <a id="list"></a>

| 编号 | 任务 | 工时（重估） | 状态 | 完成日期 | 任务文件 |
| --- | --- | --- | --- | --- | --- |
| 01 | 前端基础类 | 6h | 已完成 | 2026-09-10 | [01](01_工程骨架_04_frontend工程初始化_01_前端基础类/01_工程骨架_04_frontend工程初始化_01_前端基础类.md) |
| 02 | 前端公共组合式与工具基座 | 6h | 已完成 | 2026-09-10 | [02](01_工程骨架_04_frontend工程初始化_02_前端公共组合式与工具基座/01_工程骨架_04_frontend工程初始化_02_前端公共组合式与工具基座.md) |

父任务工时 = 自有 3h + 直属子任务 12h = 15h；子任务状态/完成日期随其实施进度回写本表。

## 3. 任务内容 <a id="content"></a>

1. 技术基线：Vue 3 + Vite + TypeScript（strict）、Element Plus、SCSS、npm 管理；`.npmrc` 配 npmmirror 国内源，`package-lock.json` 提交仓库
2. `package.json` 依赖清单：vue、vue-router@4、pinia、axios、element-plus、vue-i18n、socket.io-client；dev：vite、typescript、vue-tsc、eslint + eslint-plugin-vue、prettier、vitest、@vue/test-utils、openapi-typescript；`.nvmrc` 固定 22
3. `src/` 目录：api（http.ts Axios 实例 + types.ts 占位 + 模块.ts）、router（动态路由骨架）、stores（useUserStore 等占位）、views（默认首页）、layouts（基础壳）、components、i18n（index + zh-CN/en-US，预留错误码映射段 `error.{code}`，与后端统一响应 message 口径一致）、utils
4. 工程配置：vite.config.ts（@ 别名、代理 `/api` → `http://localhost:8000`、`/docs` 不代理）；`.env.development`（`VITE_API_BASE=/api`）；ESLint + Prettier；`ApiResponse<T>`/`PageResponse<T>` 手写基类（openapi-typescript 生成类型随 05 域契约接入替换）
5. Axios 基线：请求拦截器预留 Bearer token 位（仅存内存）、响应拦截器统一处理 `{code, message, data}`；401/会话失效 TODO 占位（阶段四接入）

## 4. 完成标准 <a id="accept"></a>

`npm ci` 通过；`npm run dev` 默认页（标题「BMS 基础管理系统」）显示 backend `/` 返回的 name/version（代理与响应解析链路通）；`npm run build`、`vue-tsc`、ESLint、`vitest run`（1 条冒烟用例）全通过；`node -v` ≥ 22；frontend/ 落地后 main 冒烟层前端 job（exists 激活，见 05-1）全绿。

## 5. 参考文档 <a id="ref"></a>

- [04_详细设计_01_frontend工程初始化](设计/04_详细设计_01_frontend工程初始化.md)（本任务详细设计，已定稿）
- [04_实施_01_frontend工程初始化](实施/04_实施_01_frontend工程初始化.md)（实做内容、问题与处置、验证与遗留）
- [04_测试_01_frontend工程初始化](测试/04_测试_01_frontend工程初始化.md)（用例、执行结果、问题与覆盖率）
- [需求 01-4](../../../需求/01_需求_工程骨架.md#r01-4)（本任务对应需求）
- 《[项目规划说明](../../../../../规划/项目规划说明.md)》「前端」「环境与配置」节
- 《[前端开发规范](../../../../../规范/前端开发规范.md)》第 2/4/11 节
- 《[命名规范](../../../../../规范/命名规范.md)》「前端命名」节
- [05-1 CI 流水线激活](../../04_CI与阶段验收/04_CI与阶段验收_01_CI流水线激活/04_CI与阶段验收_01_CI流水线激活.md)（前端 job exists 激活联动）

> 本文档依《文档生成规范》编写
