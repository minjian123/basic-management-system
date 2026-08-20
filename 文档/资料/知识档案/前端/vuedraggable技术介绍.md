# vuedraggable 技术介绍

> 列表拖拽排序（SortableJS 封装）· BMS 表单设计器专用

[文档首页](../../../文档首页.html) › [知识档案](../技术栈知识档案总览.md) › [前端](../技术栈知识档案总览.md#frontend) › vuedraggable 技术介绍　|　[← 返回总览](../技术栈知识档案总览.md)

---

## 1. 技术概述 <a id="overview"></a>

**vuedraggable**（npm 包名 `vuedraggable`）是
**SortableJS** 的 Vue 官方封装。SortableJS 是一个框架无关的拖拽库，
不依赖 jQuery，同时支持鼠标与触摸；vuedraggable 在它之上把「拖拽」变成
**Vue 列表数据的重排**——拖一下，响应式数组顺序就变了，
页面其余部分（计算属性、watcher、持久化）全部跟着动。

- **定位**：BMS 表单设计器专用——字段排序、分组与跨分区拖拽、查询区/明细列顺序调整（见《[项目规划说明](../../../规划/项目规划说明.html#stack-frontend)》2.2 节）。
- **版本**：4.1.0（Vue 3 版即 Vue.Draggable.Next，2021 年发布后无新版；底层 SortableJS 持续维护）。
- **许可**：MIT，OSI 认证开源。
- **语言**：JavaScript 编写，Vue 3 组件。

## 2. 核心概念与原理 <a id="principles"></a>

| 概念 | 说明 |
| --- | --- |
| SortableJS | 底层拖拽引擎：处理拖起、占位、放下、动画等全部交互细节，框架无关，鼠标/触摸都支持 |
| draggable 组件 | vuedraggable 提供的 Vue 组件，把 SortableJS 绑定到 `v-for` 列表上，拖拽结果直接写回数组 |
| list / modelValue | 列表数据源：`:list` 模式原地重排数组；`v-model` 模式通过事件同步顺序，跨容器场景两种都常用 |
| group | 分组配置：控制元素能否跨容器拖入拖出，BMS「字段跨分区移动」靠它实现 |
| handle | 拖拽把手：只有按住指定元素（如行首的拖拽图标）才触发拖拽，避免和行内按钮、输入框的点击冲突 |
| placeholder | 拖拽过程中原位置显示的占位元素，视觉上的「空槽」 |
| animation | 松手后元素归位的动画帧数（毫秒），拖拽体验顺滑度的关键参数 |
| 事件机制 | `@change`（顺序变化）、`@add`/`@remove`（跨容器进出）、`@start`/`@end`，监听后触发持久化 |
| clone | 允许「拖出即复制」：从字段库拖字段进表单区时用，原件留在库里 |
| 触摸支持 | SortableJS 原生支持 touch，移动端 H5 里同样可用 |
| Vue 响应式驱动 | 拖拽结果写回响应式数组，computed/watch/后端持久化全部由数据变化驱动，不直接操作 DOM |

## 3. 在 BMS 项目中的用途 <a id="usage"></a>

- **表单设计器（表单布局管理）**：选表单 → 布局编辑——分区/分组/列数/跨列/顺序/标签宽度、查询表单区、明细区列配置、字段属性、租户自建字段，列表排序与跨分区拖拽统一用 vuedraggable（见《[项目规划说明](../../../规划/项目规划说明.html#pages)》15 节、《[项目规划说明](../../../规划/项目规划说明.html#plan)》20 节验收标准）。
- **字段排序**：同一分区内字段上下拖拽调整顺序，结果写回布局 JSON 存后端。
- **跨分区拖拽**：多个分区容器配置相同 `group`，字段可在分区之间移动（`@add`/`@remove` 事件感知进出）。
- **查询区/明细列顺序调整**：查询表单区字段、明细区列的先后顺序调整，同一套组件复用。
- **字段库拖入**：从可用字段库拖字段进表单区（`clone` 模式，字段库不减少）。
- **三库分工**：列表排序用 vuedraggable、网格布局用 gridstack、自由画布用 vue-flow，三者互不混用（见《[项目规划说明](../../../规划/项目规划说明.html#sel-frontend)》3.2 节）。

最小示例（列表排序 + 跨容器）：

```html
<script setup>
import { ref } from 'vue'
import draggable from 'vuedraggable'

const fields = ref([
  { id: 'f1', label: '申请单号' },
  { id: 'f2', label: '申请人' },
  { id: 'f3', label: '金额' },
])

function onChange(evt) {
  // evt.oldIndex / evt.newIndex：本容器内位置变化
  // evt.from / evt.to：跨容器时分别是源、目标容器
  // 在此把新顺序持久化到后端（布局 JSON）
}
</script>

<template>
  <draggable
    :list="fields"
    :group="'form-fields'"
    :animation="200"
    handle=".drag-handle"
    @change="onChange"
  >
    <template #item="{ element }">
      <div class="field-row">
        <span class="drag-handle">⋮⋮</span>
        {{ element.label }}
      </div>
    </template>
  </draggable>
</template>
```

## 4. 选型对比 <a id="compare"></a>

| 候选技术 | 优缺点 | 结论 |
| --- | --- | --- |
| **vuedraggable（选中）** | Vue 3 官方封装、数据驱动重排、group 跨容器、触摸支持、MIT | 与 BMS 表单设计器「列表排序 + 跨分区拖拽」诉求完全匹配 |
| SortableJS（裸用） | 功能全、框架无关；但无 Vue 绑定，DOM 与数据要手工同步，易和响应式脱节 | 能力重复，直接用封装版更省心 |
| gridstack.js | 网格布局强（位置 + 尺寸 + 响应式）；但面向「网格卡片」，表单设计器是「列表排序」，坐标系不对 | 分工不同：网格布局用 gridstack（见《[gridstack 技术介绍](gridstack技术介绍.md)》） |
| 原生 HTML5 Drag and Drop | 零依赖；但体验差（幽灵图、无占位动画、不支持触摸），移动端基本不可用 | 工作量与体验都不划算，不选 |
| 自研拖拽 | 完全可控；但拖拽/占位/动画/触摸/无障碍全是坑 | 重复造轮子，风险高，不选 |

## 5. 常见问题与注意事项 <a id="pitfalls"></a>

- **版本对应**：4.x 是 Vue 3 版（Vue.Draggable.Next）；2.x 是 Vue 2 版，BMS 一律用 4.x，别混装。
- **数据驱动**：拖拽结果写回响应式数组即可，不要去手动操作 DOM 顺序，否则和 Vue 渲染打架。
- **handle 必配**：行内有按钮、输入框时必须指定 `handle`，否则整行都能拖、点击事件被吞。
- **跨容器配置**：多个容器要拖入拖出，必须配相同 `group`，并用 `@add`/`@remove` 感知元素进出。
- **持久化时机**：在 `@change` 或「保存」按钮时写后端，别在拖拽过程中高频请求。
- **与 gridstack 分工**：列表排序用 vuedraggable、网格布局用 gridstack，两者互不混用（见《[gridstack 技术介绍](gridstack技术介绍.md)》）。
- **移动端真机验证**：触摸拖拽在企微/钉钉 WebView 里行为可能有差异，上线前真机过一遍。
- **长列表性能**：字段很多时按分区拆分列表，必要时虚拟滚动，别把几百个字段塞进一个容器。

## 6. 学习与参考资料 <a id="learn"></a>

| 资源 | 网址 | 说明 |
| --- | --- | --- |
| vuedraggable（Vue 3 版）GitHub | https://github.com/SortableJS/Vue.Draggable.Next | 本项目使用的 4.x 源码与 API 说明 |
| vuedraggable npm | https://www.npmjs.com/package/vuedraggable | 安装与版本历史 |
| SortableJS 官网 | https://sortablejs.github.io/SortableJS/ | 底层拖拽引擎文档与演示 |
| SortableJS GitHub | https://github.com/SortableJS/Sortable | 引擎源码、Changelog 与 issue |
| Vue 3 官方文档：列表渲染 | https://cn.vuejs.org/guide/essentials/list.html | 理解 v-for 与响应式数组重排的底层机制 |
| vuedraggable（Vue 2 版）GitHub | https://github.com/SortableJS/Vue.Draggable | 仅参考，BMS 用 4.x |

## 7. 项目内关联文档 <a id="related"></a>

| 文档 | 说明 |
| --- | --- |
| 《[项目规划说明](../../../规划/项目规划说明.html#stack-frontend)》2.2 节 | 前端技术栈（vuedraggable 条目） |
| 《[项目规划说明](../../../规划/项目规划说明.html#sel-frontend)》3.2 节 | 选型理由：表单设计器专用，与 gridstack/vue-flow 三者分工 |
| 《[项目规划说明](../../../规划/项目规划说明.html#pages)》15 节 | 表单布局管理页面清单（分区/分组/列数/跨列/顺序/标签宽度） |
| 《[gridstack 技术介绍](gridstack技术介绍.md)》 | 网格布局（与 vuedraggable 列表排序分工） |
| 《[vue-flow 技术介绍](vue-flow技术介绍.md)》 | 大屏自由画布（与 vuedraggable 列表排序分工） |
| 《[Element Plus 技术介绍](ElementPlus技术介绍.md)》 | 设计器页面工具栏、字段属性表单等界面组件 |
| 《[命名规范](../../../规范/命名规范.html)》 | 布局 JSON 字段、分区/分组等命名 |

---

> 本文档为 AI 生成 · 依《[文档生成规范](../../../规范/文档生成规范.html)》编写 · 生成日期：2026-08-19