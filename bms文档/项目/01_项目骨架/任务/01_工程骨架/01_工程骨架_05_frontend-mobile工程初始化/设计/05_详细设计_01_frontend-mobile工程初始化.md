# frontend-mobile 工程初始化详细设计

> 项目骨架 · 01 工程骨架 · 子任务 05 · 详细设计

[文档首页](../../../../../../文档首页.md) › [05 frontend-mobile 工程初始化](../01_工程骨架_05_frontend-mobile工程初始化.md) › 01 详细设计　|　[← 任务文档](../01_工程骨架_05_frontend-mobile工程初始化.md)　[父任务](../../01_工程骨架.md)

## 1. 概述 <a id="overview"></a>

- **目标**：把 01-01 交付的 frontend-mobile 最小占位（Vue 3.5 + Vite 8 + TS 6）升级为**需求 01-5 定义的完整工程**：Vant 移动端依赖、src 分层骨架、统一响应契约（复用同款 Axios 基线）、移动端视口适配与安全区基线、ESLint/Prettier/Vitest 与冒烟测试。
- **范围**：仅 frontend-mobile 工程与其冒烟验证；业务页面与移动端 UI 细节不做（默认页占位，随阶段十四细化）；认证与免登（企业微信/钉钉）随对应阶段。
- **依据**：需求 [01-5](../../../../需求/01_需求_工程骨架.md#r01-5)、《[前端开发规范](../../../../../../规范/前端开发规范.md)》第 2/9 节、《[项目规划说明](../../../../../../规划/项目规划说明.md)》「前端」「项目目录结构」节、《[命名规范](../../../../../../规范/命名规范.md)》「前端命名」节；共享契约与拦截器设计见 [04 详细设计](../../01_工程骨架_04_frontend工程初始化/设计/04_详细设计_01_frontend工程初始化.md)。

## 2. 现状与差距 <a id="gap"></a>

| 现状（01-01 占位） | 差距（需求 01-5） |
| --- | --- |
| `vue ^3.5.41` + `vite ^8.2.2` + `typescript ~6.0.2` + `vue-tsc`，dev 端口 5174 | 缺 Vant、Vue Router 4、Pinia、Axios、vue-i18n、视口适配插件 |
| `src/` 仅 `App.vue` + `main.ts`（默认页） | 缺 api / router / stores / views / components / i18n / utils 分层 |
| 无代理与环境变量 | 缺 `/api` → backend、`/docs` 不代理、`.env.development`（`VITE_API_BASE=/api`） |
| 无 lint / 测试 | 缺 ESLint + Prettier、Vitest + @vue/test-utils |
| 无视口适配 | 缺 postcss rem/px 适配基线 + 安全区 `env(safe-area-inset-*)` 变量占位 |
| 无 npm 源约定 | 缺 `.npmrc`（npmmirror）与锁文件提交约定（锁文件已存在） |

## 3. 目标目录与交付物清单 <a id="tree"></a>

```text
frontend-mobile/
├── .npmrc                          # 新增：npmmirror 国内源
├── .nvmrc                          # 已有：22
├── .env.development                # 新增：VITE_API_BASE=/api
├── package.json                    # 修改：依赖 + scripts（lint/format/test）
├── package-lock.json               # 提交（npm ci 可复现）
├── vite.config.ts                  # 修改：@ 别名 + 代理 + Vant 按需 + 端口 5174
├── postcss.config.js               # 新增：px→vw 适配（设计稿 375，保留 1px）
├── eslint.config.js                # 新增：flat config（vue + ts + prettier）
├── .prettierrc.json                # 新增：Prettier 配置
├── vitest.config.ts                # 新增：Vitest（jsdom 环境）
├── index.html                      # 修改：标题「BMS 基础管理系统」+ viewport meta
├── src/
│   ├── main.ts                     # 修改：挂载 router / pinia / i18n / Vant
│   ├── App.vue                     # 修改：router-view 出口
│   ├── api/
│   │   ├── types.ts                # 新增：ApiResponse<T> / PageResponse<T>（与 04 同款）
│   │   ├── http.ts                 # 新增：Axios 实例 + 拦截器 + fetchAppInfo()
│   │   └── types.gen.ts            # 新增：openapi-typescript 生成占位（随 05 域替换）
│   ├── router/routes.ts            # 新增：路由骨架（不硬编码业务路由表）
│   ├── stores/useUserStore.ts      # 新增：Pinia 占位（token 仅内存）
│   ├── views/HomeView.vue          # 新增：默认页（标题 + backend 连通状态）
│   ├── components/README.md        # 新增：组件目录占位说明
│   ├── i18n/index.ts               # 新增：vue-i18n 实例
│   ├── i18n/zh-CN.ts               # 新增：中文语言包（含 error.{code} 段）
│   ├── i18n/en-US.ts               # 新增：英文语言包
│   ├── styles/safe-area.scss       # 新增：安全区 CSS 变量占位
│   └── utils/README.md             # 新增：工具目录占位说明
└── tests/
    └── home.spec.ts                # 新增：默认页冒烟（Kiwi 20）
```

## 4. package.json 设计 <a id="package"></a>

**运行依赖**（主版本范围 + `package-lock.json` 锁定）：`vue`（已有 `^3.5.41`）、`vue-router ^4`、`pinia ^3`、`axios ^1`、`vant ^4`、`vue-i18n ^11`。

**开发依赖**：`vite`/`typescript`/`vue-tsc`/`@vitejs/plugin-vue`（已有）、`sass`、`unplugin-vue-components` + `@vant/auto-import-resolver`（Vant 按需引入）、`postcss-px-to-viewport-8-plugin`、`eslint` + `eslint-plugin-vue` + `typescript-eslint` + `@vue/eslint-config-typescript` + `@vue/eslint-config-prettier`、`prettier`、`vitest` + `@vue/test-utils` + `jsdom`、`openapi-typescript`（契约生成占位）。

**scripts** 与 04 同款：`dev / build / preview / lint / lint:fix / format / test / test:cov`（另预留 `gen:api`）。

## 5. 工程配置设计 <a id="config"></a>

`vite.config.ts`（在现占位基础上扩展）：

```ts
import { fileURLToPath, URL } from 'node:url'
import vue from '@vitejs/plugin-vue'
import Components from 'unplugin-vue-components/vite'
import { VantResolver } from '@vant/auto-import-resolver'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [vue(), Components({ resolvers: [VantResolver()] })],
  resolve: { alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) } },
  server: {
    port: 5174,
    strictPort: true,
    proxy: {
      '/api': { target: 'http://localhost:8000', changeOrigin: true },
      '/healthz': { target: 'http://localhost:8000', changeOrigin: true },
      '/info': { target: 'http://localhost:8000', changeOrigin: true, rewrite: () => '/' },
    },
  },
})
```

- **代理口径**与 04 一致：`/api`（业务契约）、`/healthz`（探针）、`/info`（重写至 backend `/`，连通验证）；`/docs` 不代理。
- **视口适配**（`postcss.config.js`）：`postcss-px-to-viewport-8-plugin`——设计稿宽 375、`viewportWidth: 375`、`unitPrecision: 5`、保留 1px 边框（`minPixelValue: 2`）、忽略注释 `/* px-to-viewport-ignore */`；后续如需 rem 方案可切 `postcss-pxtorem` + flexible（配置层切换，不改业务样式）。
- **安全区**（`src/styles/safe-area.scss`）：`--safe-top/right/bottom/left` 变量映射 `env(safe-area-inset-*)` 占位，全局引入。
- `.env.development`：`VITE_API_BASE=/api`；`.npmrc`：npmmirror；tsconfig 补 `@/*` paths；ESLint/Prettier/Vitest 同 04 口径。

## 6. src 骨架设计 <a id="src"></a>

| 文件 | 职责 | 禁止 |
| --- | --- | --- |
| `api/types.ts` | 统一响应与分页契约类型（与 04 保持同源） | 不写业务 API |
| `api/http.ts` | Axios 实例、拦截器（token 注入位、统一响应解析、401 TODO）、`fetchAppInfo()` | 不写页面逻辑 |
| `router/routes.ts` | 路由实例与壳路由；动态路由骨架（阶段三按权限注入） | 不硬编码业务路由表 |
| `stores/useUserStore.ts` | 用户/token 占位（token 仅内存） | 不持久化 token |
| `views/HomeView.vue` | 默认页：标题 + backend 连通状态（连通显示应用名/版本，失败显示降级文案） | 不放业务逻辑 |
| `i18n/*` | vue-i18n 实例与 zh-CN/en-US 语言包（含 `error.{code}` 段） | 不硬编码文案 |
| `styles/safe-area.scss` | 安全区变量占位 | 不放组件样式 |

统一响应契约与拦截器行为、`fetchAppInfo()` 设计与 04 完全一致（见 [04 详细设计 §7](../../01_工程骨架_04_frontend工程初始化/设计/04_详细设计_01_frontend工程初始化.md)）；移动端默认页在请求失败时仍渲染标题并展示「backend 未连通」状态（避免骨架期演示依赖后端先行）。

## 7. 测试设计（Kiwi 先行） <a id="tests"></a>

| Kiwi | 用例 | 自动化 |
| --- | --- | --- |
| 20 | frontend-mobile 默认页与连通冒烟（标题、backend 连通状态成功/降级两种渲染） | `tests/home.spec.ts`（Vitest + @vue/test-utils，mock `fetchAppInfo`） |

- 质量门禁：`npm run lint`、`vue-tsc -b`、`npm run test`、`npm run build` 全通过；frontend-mobile/ 落地后 main 冒烟层前端 job（05-1 exists 激活，双构建含 mobile）全绿。
- 视口（375×667）布局正常为手工/阶段验收核对项（自动化视口断言随 Playwright E2E，05-1 重验证层）。

## 8. 实施步骤 <a id="steps"></a>

1. Kiwi Case 20 登记（已登记）。
2. `.npmrc` + `package.json` 依赖/scripts（npmmirror 安装，提交 `package-lock.json`）。
3. 工程配置：vite（代理/别名/Vant 按需）、postcss 适配、`.env.development`、tsconfig paths、ESLint/Prettier、Vitest。
4. src 骨架：types/http/router/store/view/i18n/safe-area/utils 与 `main.ts`/`App.vue` 接线。
5. 默认页与 `/info` 连通验证（人工起 backend 复核；失败降级渲染）。
6. 冒烟用例与门禁命令跑通。
7. 验证：`npm ci` / `npm run dev`（375×667 视口）/ `build` / `vue-tsc` / `lint` / `test`。
8. 回写实施/测试记录、任务与计划状态、README。

## 9. 验收映射 <a id="accept-map"></a>

| 完成标准 | 验证方式 |
| --- | --- |
| 代理与响应解析链路通 | 起 backend + `npm run dev`，默认页展示 backend 连通状态；`curl /info` 代理返回 |
| 依赖与工程结构齐备 | 目录树对照需求 01-5 第 1/2/3 条 |
| 视口适配与安全区基线 | 375×667 视口默认页布局正常；`env(safe-area-inset-*)` 变量生效（模拟器） |
| 质量门禁 | `npm ci`、`build`、`vue-tsc`、`lint`、`test` 全通过 |
| Kiwi 用例登记并标注 | 平台 Case 20 + 用例关联 |

## 10. 边界与开放项 <a id="boundary"></a>

- 不含移动端业务页面与交互细节（默认页占位；随阶段十四细化）。
- 视口方案默认 vw（postcss-px-to-viewport），如遇第三方组件兼容问题可切 rem 方案（配置层切换）。
- 企业微信/钉钉免登、401 刷新与 token 口径随阶段三。
- OpenAPI 类型生成为占位，随 05 域契约接入启用。

## 11. 对齐记录 <a id="align"></a>

| # | 事项 | 结论 |
| --- | --- | --- |
| 1 | 版本口径 | 主版本范围 + `package-lock.json` 锁定实际版本 |
| 2 | 连通探针 | `/info` 代理重写至 backend `/`（与 04 同口径） |
| 3 | Kiwi | Case 20 一条冒烟（含连通成功/降级两种状态） |
| 4 | 视口方案 | postcss px→vw（设计稿 375、保留 1px）+ 安全区 CSS 变量；rem 方案可切换 |
| 5 | CI | frontend-mobile/ 落地激活 05-1 前端 job（ESLint/Vitest/双构建） |

> 本文档依《文档生成规范》编写 · 关键决策逐项确认
