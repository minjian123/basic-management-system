# Vue 3 技术介绍

> 渐进式 JavaScript 前端框架 · BMS 双端（PC + H5）统一基础

[文档首页](../../../文档首页.md) › [知识档案](../技术栈知识档案总览.md) › [前端](../技术栈知识档案总览.md#frontend) › Vue 3 技术介绍　|　[← 返回总览](../技术栈知识档案总览.md)

---

## 1. 技术概述

**Vue 3** 是一个渐进式的 JavaScript 前端框架，由尤雨溪（Evan You）创建并主导开发，
2020 年 9 月正式发布。与 Vue 2 相比，Vue 3 采用全新的组合式 API（Composition API）、
更高效的虚拟 DOM 与响应式系统，并原生获得 TypeScript 支持。
截至 2026 年，Vue 3（3.5.x 系列）是社区最主流的前端框架之一，中文资料与生态尤为丰富。

- **定位**：BMS 前端核心框架，PC 管理端与移动端 H5 双工程的基础。
- **版本**：3.5.x 系列（截至 2026 年 8 月，持续小版本迭代）。
- **许可**：MIT，OSI 认证开源。
- **语言**：TypeScript 编写，项目内以 `<script setup>` 组合式写法为主。

## 2. 核心概念与原理

| 概念 | 说明 |
| --- | --- |
| 响应式系统 | `ref()`/`reactive()` 声明响应式数据，数据变化自动触发界面更新（Proxy 实现，比 Vue 2 的 defineProperty 更完整） |
| 组合式 API（Composition API） | 用函数组织逻辑：`setup`/`<script setup>` 中声明状态与函数，按业务切片复用，适合中后台复杂页面 |
| 选项式 API（Options API） | Vue 2 风格：data/computed/methods 分块书写，Vue 3 保留兼容，BMS 项目以组合式为主 |
| SFC 单文件组件 | `.vue` 文件 = 模板 + 脚本 + 样式三合一（`<template>`/`<script>`/`<style>`），Vite 负责编译 |
| 虚拟 DOM | 模板编译为渲染函数，通过新旧 VNode 对比（diff）只更新变化部分，Vue 3 的编译期优化使更新更快 |
| 计算属性与侦听器 | `computed()` 派生值（缓存）、`watch()`/`watchEffect()` 响应数据变化执行副作用 |
| 组件通信 | props 单向数据流、emit 事件、插槽 slot 分发内容、provide/inject 跨层级共享（详见《[Vue Router](VueRouter技术介绍.md)》《[Pinia](Pinia技术介绍.md)》配套使用） |
| 生命周期钩子 | onMounted/onUnmounted 等组合式钩子，在组件挂载、更新、卸载时执行代码 |
| defineProps / defineEmits | `<script setup>` 中声明组件入参与事件，配合 TypeScript 可做强类型校验 |
| Teleport / Transition | Teleport 把弹窗等渲染到 body 下；Transition 提供进入/离开动画钩子 |
| KeepAlive | 缓存组件实例，列表页跳详情再返回时保留滚动位置与状态 |

## 3. 在 BMS 项目中的用途

- PC 管理端（frontend）与移动端 H5（frontend-mobile）**双工程同用 Vue 3**，分别配合 Element Plus 与 Vant 组件库，复用同一套后端 API 与会话体系（见《[项目规划说明](../../../规划/项目规划说明.md#stack-frontend)》2.2 节）。
- **组合式 API 适合中后台业务**：按业务切片组织代码，配合 TypeScript 类型化 props/emits，团队协作与长期维护成本低（见《[项目规划说明](../../../规划/项目规划说明.md#sel-frontend)》3.2 节）。
- 与 [Vite](Vite技术介绍.md)（构建）、[TypeScript](TypeScript技术介绍.md)（类型）、[Vue Router](VueRouter技术介绍.md)（路由）、[Pinia](Pinia技术介绍.md)（状态）、[Element Plus](ElementPlus技术介绍.md)（PC 组件）组成完整技术栈。
- 前端工程目录（frontend/src/）按 vue 惯例组织：views（页面）、layouts（布局）、components（组件）、stores（Pinia）、router（动态路由）、api（接口）、i18n（文案），见《[项目规划说明](../../../规划/项目规划说明.md#structure)》4 节。
- 移动端 H5（frontend-mobile）独立工程同用 Vue 3 + Vant，实现审批、通知、数据查询等移动场景，企业微信/钉钉内嵌免登。
- 待办角标等全局 UI 元素由布局组件统一承载，配合 [python-socketio](../后端核心/python-socketio技术介绍.md) 实时推送更新。

最小示例（组合式 API）：

```html
<script setup lang="ts">
import { ref } from 'vue'
const count = ref(0)
function add() { count.value++ }
</script>

<template>
  <el-button @click="add">点击 {{ count }}</el-button>
</template>
```

## 4. 选型对比

| 框架 | 优缺点 | 结论 |
| --- | --- | --- |
| **Vue 3（选中）** | 组合式 API 灵活、中文生态最大、上手门槛低、渐进式可按需引入 | 与项目双端（PC/H5）、中后台场景、团队技能匹配 |
| React 18+ | 生态庞大、函数式思维，但路由/状态需自行选型组合，对国内中后台同学上手成本高 | 可行但团队与生态成本高，与 Element Plus 等成熟配套脱钩 |
| Angular | 全家桶一体化、约束强，但体积大、学习曲线陡 | 过重，与 BMS 轻快迭代目标不符 |
| Svelte | 编译时框架、运行开销小，但生态与组件库成熟度不足 | 生态（尤其是中后台组件库）不满足需求 |

## 5. 常见问题与注意事项

- **响应式丢失**：解构 props 或把 reactive 对象重新整体赋值都会失去响应性，改用 toRefs/storeToRefs 或直接操作属性。
- **ref 的 .value**：模板中自动解包，但 JS 逻辑中必须写 `.value`，忘写是最高频低级错误。
- **props 只读**：禁止直接修改 props，需要派生值用 computed，需要回传用 emit。
- **watch 监听对象**：直接 watch(reactiveObj) 需要 deep 选项或改用 getter 形式，否则监听不到内部变化。
- **Vue 2 → Vue 3 不兼容**：Vue 2 的过滤器、事件总线等语法在 Vue 3 已移除；本项目为新工程直接上 Vue 3，无迁移负担，但参考旧代码时需注意。
- **内存泄漏**：onMounted 中挂的全局监听器、定时器必须在 onUnmounted 中清理。
- **长列表性能**：v-for 必须带稳定的 key；大数据表格用虚拟滚动（Element Plus 虚拟化或后端分页）。
- **版本锁定**：Vue 与配套生态（Element Plus、Vue Router、Pinia）版本需匹配，依赖升级交给 [Renovate](../部署与运维/Renovate技术介绍.md) 自动提 MR。

## 6. 学习与参考资料

| 资源 | 网址 | 说明 |
| --- | --- | --- |
| Vue 3 官方文档（中文） | https://cn.vuejs.org/ | 权威教程与 API 参考，中文支持完善 |
| Vue 3 官方文档（英文） | https://vuejs.org/ | 英文原版，更新最快 |
| Vue 官方教程（交互式） | https://cn.vuejs.org/tutorial/ | 边写边学的入门教程，适合新手 |
| Vue GitHub 仓库 | https://github.com/vuejs/core | 源码、Changelog 与 issue 讨论 |
| create-vue 脚手架 | https://github.com/vuejs/create-vue | 官方工程脚手架，BMS 工程初始化参考 |
| VueUse 工具集 | https://vueuse.org/ | 官方维护的组合式 API 工具库，常用函数可复用 |

## 7. 项目内关联文档

| 文档 | 说明 |
| --- | --- |
| 《[项目规划说明](../../../规划/项目规划说明.md#stack-frontend)》2.2 节 | 前端技术栈选型（Vue 3 条目） |
| 《[项目规划说明](../../../规划/项目规划说明.md#sel-frontend)》3.2 节 | 前端选型理由（组合式 API、双工程） |
| 《[项目规划说明](../../../规划/项目规划说明.md#structure)》4 节 | frontend / frontend-mobile 目录结构 |
| 《[前端开发规范](../../../规范/前端开发规范.md)》 | 编码风格与工程约束（与 Vue 3 写法相关） |
| 《[Vite 技术介绍](Vite技术介绍.md)》 | Vue 3 工程的构建与开发服务器 |
| 《[TypeScript 技术介绍](TypeScript技术介绍.md)》 | Vue 3 组件的类型化支持 |
| 《[Element Plus 技术介绍](ElementPlus技术介绍.md)》 | PC 管理端 UI 组件库 |
| 《[Vant 技术介绍](Vant技术介绍.md)》 | 移动端 H5（frontend-mobile）组件库 |

---

> 依《[文档生成规范](../../../规范/文档生成规范.md)》编写 · 生成日期：2026-08-19