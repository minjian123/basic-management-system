# vue-flow 技术介绍

> 自由画布节点图引擎 · BMS 大屏设计器画布基础

[文档首页](../../../文档首页.md) › [知识档案](../技术栈知识档案总览.md) › [前端](../技术栈知识档案总览.md#frontend) › vue-flow 技术介绍　|　[← 返回总览](../技术栈知识档案总览.md)

---

## 1. 技术概述 <a id="overview"></a>

**Vue Flow**（核心包 `@vue-flow/core`）是
React Flow 生态的官方 Vue 3 实现，定位是**自由画布**：
节点按绝对坐标自由摆放、可连线、可缩放平移，支持自定义节点
（节点内容就是普通 Vue 组件）、小地图、控件等。
截至 2026 年，Vue Flow（1.48.x）活跃维护，是 Vue 生态做
节点图/画布类交互的主流开源方案。

- **定位**：BMS 大屏设计器的自由画布——节点自由拖拽（绝对定位）、缩放平移，配合 ECharts 渲染图表节点（见《[项目规划说明](../../../规划/项目规划说明.md#stack-frontend)》2.2 节）。
- **版本**：1.48.2（截至 2026 年，持续迭代）。
- **许可**：MIT，OSI 认证开源。
- **语言**：TypeScript 编写，Vue 3 组件。

## 2. 核心概念与原理 <a id="principles"></a>

| 概念 | 说明 |
| --- | --- |
| Node（节点） | 画布上的单元，按绝对坐标（x/y）定位；节点内容可以是自定义 Vue 组件，BMS 把 ECharts 图表放进节点 |
| Edge（连线） | 节点之间的连接（source → target）；大屏以自由布局为主，连线场景少但能力具备 |
| Viewport（视口） | 画布的视图状态：缩放（zoom）+ 平移（pan），`fitView` 一键适配全部节点 |
| Handle（连接点） | 节点上的 source/target 锚点，连线时从这里出发/接入 |
| Custom Node（自定义节点） | 节点内容即 Vue 组件：可渲染 ECharts、文本、图片等任意内容，BMS 图表节点的基础 |
| node-resizer | `@vue-flow/node-resizer` 插件：拖拽调整节点尺寸，大屏卡片大小调整用它 |
| Minimap / Controls / Background | 辅助组件：`@vue-flow/minimap`（小地图）、`@vue-flow/controls`（缩放控件）、`@vue-flow/background`（点阵背景） |
| v-model:nodes / edges | 节点与连线数据和 Vue 响应式状态双向绑定，改数组即改画布 |
| 事件机制 | `nodeDragStop`、`nodeClick`、`viewportChange` 等，监听拖拽结束与视图变化触发持久化 |
| 坐标系 | 画布有独立的 flow 坐标系，与屏幕坐标不同；`screenToFlowPosition` 做换算，存位置时以 flow 坐标为准 |
| 布局持久化 | nodes 数组（位置/尺寸/类型）导出 JSON 存后端，播放/还原时 `load` 回画布 |

## 3. 在 BMS 项目中的用途 <a id="usage"></a>

- **大屏设计器**：大屏自由画布——节点自由拖拽（绝对定位）、缩放平移，与 gridstack 网格布局分工明确，互不混用（见《[项目规划说明](../../../规划/项目规划说明.md#sel-frontend)》3.2 节）。
- **图表节点**：节点内容用 ECharts 渲染（营收趋势、区域分布等），节点即图表卡（见《[ECharts 技术介绍](ECharts技术介绍.md)》）。
- **布局持久化**：节点位置/尺寸/类型序列化为 JSON 存后端；大屏播放页只读还原画布并 `fitView` 适配屏幕。
- **尺寸调整**：设计态用 node-resizer 拖拽改节点尺寸，播放态按屏幕比例缩放。
- **三库分工**：列表排序用 vuedraggable、网格布局用 gridstack、自由画布用 vue-flow（见《[项目规划说明](../../../规划/项目规划说明.md#sel-frontend)》3.2 节）。

最小示例（两个节点 + 自适应视图）：

```html
<script setup>
import { ref } from 'vue'
import { VueFlow } from '@vue-flow/core'
import '@vue-flow/core/dist/style.css'
import '@vue-flow/core/dist/theme-default.css'

const nodes = ref([
  { id: 'n1', position: { x: 0, y: 0 }, label: '营收趋势' },
  { id: 'n2', position: { x: 400, y: 120 }, label: '区域分布' },
])
</script>

<template>
  <VueFlow :nodes="nodes" :edges="[]" :fit-view-on-init="true" />
</template>
```

## 4. 选型对比 <a id="compare"></a>

| 候选技术 | 优缺点 | 结论 |
| --- | --- | --- |
| **vue-flow（选中）** | Vue 3 官方实现、自由画布 + 缩放平移 + 自定义节点、插件齐全、活跃维护、MIT | 与 BMS 大屏「自由定位 + 图表节点」诉求完全匹配 |
| React Flow | 功能最全、生态最大；但绑定 React，Vue 项目不适用 | 框架不符，直接排除 |
| gridstack.js | 网格布局强（对齐网格 + resize + 响应式）；但大屏要自由定位，网格约束反而碍事 | 分工不同：网格布局用 gridstack（见《[gridstack 技术介绍](gridstack技术介绍.md)》） |
| D3.js | 底层 SVG/Canvas 能力极强；但画布交互（拖拽/缩放/坐标）要全部自建，学习曲线陡 | 杀鸡用牛刀，不选 |
| 自研绝对定位 | 完全可控；但缩放平移、坐标换算、碰撞避让工作量大 | 重复造轮子，风险高，不选 |

## 5. 常见问题与注意事项 <a id="pitfalls"></a>

- **与 gridstack 分工**：网格布局用 gridstack、自由画布用 vue-flow，两者互不混用（见《[gridstack 技术介绍](gridstack技术介绍.md)》）。
- **节点内 ECharts 生命周期**：节点组件 onMounted 初始化图表、onBeforeUnmount 调 `chart.dispose()`，防内存泄漏。
- **图表 resize**：节点尺寸变化（node-resizer）时要联动 `chart.resize()`，否则图表不跟随。
- **坐标系换算**：存位置用 flow 坐标；从鼠标事件取坐标要用 `screenToFlowPosition`，混用会偏移。
- **插件版本对齐**：`@vue-flow/minimap`、`@vue-flow/controls` 等插件包要和 `@vue-flow/core` 大版本一致。
- **大画布性能**：节点很多时关闭动画、播放态用只读模式，避免交互开销。
- **样式引入**：必须引入 `@vue-flow/core/dist/style.css` 与 `theme-default.css`，否则节点/连线样式缺失。
- **升级走评审**：大版本变更走 [Renovate](../部署与运维/Renovate技术介绍.md) 提 MR + 回归，重点验证布局 JSON 兼容。

## 6. 学习与参考资料 <a id="learn"></a>

| 资源 | 网址 | 说明 |
| --- | --- | --- |
| Vue Flow 官网 | https://vueflow.dev | 文档、示例与特性入口 |
| Vue Flow GitHub | https://github.com/bcakmakoglu/vue-flow | 源码、API、Changelog 与 issue |
| @vue-flow/core npm | https://www.npmjs.com/package/@vue-flow/core | 安装与版本历史 |
| React Flow 文档 | https://reactflow.dev | 同生态文档，概念与 API 大体相通，可交叉参考 |
| Vue 3 官方文档 | https://cn.vuejs.org/ | 自定义节点即 Vue 组件，组件机制是基础 |

## 7. 项目内关联文档 <a id="related"></a>

| 文档 | 说明 |
| --- | --- |
| 《[项目规划说明](../../../规划/项目规划说明.md#stack-frontend)》2.2 节 | 前端技术栈（vue-flow 条目） |
| 《[项目规划说明](../../../规划/项目规划说明.md#sel-frontend)》3.2 节 | 选型理由：大屏自由画布，与 gridstack 分工明确 |
| 《[ECharts 技术介绍](ECharts技术介绍.md)》 | 图表节点渲染（vue-flow 画布 + ECharts 内容） |
| 《[gridstack 技术介绍](gridstack技术介绍.md)》 | 网格布局（与 vue-flow 自由画布分工） |
| 《[vuedraggable 技术介绍](vuedraggable技术介绍.md)》 | 表单设计器列表排序（三者分工之一） |
| 《[Vue 3 技术介绍](Vue3技术介绍.md)》 | vue-flow 的宿主框架 |
| 《[命名规范](../../../规范/命名规范.md)》 | 大屏布局 JSON 字段命名 |

---

> 依《[文档生成规范](../../../规范/文档生成规范.md)》编写 · 生成日期：2026-08-19