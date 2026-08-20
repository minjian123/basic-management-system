# Vite 技术介绍

> 下一代前端构建工具 · 冷启动快 · BMS 双工程构建基础

[文档首页](../../../文档首页.html) › [知识档案](../技术栈知识档案总览.md) › [前端](../技术栈知识档案总览.md#frontend) › Vite 技术介绍　|　[← 返回总览](../技术栈知识档案总览.md)

---

## 1. 技术概述 <a id="overview"></a>

**Vite**（法语"快"之意）是由尤雨溪发起的新一代前端构建工具，
2020 年发布。它的核心思路是：**开发环境基于浏览器原生 ESM 按需编译**，
冷启动与热更新（HMR）远快于 Webpack；生产构建则基于 Rollup（Rust 版 Rolldown 正在演进）。
截至 2026 年，Vite（6.x 系列）已成为 Vue 官方默认构建工具，并广泛用于 React 等生态。

- **定位**：BMS 前端开发服务器与生产构建工具，frontend 与 frontend-mobile 双工程共用。
- **版本**：6.x 系列（截至 2026 年，跟随 Node LTS 版本演进）。
- **许可**：MIT，OSI 认证开源。
- **运行环境**：Node.js（工程内以 .nvmrc 固定版本）。

## 2. 核心概念与原理 <a id="principles"></a>

| 概念 | 说明 |
| --- | --- |
| 原生 ESM（ES Modules） | 开发时浏览器直接加载 ESM 模块，Vite 只按需转换被请求的文件，无需打包，冷启动秒级 |
| 依赖预构建 | 用 esbuild（Go 编写）把 node_modules 里的 CommonJS 依赖预编译为 ESM 并缓存到 node_modules/.vite，加速加载 |
| HMR 热模块替换 | 修改代码后只替换被改动模块，不刷新页面，组件状态保留，开发体验的关键 |
| 生产构建 | 基于 Rollup 打包：代码分割、资源指纹（hash）、tree-shaking、压缩，输出 dist/ 静态产物 |
| 插件机制 | @vitejs/plugin-vue 编译 .vue 文件，unplugin 系列做自动导入/按需引入，生态丰富 |
| dev server 代理 | server.proxy 把 /api 等前缀请求转发到后端，解决跨域，开发/联调利器 |
| 环境变量 | .env 文件 + import.meta.env（VITE_ 前缀），按 dev/prod 环境区分配置 |
| 路径别名 | resolve.alias 配置 @ 指向 src/，配合 tsconfig paths 双端同步 |
| Vitest 同构 | Vitest 复用 Vite 的配置与插件，测试环境与构建环境一致（见《[Vitest 技术介绍](Vitest技术介绍.md)》） |
| 构建产物分析 | vite build --report 或 rollup-plugin-visualizer 分析包体积，优化首屏 |

## 3. 在 BMS 项目中的用途 <a id="usage"></a>

- **frontend 与 frontend-mobile 双工程各自独立配置**：各自维护 vite.config.ts（代理、别名、构建输出），互不影响（见《[项目规划说明](../../../规划/项目规划说明.html#sel-frontend)》3.2 节）。
- **开发代理**：dev server 把 /api/v1 代理到本地/远程后端，配合 [Axios](Axios技术介绍.md) baseURL 联调（见《[开发部署规划](../../../规划/开发部署规划.html)》前端启动说明）。
- **CI 双端构建**：GitLab CI 流水线执行前端 ESLint + Vitest + 双端构建，产物由 nginx 托管（见《[项目规划说明](../../../规划/项目规划说明.html#sel-ops)》3.4 节）。
- **配合 Vitest 同构**：单元测试零配置复用 Vite 配置，覆盖率统计进 CI 门禁。
- **按需引入 Element Plus**：unplugin-vue-components 插件实现组件按需加载，控制包体积（见《[Element Plus 技术介绍](ElementPlus技术介绍.md)》）。
- **环境区分**：.env.development / .env.production 管理接口地址与构建开关。

最小示例（vite.config.ts 代理片段）：

```ts
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath, URL } from 'node:url'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) }
  },
  server: {
    port: 5173,
    proxy: {
      '/api': { target: 'http://localhost:8000', changeOrigin: true }
    }
  }
})
```

## 4. 选型对比 <a id="compare"></a>

| 工具 | 优缺点 | 结论 |
| --- | --- | --- |
| **Vite（选中）** | 冷启动秒级、HMR 快、配置简单、与 Vue/Vitest 同构 | 官方推荐，开发体验与工程一致性最佳 |
| Webpack 5 | 生态最全、兼容老项目，但配置繁琐、冷启动与 HMR 明显偏慢 | 重且慢，新工程不再推荐 |
| Rollup | 生产打包精细、库构建首选，但开发服务器需自行组装 | 已被 Vite 封装为生产构建底层，不必直接用 |
| esbuild | 极快，但缺少 HMR/插件生态等完整工程能力 | 作为 Vite 的依赖预构建引擎存在 |

## 5. 常见问题与注意事项 <a id="pitfalls"></a>

- **改配置要重启**：修改 vite.config.ts、新增 .env 变量、改动依赖时需重启 dev server，HMR 不会自动生效。
- **依赖预构建缓存**：node_modules/.vite 缓存异常会导致"依赖解析失败"类报错，删除该目录重启即可。
- **别名两处同步**：vite.config.ts 的 alias 与 tsconfig.json 的 paths 必须一致，否则编辑器报红但运行正常（或反之）。
- **代理 rewrite**：代理目标接口路径与前端请求前缀不一致时需配置 rewrite，前后端联调前先确认路径约定（见《[API 接口规范](../../../规范/API接口规范.html)》）。
- **构建产物体积告警**：chunk 超 500KB 警告属正常提示，按需分析（大依赖拆 manualChunks），不必强行压榨。
- **旧浏览器兼容**：Vite 默认面向现代浏览器（ES2020+），BMS 为内部系统不强制兼容旧 IE；如需兼容走 @vitejs/plugin-legacy。
- **Node 版本**：Vite 各版本对 Node 有最低要求，务必配合 .nvmrc 固定 Node 版本，避免 CI 与本地行为不一致。

## 6. 学习与参考资料 <a id="learn"></a>

| 资源 | 网址 | 说明 |
| --- | --- | --- |
| Vite 官方文档（中文） | https://cn.vitejs.dev/ | 官方中文文档，配置参考权威 |
| Vite 官方文档（英文） | https://vitejs.dev/ | 英文原版，更新最快 |
| Vite GitHub 仓库 | https://github.com/vitejs/vite | 源码、Changelog 与 issue |
| @vitejs/plugin-vue | https://github.com/vitejs/vite-plugin-vue | Vue SFC 编译插件文档 |
| Vitest 官方文档 | https://vitest.dev/ | Vite 同构测试框架，见《[Vitest 技术介绍](Vitest技术介绍.md)》 |

## 7. 项目内关联文档 <a id="related"></a>

| 文档 | 说明 |
| --- | --- |
| 《[项目规划说明](../../../规划/项目规划说明.html#stack-frontend)》2.2 节 | 前端技术栈（Vite 条目） |
| 《[项目规划说明](../../../规划/项目规划说明.html#sel-frontend)》3.2 节 | Vite 冷启动快、与 Vitest 同构的选型理由 |
| 《[开发部署规划](../../../规划/开发部署规划.html)》 | 前端双工程安装、启动与构建流程 |
| 《[Vue 3 技术介绍](Vue3技术介绍.md)》 | 被构建的前端框架 |
| 《[TypeScript 技术介绍](TypeScript技术介绍.md)》 | tsconfig 与 Vite 别名同步事项 |
| 《[npm 技术介绍](npm技术介绍.md)》 | 依赖安装与版本锁定（Vite 经 npm 引入） |
| 《[Vitest 技术介绍](Vitest技术介绍.md)》 | 与 Vite 同构的单元测试框架 |

---

> 本文档为 AI 生成 · 依《[文档生成规范](../../../规范/文档生成规范.html)》编写 · 生成日期：2026-08-19