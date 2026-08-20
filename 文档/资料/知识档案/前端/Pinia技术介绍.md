# Pinia 技术介绍

> Vue 3 官方状态管理库（Vuex 继任者）· BMS 前端全局状态

[文档首页](../../../文档首页.md) › [知识档案](../技术栈知识档案总览.md) › [前端](../技术栈知识档案总览.md#frontend) › Pinia 技术介绍　|　[← 返回总览](../技术栈知识档案总览.md)

---

## 1. 技术概述 <a id="overview"></a>

**Pinia** 是 Vue 官方推出的状态管理库，是 Vuex 的继任者，
从 Vue 3 组合式 API 时代开始成为默认推荐方案。相比 Vuex 4 去掉了
mutations 概念、移除了模块嵌套，API 更简洁，TypeScript 支持优秀，
且对 Vue 3 的响应式体系是原生级的（无兼容层）。

- **定位**：BMS 前端（frontend / frontend-mobile）全局状态管理，负责会话、用户信息、权限、偏好等跨页面状态。
- **版本**：2.x/3.x 系列（API 一致，持续迭代）。
- **许可**：MIT，OSI 认证开源（见《项目规划说明》2.5 节许可清单）。
- **组织**：按模块拆分 store 文件，统一放 `src/stores/` 目录（见《项目规划说明》4 节目录结构）。

## 2. 核心概念与原理 <a id="principles"></a>

| 概念 | 说明 |
| --- | --- |
| defineStore | 定义 store 的入口：id + 配置对象（state/getters/actions）或 setup 函数，两种写法按需选择 |
| state | store 的响应式数据源，等价于组件 data；修改即触发相关组件更新 |
| getters | 派生状态（相当于计算属性），基于 state 计算，自动缓存且响应式 |
| actions | 业务动作，可同步可异步（调用 API 后再更新 state）；相比 Vuex 无需再写 mutations |
| storeToRefs | 从 store 中解构出响应式引用：直接解构会丢失响应性，必须经它取 state/getters |
| setup store | 以 setup 函数定义 store，内部用 ref/computed/函数自由组合，适合复杂逻辑（BMS 项目推荐） |
| 插件（Plugin） | store 生命周期钩子（$subscribe、$onAction），可扩展持久化（persist 插件）等能力 |
| 模块化 | 一个 store 一个文件，按业务域拆分（user / permission / preference / i18n），比 Vuex 的模块嵌套扁平直接 |
| $subscribe | 订阅 state 变化，可用于把状态同步到 localStorage（如语言偏好、工作台布局） |
| DevTools 集成 | Vue DevTools 原生支持时间旅行调试 state 与 actions |

## 3. 在 BMS 项目中的用途 <a id="usage"></a>

- **官方状态管理（2.2 节）**：Pinia 取代 Vuex，TS 支持好（见《[项目规划说明](../../../规划/项目规划说明.md#stack-frontend)》2.2 节与 3.2 节选型理由）。
- **模块化 store（4 节目录结构）**：状态按 `stores/` 目录组织，每个业务域一个 store 文件，与后端模块划分对应（见《[项目规划说明](../../../规划/项目规划说明.md#structure)》4 节）。
- **会话与用户信息**：access token（仅存内存）、当前用户、语言/时区（sys_user.locale/timezone）等状态集中管理，配合路由守卫与 [Axios](Axios技术介绍.md) 拦截器读写（见《[项目规划说明](../../../规划/项目规划说明.md#security)》12 节认证与安全）。
- **权限状态**：登录后拉取的菜单树与权限码列表存 store，路由动态注册与按钮/字段显隐都从这里取（见《[项目规划说明](../../../规划/项目规划说明.md#pages)》15 节菜单机制）。
- **用户喜好**：主题模式、列表页个性化、工作台布局等偏好（sys_user_preference）经 store 统一读写，PC 与移动端跨端同步（见《[项目规划说明](../../../规划/项目规划说明.md#modules)》5 节用户喜好模块）。
- **语言偏好**：当前语言与语言包缓存经 store 管理，与 vue-i18n 联动（见《[vue-i18n 技术介绍](vue-i18n技术介绍.md)》）。

setup store 最小示例：

```js
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

export const useUserStore = defineStore('user', () => {
  const accessToken = ref('')
  const profile = ref(null)

  const isLoggedIn = computed(() => !!accessToken.value)

  async function login(credentials) {
    const { data } = await apiAuth.login(credentials)
    accessToken.value = data.access_token
    profile.value = data.profile
  }

  function logout() {
    accessToken.value = ''
    profile.value = null
  }

  return { accessToken, profile, isLoggedIn, login, logout }
})
```

## 4. 选型对比 <a id="compare"></a>

| 候选技术 | 优缺点 | 结论 |
| --- | --- | --- |
| **Pinia（选中）** | Vue 官方继任者、TS 支持好、无 mutations 心智负担、DevTools 原生支持 | 与 Vue 3 组合式体系完全契合，官方推荐路径 |
| Vuex 4 | 成熟、资料多，但 mutations 冗余、TS 推导差、模块嵌套繁琐 | 官方已转向 Pinia，Vuex 4 仅维护不再演进 |
| provide/inject + composables | 零依赖、适合局部状态，但全局共享与调试能力弱 | 可做组件内局部状态，全局状态仍归 Pinia |
| 全局 reactive 单例 | 写法简单，但无命名空间、无插件机制、DevTools 不可见 | 规模一大就失控，BMS 模块众多不适用 |

## 5. 常见问题与注意事项 <a id="pitfalls"></a>

- **解构丢响应性**：`const { name } = store` 拿到的是快照；state/getters 必须 `storeToRefs(store)` 解构，actions 可直接解构。
- **setup 外使用 store**：在路由守卫、Axios 拦截器等非组件环境用 store 前，需确保 pinia 实例已 install（Vite 入口 createApp 时安装）；独立模块中可调用 `useStore(pinia)` 显式传实例。
- **敏感信息不进持久化**：access token 按规范只存内存，绝不可用 persist 插件写进 localStorage（防 XSS 窃取，见《[项目规划说明](../../../规划/项目规划说明.md#security)》12 节）。
- **store 只存可序列化数据**：不要放组件实例、DOM 元素等非序列化对象。
- **模块边界**：一个业务域一个 store 文件，避免"万能 store"；store 间互相引用注意初始化顺序。
- **持久化按需配置**：只有语言偏好、布局等需要跨会话保留的状态才配 persist，且键名与后端 `pref_key` 对齐（如 dashboard:layout）。

## 6. 学习与参考资料 <a id="learn"></a>

| 资源 | 网址 | 说明 |
| --- | --- | --- |
| Pinia 官方文档 | https://pinia.vuejs.org/ | 权威文档：核心概念、API 参考 |
| Pinia 官方文档（中文） | https://pinia.vuejs.org/zh/ | 官方中文版 |
| Pinia GitHub | https://github.com/vuejs/pinia | 源码、issue 与 release |
| pinia-plugin-persistedstate | https://github.com/prazdevs/pinia-plugin-persistedstate | 社区主流持久化插件（注意敏感字段排除） |
| Vue 官方状态管理章节 | https://cn.vuejs.org/guide/scaling-up/state-management | Vue 3 文档对 Pinia 的定位说明 |

## 7. 项目内关联文档 <a id="related"></a>

| 文档 | 说明 |
| --- | --- |
| 《[项目规划说明](../../../规划/项目规划说明.md#stack-frontend)》2.2 节 | 前端技术栈（Pinia 条目） |
| 《[项目规划说明](../../../规划/项目规划说明.md#structure)》4 节 | 目录结构：frontend/src/stores/ 组织方式 |
| 《[项目规划说明](../../../规划/项目规划说明.md#modules)》5 节 | 用户喜好模块：偏好状态经 store 管理并落 sys_user_preference |
| 《[前端开发规范](../../../规范/前端开发规范.md)》 | 组件与状态管理约定 |
| 《[Vue 3 技术介绍](Vue3技术介绍.md)》 | Pinia 所依托的前端框架 |
| 《[Vue Router 技术介绍](VueRouter技术介绍.md)》 | 路由守卫中读取 userStore / permissionStore |
| 《[Axios 技术介绍](Axios技术介绍.md)》 | 拦截器与 store 的读写配合（token、401 续期） |

---

> 本文档为 AI 生成 · 依《[文档生成规范](../../../规范/文档生成规范.md)》编写 · 生成日期：2026-08-19