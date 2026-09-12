# frontend 工程初始化详细设计

> 项目骨架 · 01 工程骨架 · 子任务 04 · 详细设计

[文档首页](../../../../../../文档首页.md) › [04 frontend 工程初始化](../01_工程骨架_04_frontend工程初始化.md) › 01 详细设计　|　[← 任务文档](../01_工程骨架_04_frontend工程初始化.md)　[父任务](../../01_工程骨架.md)

## 1. 概述 <a id="overview"></a>

- **目标**：把 01-01 交付的 frontend 最小占位（Vue 3.5 + Vite 8 + TS 6）升级为**需求 01-4 定义的完整工程**：依赖清单、src 分层骨架、统一响应契约类型、Vite 代理链路、ESLint/Prettier/Vitest 质量工具与冒烟测试。
- **范围**：仅 frontend 工程与其冒烟验证；业务页面/UI 布局不做（默认页占位）；OpenAPI 类型生成为占位（随 05 域契约接入）；认证与 401 处理留 TODO（阶段二）。
- **依据**：需求 [01-4](../../../../需求/01_需求_工程骨架.md#r01-4)、《[前端开发规范](../../../../../../规范/前端开发规范.md)》第 2/4/11 节、《[项目规划说明](../../../../../../规划/项目规划说明.md)》「前端」「环境与配置」节、《[命名规范](../../../../../../规范/命名规范.md)》「前端命名」节。

## 2. 现状与差距 <a id="gap"></a>

| 现状（01-01 占位） | 差距（需求 01-4） |
| --- | --- |
| `vue ^3.5.41` + `vite ^8.2.2` + `typescript ~6.0.2` + `vue-tsc`，dev 端口 5173 | 缺 Element Plus、Vue Router 4、Pinia、Axios、vue-i18n、SCSS 与 socket.io-client（预留） |
| `src/` 仅 `App.vue` + `main.ts`（默认页） | 缺 api / router / stores / views / layouts / components / i18n / utils 分层 |
| 无代理与环境变量 | 缺 `/api` → `http://localhost:8000`、`/docs` 不代理、`.env.development`（`VITE_API_BASE=/api`） |
| 无 lint / 测试 / 契约类型 | 缺 ESLint + Prettier、Vitest + @vue/test-utils、openapi-typescript、`ApiResponse<T>`/`PageResponse<T>` 手写基类 |
| 无 npm 源与锁文件约定 | 缺 `.npmrc`（npmmirror）与 `package-lock.json` 提交约定（锁文件已存在） |

## 3. 目标目录与交付物清单 <a id="tree"></a>

```text
frontend/
├── .npmrc                      # 新增：npmmirror 国内源
├── .nvmrc                      # 已有：22
├── .env.development            # 新增：VITE_API_BASE=/api
├── package.json                # 修改：依赖 + scripts（lint/format/test）
├── package-lock.json           # 提交（npm ci 可复现）
├── vite.config.ts              # 修改：@ 别名 + 代理 + 端口 5173
├── eslint.config.js            # 新增：flat config（vue + ts + prettier）
├── .prettierrc.json            # 新增：Prettier 配置
├── vitest.config.ts            # 新增：Vitest（jsdom 环境）
├── index.html                  # 修改：标题「BMS 基础管理系统」
├── src/
│   ├── main.ts                 # 修改：挂载 router / pinia / i18n（Element Plus 组件按需自动引入）
│   ├── App.vue                 # 修改：router-view 出口
│   ├── api/
│   │   ├── types.ts            # 新增：ApiResponse<T> / PageResponse<T> 契约类型
│   │   ├── http.ts             # 新增：Axios 实例 + 拦截器 + fetchAppInfo()
│   │   └── types.gen.ts        # 新增：openapi-typescript 生成占位（随 05 域替换）
│   ├── router/routes.ts        # 新增：动态路由骨架（不硬编码业务路由表）
│   ├── stores/useUserStore.ts  # 新增：Pinia 占位（token 仅内存）
│   ├── layouts/BasicLayout.vue # 新增：基础布局壳（router-view）
│   ├── views/HomeView.vue      # 新增：默认页（标题 + backend name/version）
│   ├── components/README.md    # 新增：组件目录占位说明
│   ├── i18n/index.ts           # 新增：vue-i18n 实例
│   ├── i18n/zh-CN.ts           # 新增：中文语言包（app 标题 + error.{code} 段）
│   ├── i18n/en-US.ts           # 新增：英文语言包
│   └── utils/README.md         # 新增：工具目录占位说明
└── tests/
    └── home.spec.ts            # 新增：默认页冒烟（Kiwi 19）
```

## 4. package.json 设计 <a id="package"></a>

**运行依赖**（版本用主版本范围，实际版本由 `package-lock.json` 锁定）：

| 依赖 | 范围 | 用途 |
| --- | --- | --- |
| `vue` | 已有 `^3.5.41` | 框架 |
| `vue-router` | `^4` | 路由（动态菜单骨架） |
| `pinia` | `^3` | 状态管理 |
| `axios` | `^1` | HTTP 客户端 |
| `element-plus` | `^2` | 管理端 UI |
| `@element-plus/icons-vue` | `^2` | 图标 |
| `vue-i18n` | `^11` | 国际化 |
| `socket.io-client` | `^4` | 实时通道预留（阶段二接入） |

**开发依赖**：`vite`/`typescript`/`vue-tsc`（已有）、`@vitejs/plugin-vue`（已有）、`sass`（SCSS）、`eslint` + `eslint-plugin-vue` + `typescript-eslint` + `@vue/eslint-config-typescript` + `@vue/eslint-config-prettier`、`prettier`、`vitest` + `@vue/test-utils` + `jsdom`、`openapi-typescript`。

**scripts**：

```json
{
  "dev": "vite",
  "build": "vue-tsc -b && vite build",
  "preview": "vite preview",
  "lint": "eslint . --max-warnings 0",
  "lint:fix": "eslint . --fix",
  "format": "prettier --write src",
  "test": "vitest run",
  "test:cov": "vitest run --coverage"
}
```

## 5. 工程配置设计 <a id="config"></a>

`vite.config.ts`（在现占位基础上扩展）：

```ts
import { fileURLToPath, URL } from 'node:url'
import vue from '@vitejs/plugin-vue'
import Components from 'unplugin-vue-components/vite'
import { ElementPlusResolver } from 'unplugin-vue-components/resolvers'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [vue(), Components({ resolvers: [ElementPlusResolver()] })],
  resolve: { alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) } },
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      '/api': { target: 'http://localhost:8000', changeOrigin: true },
      '/healthz': { target: 'http://localhost:8000', changeOrigin: true },
      '/info': { target: 'http://localhost:8000', changeOrigin: true, rewrite: () => '/' },
    },
  },
})
```

- **代理口径**：`/api`（业务契约）、`/healthz`（探针）直连 backend；`/info` 重写为 backend `/`（用于默认页展示 name/version 的连通验证，避免与前端根路由冲突）；`/docs` 不代理（后端 Swagger 直连 8000 查看）。
- `.env.development`：`VITE_API_BASE=/api`（`.env.production` 占位 `VITE_API_BASE=/api`，生产由 nginx 同源反代，随部署阶段）。
- `.npmrc`：`registry=https://registry.npmmirror.com`。
- tsconfig：沿用 `@vue/tsconfig` 与 `tsconfig.app.json`，补 `paths` 的 `@/*` 映射（与 Vite alias 一致）。
- ESLint：flat config（`eslint.config.js`），Vue + TS 规则链 + Prettier 兼容层；`--max-warnings 0` 作为 CI 门禁；Prettier 配置（单引号、无分号、宽度 120、Vue 脚本缩进）。
- Vitest：`vitest.config.ts`（`environment: 'jsdom'`，含 Vue 插件）。

## 6. src 骨架设计 <a id="src"></a>

| 文件 | 职责 | 禁止 |
| --- | --- | --- |
| `api/types.ts` | 统一响应与分页契约类型（手写基类） | 不写业务 API |
| `api/http.ts` | Axios 实例、拦截器（token 注入位、统一响应解析、401 TODO）、`fetchAppInfo()` | 不写页面逻辑 |
| `api/types.gen.ts` | openapi-typescript 生成占位（骨架期空导出） | 不手写业务类型 |
| `router/routes.ts` | 路由实例与静态壳路由；动态路由骨架（登录后按权限注入） | 不硬编码业务路由表 |
| `stores/useUserStore.ts` | 用户/token 占位（token 仅内存） | 不持久化 token 到 localStorage（阶段二定案） |
| `layouts/BasicLayout.vue` | 基础布局壳（`router-view`），后续接菜单/页签 | 不放业务组件 |
| `views/HomeView.vue` | 默认页：标题 + backend name/version 展示 | 不放业务逻辑 |
| `i18n/*` | vue-i18n 实例与 zh-CN/en-US 语言包（含 `error.{code}` 段） | 不硬编码文案 |

## 7. 契约类型与统一响应设计 <a id="contract"></a>

```ts
// api/types.ts
export interface ApiResponse<T> {
  code: number
  message: string
  data: T
}

export interface PageResponse<T> {
  list: T[]
  total: number
  page: number
  size: number
}
```

- 响应拦截器：HTTP 2xx 且 `code === 0` → 返回 `data`；`code !== 0` → 统一错误提示（文案按 `error.${code}` i18n 映射，缺失回退 message）并 reject；HTTP 401 → TODO（阶段二接刷新/登出）；网络错误 → 统一提示。
- 请求拦截器：预留 `Authorization: Bearer <token>` 注入位（token 仅存内存 Pinia，阶段二接入）。
- `fetchAppInfo()`：`GET /info` → `ApiResponse<{ name: string; version: string }>`（代理见 §5）。
- 生成类型：`openapi-typescript` 以 backend `/openapi.json` 生成 `types.gen.ts`（脚本 `npm run gen:api` 预留，随 05 域契约接入启用）。

## 8. 测试设计（Kiwi 先行） <a id="tests"></a>

| Kiwi | 用例 | 自动化 |
| --- | --- | --- |
| 19 | frontend 默认页与代理链路冒烟（标题「BMS 基础管理系统」、展示 backend name/version） | `tests/home.spec.ts`（Vitest + @vue/test-utils，mock `fetchAppInfo`） |

- 冒烟范围：HomeView 渲染标题与 mock 的应用名/版本；不依赖真实 backend（代理链路由手工/CI 冒烟复核）。
- 质量门禁：`npm run lint`、`vue-tsc -b`、`npm run test`、`npm run build` 全通过；frontend/ 落地后 main 冒烟层前端 job（05-1 exists 激活）全绿。

## 9. 实施步骤 <a id="steps"></a>

1. Kiwi Case 19 登记（已登记）。
2. `.npmrc` + `package.json` 依赖/scripts（npmmirror 安装，提交 `package-lock.json`）。
3. 工程配置：vite 代理/别名、`.env.development`、tsconfig paths、ESLint/Prettier、Vitest。
4. src 骨架：types/http/router/store/layout/view/i18n/utils 与 `main.ts`/`App.vue` 接线。
5. 默认页与 `/info` 连通验证（人工起 backend 复核 name/version）。
6. 冒烟用例与门禁命令跑通。
7. 验证：`npm ci` / `npm run dev` 连通 / `build` / `vue-tsc` / `lint` / `test`。
8. 回写实施/测试记录、任务与计划状态、README。

## 10. 验收映射 <a id="accept-map"></a>

| 完成标准 | 验证方式 |
| --- | --- |
| 代理与响应解析链路通 | 起 backend + `npm run dev`，默认页显示 name/version；curl `/info` 代理返回 |
| 依赖与工程结构齐备 | 目录树对照需求 01-4 第 2/3/4 条 |
| 契约类型就位 | `ApiResponse`/`PageResponse` 类型与拦截器行为核对 + 冒烟用例 |
| 质量门禁 | `npm ci`、`build`、`vue-tsc`、`lint`、`test` 全通过 |
| Kiwi 用例登记并标注 | 平台 Case 19 + 用例关联 |

## 11. 边界与开放项 <a id="boundary"></a>

- 不含业务页面与 UI 设计（默认页占位）；布局/菜单随阶段二权限体系。
- OpenAPI 类型生成与 `gen:api` 脚本占位，随 05 域契约接入启用（生成后 `types.gen.ts` 替换手写业务类型）。
- 401 刷新与登出、token 持久化口径随阶段二认证任务。
- `/info` 为骨架期连通探针（生产由网关同路径映射或改用正式信息接口，随部署阶段定案）。
- socket.io-client 仅登记依赖占位，不建立连接。

## 12. 对齐记录 <a id="align"></a>

| # | 事项 | 结论 |
| --- | --- | --- |
| 1 | 版本口径 | 主版本范围 + `package-lock.json` 锁定实际版本 |
| 2 | 连通探针 | `/info` 代理重写至 backend `/`（避免与前端根路由冲突） |
| 3 | Kiwi | Case 19 一条冒烟；Vitest + @vue/test-utils |
| 4 | npm 源 | `.npmrc` 配 npmmirror；锁文件提交 |
| 5 | CI | frontend/ 落地激活 05-1 前端 job（ESLint/Vitest/构建） |
| 6 | Element Plus | 按需引入（unplugin-vue-components + ElementPlusResolver）：主包 1,064.53 → 147.34 kB，告警消除（2026-09-10 优化） |
| 7 | openapi-typescript | peer 声明滞后但运行时不依赖 TS，`gen:api` 在 TS6 实测可用；维持 legacy-peer-deps 待上游支持 |

> 本文档依《文档生成规范》编写 · 关键决策逐项确认
