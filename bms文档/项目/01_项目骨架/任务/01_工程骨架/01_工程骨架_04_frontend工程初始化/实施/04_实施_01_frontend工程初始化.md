# frontend 工程初始化实施记录

> 项目骨架 · 01 工程骨架 · 子任务 04 · 实施记录 01

[文档首页](../../../../../../文档首页.md) › [04 frontend 工程初始化](../01_工程骨架_04_frontend工程初始化.md) › 01 实施记录　|　[详细设计 →](../设计/04_详细设计_01_frontend工程初始化.md)

## 1. 实施信息 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 任务 | [04 frontend 工程初始化](../01_工程骨架_04_frontend工程初始化.md) |
| 对应需求 | [01-4](../../../../需求/01_需求_工程骨架.md#r01-4) |
| 详细设计 | [04_详细设计_01_frontend工程初始化](../设计/04_详细设计_01_frontend工程初始化.md) |
| 实施日期 | 2026-09-10 |
| 实施人 | minjian |
| 实施环境 | 开发机（Ubuntu）；Node 22.23.2（nvm）、npm 10.9.8；npm 源 npmmirror |
| 提交 | —（随本批提交，见仓库 git log） |
| 结论 | 占位工程升级为完整初始化；代理链路（含 /info 重写）实测通过；lint/test/build 全绿 |

## 2. 实施概览 <a id="overview"></a>

```mermaid
flowchart LR
    A[依赖安装 npmmirror] --> B[工程配置 vite/tsconfig/eslint/vitest]
    B --> C[src 骨架与契约类型]
    C --> D[默认页与 /info 连通]
    D --> E[门禁 lint/test/build]
    E --> F[代理链路实测与回写]
```

## 3. 实施过程 <a id="process"></a>

### 3.1 依赖与 npm 源

- `.npmrc`：`registry=https://registry.npmmirror.com` + `legacy-peer-deps=true`（原因见问题 1）；
- 运行依赖：vue-router 4.6、pinia 3.0、axios 1.20、element-plus 2.14、@element-plus/icons-vue 2.3、vue-i18n 11.4、socket.io-client 4.8；
- 开发依赖：eslint 10 + eslint-plugin-vue 10 + typescript-eslint 8 + @eslint/js + @vue/eslint-config-prettier + prettier 3、vitest 5 + @vue/test-utils + jsdom + @vitest/coverage-v8、sass、openapi-typescript 7.13、vue-eslint-parser；版本范围写入 package.json，实际版本由 package-lock.json 锁定并提交。

### 3.2 工程配置

- `vite.config.ts`：`@` 别名、端口 5173（strictPort）、代理 `/api` 与 `/healthz` → `http://localhost:8000`、`/info` 重写至 backend `/`、`/docs` 不代理；
- `.env.development`（`VITE_API_BASE=/api`）；tsconfig 用 `paths` 映射 `@/*`（移除 TS6 已弃用的 baseUrl）；
- `eslint.config.js`（flat：js + typescript-eslint + eslint-plugin-vue flat/recommended + Prettier skip-formatting）、`.prettierrc.json`；`vitest.config.ts`（jsdom + v8 覆盖率）。

### 3.3 src 骨架与契约

- `api/types.ts`（`ApiResponse<T>` / `PageResponse<T>`）、`api/http.ts`（Axios 实例 + 拦截器 + `request<T>()` + `fetchAppInfo()`）、`api/types.gen.ts`（生成占位）；
- `router/routes.ts`（动态路由骨架）、`stores/useUserStore.ts`（token 仅内存）、`layouts/BasicLayout.vue`、`views/HomeView.vue`（标题 + backend 应用名/版本）、`i18n/*`（含 `error.{code}` 占位）、`components`/`utils` 占位；
- `main.ts` 接线 router/pinia/i18n/Element Plus；`index.html` 标题改为「BMS 基础管理系统」。

### 3.4 验证与提交

`npm ci` → `lint` → `test`（Vitest 2 条）→ `build`（vue-tsc -b + vite build）；起 backend + dev 后用 curl 实测代理链路；随后形成本批提交（等用户指令）。

## 4. 问题与处置 <a id="issues"></a>

| # | 问题 / 现象 | 原因 | 处置 | 落点 |
| --- | --- | --- | --- | --- |
| 1 | `npm install` ERESOLVE：openapi-typescript@7 声明 peer `typescript ^5` | 项目为 TypeScript 6（create-vue 新基线） | `.npmrc` 设 `legacy-peer-deps=true`（附注释，待其支持 TS6 后移除）；`npm ci` 可复现 | `.npmrc` |
| 2 | ESLint 报找不到 `vue-eslint-parser` | legacy-peer-deps 模式不自动安装 peer | 两工程显式 `npm install -D vue-eslint-parser` | `package.json` |
| 3 | `vue-tsc -b` 报 TS5101：`baseUrl` 弃用（TS7 将移除） | TypeScript 6 弃用口径 | 移除 `baseUrl`，仅保留 `paths`（相对 tsconfig 解析） | `tsconfig.app.json` |
| 4 | 构建告警：单 chunk > 500 kB（Element Plus 全量引入） | 骨架期全量注册 Element Plus | 接受并登记；按需引入（unplugin）作为后续优化项 | 本记录 §6 |

## 5. 验证结果 <a id="verify"></a>

| 验证点（完成标准） | 方法 | 结果 |
| --- | --- | --- |
| `npm ci` 可复现 | 命令 | 通过（npmmirror，锁文件生效） |
| 代理与响应解析链路 | 起 backend + `npm run dev` 后 curl | 通过（见下） |
| `npm run lint` | 命令 | 通过（--max-warnings 0） |
| `npm run test` | 命令 | 通过（2 passed，Kiwi 19） |
| `npm run build` / `vue-tsc` | 命令 | 通过 |
| 覆盖率 | `npm run test:cov` | 100%（已导入文件） |
| Node 版本 | `node -v` | v22.23.2（≥ 22） |

代理实测摘要：页面标题 `BMS 基础管理系统`；`/info` → `{"code":0,…,"data":{"name":"BMS 基础管理系统","version":"0.1.0"}}`（重写至 backend 根）；`/api/v1/demos` → 业务空列表（/api 代理）；`/healthz` → `{"status":"ok"}`。

## 6. 偏差与遗留 <a id="deviations"></a>

- Element Plus 全量引入构建告警：**已于 2026-09-10 优化为按需引入**（unplugin-vue-components + ElementPlusResolver；主包 1,064.53 kB → 147.34 kB，gzip 342.74 → 53.67 kB，告警消除）。
- `openapi-typescript` peer 声明滞后（^5 vs 项目 TS 6）：**已评估**——该包运行时不依赖 TypeScript，`npm run gen:api` 在 TS6 下实测可用（对本地 OpenAPI 生成 396 行，42ms）；维持 `legacy-peer-deps` 并注明，待上游支持后移除。
- 页面渲染断言当前由 Vitest mock 覆盖；真实浏览器链路（含视觉/视口）随 05-1 Playwright E2E。
- 401 刷新、token 持久化、动态路由注入留阶段四（代码内 TODO 标注）。

> 本文档依《文档生成规范》编写 · 按《任务文档规范》「实施文档（任务执行记录）」节实施文档结构组织
