# Vue Router 技术介绍

> Vue 3 官方路由库 · BMS 前端路由与菜单权限载体

[文档首页](../../../文档首页.md) › [知识档案](../技术栈知识档案总览.md) › [前端](../技术栈知识档案总览.md#frontend) › Vue Router 技术介绍　|　[← 返回总览](../技术栈知识档案总览.md)

---

## 1. 技术概述 <a id="overview"></a>

**Vue Router** 是 Vue.js 官方路由库，负责单页应用（SPA）的页面切换与
URL 管理。第 4 版（Vue Router 4）专为 Vue 3 重写，全部基于组合式 API 与
TypeScript 编写。BMS 的 PC 管理端（frontend）与移动端 H5（frontend-mobile）
均为 SPA，路由是页面组织的骨架。

- **定位**：BMS 前端唯一路由方案，承载页面导航与菜单级权限控制。
- **版本**：4.x 系列（Vue 3 对应版本，持续迭代）。
- **许可**：MIT，OSI 认证开源（见《项目规划说明》2.5 节许可清单）。
- **依赖**：与 Vue 3 同源维护（vuejs 官方团队）。

## 2. 核心概念与原理 <a id="principles"></a>

| 概念 | 说明 |
| --- | --- |
| createRouter | 创建路由实例的入口函数，传入路由表（routes）与 history 模式；BMS 在 `src/router/` 中初始化 |
| createWebHistory | HTML5 History 模式：URL 无 `#`，地址更干净；SPA 需服务端（nginx）把未知路径回退到 index.html |
| 路由记录（RouteRecord） | 路由表数组中的每一项：path、name、component、children、meta 等字段的组合 |
| 嵌套路由 | children 子路由渲染进父组件的 `<router-view>`，BMS 主布局（侧边栏 + 内容区）即典型嵌套结构 |
| 命名路由 | 给路由起 name，跳转用 `router.push({ name: '...' })`，避免硬编码路径 |
| 动态路由（addRoute） | 运行期追加/删除路由记录：BMS 菜单树由后端按用户权限返回，前端据此动态注册路由（见《项目规划说明》15 节菜单机制） |
| 路由守卫 | 导航过程中的拦截钩子：全局（beforeEach）、路由级（beforeEnter）、组件内；BMS 用它做登录校验与权限拦截 |
| 路由懒加载 | 组件写成 `() => import('@/views/...')`，页面按需打包与加载，配合静态资源压缩（见《项目规划说明》15 节前端性能） |
| meta 元信息 | 路由上携带自定义字段（如权限码、标题、菜单标识），守卫与页面内读取 |
| router-view | 视图出口组件，当前匹配的路由组件渲染于此；配合 transition 可做页面切换动画 |
| 导航解析流程 | 每次跳转按"失活组件 → 守卫 → 激活组件"的固定顺序执行，理解此流程才能正确使用守卫与取消导航 |
| 滚动行为（scrollBehavior） | 路由切换后控制页面滚动位置（回到顶部、锚点定位等） |

## 3. 在 BMS 项目中的用途 <a id="usage"></a>

- **前端路由（2.2 节）**：frontend 与 frontend-mobile 双工程各自使用 Vue Router 4 管理页面导航（见《[项目规划说明](../../../规划/项目规划说明.md#stack-frontend)》2.2 节）。
- **动态路由（15 节菜单机制）**：菜单树由后端按用户权限动态返回，前端根据菜单树动态注册路由与生成侧边栏；前端不硬编码路由表，新增菜单/表单/按钮/字段无需发版（见《[项目规划说明](../../../规划/项目规划说明.md#pages)》15 节）。
- **路由守卫配合业务权限做菜单级控制（3.2 节）**：全局守卫在每次导航前校验登录态与路由 meta 中的权限码，无权页面重定向到 403/首页（见《[项目规划说明](../../../规划/项目规划说明.md#sel-frontend)》3.2 节与 7 节权限模型的双重控制）。
- **静默续期（12 节认证与安全）**：access token 仅存前端内存、刷新页面后静默续期——路由守卫恰是"刷新后先续期再放行"的落点（见《[项目规划说明](../../../规划/项目规划说明.md#security)》12 节）。
- **路由懒加载**：按 15 节前端性能要求，页面组件全部懒加载，控制首屏体积。
- **目录约定**：动态路由生成逻辑集中在 `src/router/`（见《[项目规划说明](../../../规划/项目规划说明.md#structure)》4 节目录结构）。
- **移动端复用**：frontend-mobile 同样基于 Vue Router 4，页面栈与参数传递约定与 PC 端保持一致。

动态路由最小示例（登录取回菜单后注册）：

```ts
import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/dashboard' },
    { path: '/login', component: () => import('@/views/login/index.vue') },
    { path: '/:pathMatch(.*)*', component: () => import('@/views/error/404.vue') }
  ]
})

router.beforeEach(async (to) => {
  if (to.path === '/login') return true
  if (!userStore.accessToken) {
    return { path: '/login', query: { redirect: to.fullPath } }
  }
  if (!router.hasRoute(to.name ?? '')) {
    const menus = await menuApi.getTree() // 后端按权限返回菜单
    registerDynamicRoutes(menus)         // addRoute 批量注册
    return { ...to, replace: true }      // 重进目标路由
  }
  return true
})
```

## 4. 选型对比 <a id="compare"></a>

| 候选技术 | 优缺点 | 结论 |
| --- | --- | --- |
| **Vue Router 4（选中）** | Vue 3 官方路由，组合式 API 重写、TS 类型完整、守卫机制强大、生态资料全 | 与 Vue 3 同源维护，动态路由能力正好支撑菜单机制 |
| 手写 hash 监听 | 零依赖，但路由表、守卫、嵌套、懒加载全要自建 | 工程化成本高，权限与懒加载难以优雅实现 |
| Nuxt 文件路由 | 约定式路由、开箱 SSR，但引入整套 Nuxt 框架 | 《项目规划说明》24 节已明确前端不采用 SSR/Nuxt |
| vue-router 3（Vue 2 版） | 成熟的旧版本，但面向 Options API | 不兼容 Vue 3 组合式体系，无选型意义 |

## 5. 常见问题与注意事项 <a id="pitfalls"></a>

- **动态路由添加后导航中断**：addRoute 后本次导航可能"打空"，需在守卫里 `return { ...to, replace: true }` 重新进入目标路由。
- **注销/切换角色后路由残留**：动态路由是运行期叠加的，登出或权限变化时必须 removeRoute 清理，否则越权页面仍可直接访问。
- **404 兜底要最后注册**：`/:pathMatch(.*)*` 必须放在路由表末尾，且动态路由注册后 404 可能被抢先匹配——注册顺序要留意。
- **守卫死循环**：beforeEach 内跳转或返回同一目标会死循环，务必用 to.path/to.name 判分支。
- **History 模式部署 404**：nginx 需 try_files 回退 index.html，否则刷新子路径白屏（见《部署发布规范》）。
- **懒加载 chunk 加载失败**：网络抖动导致 import() 失败会白屏，可监听 chunk 错误并引导刷新重试。
- **权限判断放守卫不放组件**：仅靠组件内 v-if 隐藏入口拦不住直接输 URL，菜单级控制必须在全局守卫按 meta 权限码拦截（与后端 `require_permission` 双重控制对应）。

## 6. 学习与参考资料 <a id="learn"></a>

| 资源 | 网址 | 说明 |
| --- | --- | --- |
| Vue Router 官方文档 | https://router.vuejs.org/ | 权威文档：向导、API 参考与迁移指南 |
| Vue Router 官方文档（中文） | https://router.vuejs.org/zh/ | 官方中文版 |
| Vue Router GitHub | https://github.com/vuejs/router | 源码、issue 与 release 说明 |
| Vue 3 官方文档（路由章节） | https://cn.vuejs.org/guide/essentials/application | Vue 3 生态总览中的路由章节 |
| Vue Router 在线演练场 | https://play.vuejs.org/ | 官方 Vue 在线示例，可快速验证路由行为 |

## 7. 项目内关联文档 <a id="related"></a>

| 文档 | 说明 |
| --- | --- |
| 《[项目规划说明](../../../规划/项目规划说明.md#stack-frontend)》2.2 节 | 前端技术栈（Vue Router 4 条目） |
| 《[项目规划说明](../../../规划/项目规划说明.md#pages)》15 节 | 菜单机制：动态路由生成与侧边栏、前端不硬编码路由表 |
| 《[项目规划说明](../../../规划/项目规划说明.md#sel-frontend)》3.2 节 | 选型理由：路由守卫配合业务权限做菜单级控制 |
| 《[前端开发规范](../../../规范/前端开发规范.md)》 | 路由与目录约定、提交规范 |
| 《[Vue 3 技术介绍](Vue3技术介绍.md)》 | Vue Router 所依托的前端框架 |
| 《[Pinia 技术介绍](Pinia技术介绍.md)》 | 路由守卫中读取用户/权限状态（userStore） |
| 《[Axios 技术介绍](Axios技术介绍.md)》 | 拉取菜单树接口与 401 静默续期配合守卫 |

---

> 本文档为 AI 生成 · 依《[文档生成规范](../../../规范/文档生成规范.md)》编写 · 生成日期：2026-08-19