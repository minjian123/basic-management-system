# gridstack.js 技术介绍

> 框架无关的网格拖拽布局库 · BMS 工作台与报表设计器布局基础

[文档首页](../../../文档首页.md) › [知识档案](../技术栈知识档案总览.md) › [前端](../技术栈知识档案总览.md#frontend) › gridstack.js 技术介绍　|　[← 返回总览](../技术栈知识档案总览.md)

---

## 1. 技术概述 <a id="overview"></a>

**gridstack.js**（npm 包名 `gridstack`）是一个框架无关的
网格拖拽布局库，纯 TypeScript 编写、无外部依赖，支持
**卡片拖拽、尺寸调整、响应式断点**与**布局存取**，
内置 Angular/React/Vue 封装。截至 2026 年，gridstack（13.x 系列）是 Web 端
仪表盘/工作台网格布局的主流开源方案，活跃维护。

- **定位**：BMS 工作台卡片与报表设计器的统一布局引擎，负责网格拖拽、尺寸调整与响应式。
- **版本**：13.x 系列（13.0.2，截至 2026 年，持续迭代）。
- **许可**：MIT，OSI 认证开源。
- **语言**：TypeScript 编写，框架无关（Vue 经封装或自行集成）。

## 2. 核心概念与原理 <a id="principles"></a>

| 概念 | 说明 |
| --- | --- |
| 网格（Grid） | 由列（column）与行高（cellHeight）定义的布局坐标系，BMS 默认 12 列 |
| 单元格（Cell） | 网格最小单位，卡片位置与尺寸都用「占几列几行」描述（x/y/w/h） |
| Item（卡片） | 网格内可拖拽的单元，承载一个工作台卡片或图表 |
| 拖拽与尺寸调整 | 内置拖拽移动与四角/边缘 resize，自动避让其他卡片 |
| 响应式断点 | 按屏宽切换列数（如桌面 12 列、平板 6 列、手机 1 列），布局自动重排 |
| save / load | `grid.save()` 导出布局 JSON、`grid.load()` 还原，BMS 据此持久化到后端 |
| float / static | float 允许卡片上移填空隙，static 锁定位置，BMS 编辑态用 float |
| 跨网格拖拽 | 多网格间拖入拖出，BMS 卡片从「卡片库」拖入工作台用 |
| 事件机制 | `dragstop`、`resizestop`、`change` 等，监听布局变化触发保存 |
| Vue 集成 | 官方内置 Vue 封装（`gridstack/dist/vue`）或自行包组件，BMS 按生命周期管理 init/destroy |

## 3. 在 BMS 项目中的用途 <a id="usage"></a>

- **工作台卡片布局**：首页工作台卡片拖拽、显隐、尺寸调整、响应式，统一用 gridstack（见《[项目规划说明](../../../规划/项目规划说明.md#sel-frontend)》3.2 节）。
- **布局持久化**：个人布局（`sys_user_preference`，pref_key=dashboard:layout）与角色模板（`sys_dashboard_template.layout_config`）均序列化为 gridstack 布局 JSON（见《[项目规划说明](../../../规划/项目规划说明.md#pages)》数据规范）。
- **三级模板回退**：个人布局 → 角色模板 → 平台默认模板，一键重置逐级回退，布局结构统一为 gridstack 格式便于解析。
- **报表设计器布局**：报表/大屏卡片在网格中的位置与尺寸用 gridstack 描述，与 ECharts 图表卡配合（见《[ECharts 技术介绍](ECharts技术介绍.md)》）。
- **跨端一致**：PC 与移动端布局配置同源，gridstack 响应式断点适配不同屏宽。

最小示例（初始化 + 加卡片 + 存取布局）：

```js
import GridStack from 'gridstack'
import 'gridstack/dist/gridstack.min.css'

const grid = GridStack.init({ column: 12, cellHeight: 80 })

grid.addWidget({ x: 0, y: 0, w: 4, h: 2, content: '待办' })
grid.addWidget({ x: 4, y: 0, w: 8, h: 2, content: '图表' })

// 布局变化后保存（序列化 JSON 存 sys_user_preference / sys_dashboard_template）
grid.on('dragstop resizestop', () => {
  const layout = grid.save()
  // POST 到后端持久化
})

// 还原布局
grid.load(layout)
```

## 4. 选型对比 <a id="compare"></a>

| 候选技术 | 优缺点 | 结论 |
| --- | --- | --- |
| **gridstack.js（选中）** | 框架无关、拖拽/resize/响应式齐全、布局可存取、活跃维护、MIT | 与 BMS 工作台/报表设计器统一布局诉求完全匹配 |
| react-grid-layout | 功能类似；但绑定 React，Vue 项目不适用 | 框架不符，直接排除 |
| Masonry（瀑布流） | 自动排布好看；但无拖拽/resize，不可交互定制 | 只读展示可用，BMS 需用户定制布局，不选 |
| 自研绝对定位 | 完全可控；但拖拽避让、resize、响应式、碰撞检测工作量大 | 重复造轮子，风险高，不选 |

## 5. 常见问题与注意事项 <a id="pitfalls"></a>

- **Vue 集成生命周期**：init 要在 DOM 挂载后（onMounted），销毁时 `grid.destroy()` 防内存泄漏与事件残留。
- **布局 JSON 版本兼容**：gridstack 大版本升级可能调整布局结构，持久化数据要留版本号、做兼容迁移。
- **保存时机**：在 `dragstop`/`resizestop` 后保存，别在每次 `change` 都写后端，避免高频请求。
- **与 vue-flow 分工**：网格布局用 gridstack、自由画布用 vue-flow，两者互不混用（见《[vue-flow 技术介绍](vue-flow技术介绍.md)》）。
- **卡片内容自适应**：卡片内 ECharts 等要在尺寸变化时 resize，监听 grid 的 resize 事件联动。
- **响应式断点配置**：按实际屏宽设列数断点，别用默认值，否则移动端布局错乱。
- **升级走评审**：大版本变更走 [Renovate](../部署与运维/Renovate技术介绍.md) 提 MR + 回归，重点验证布局存取兼容。

## 6. 学习与参考资料 <a id="learn"></a>

| 资源 | 网址 | 说明 |
| --- | --- | --- |
| gridstack.js 官网 | https://gridstackjs.com | 演示、文档与示例入口 |
| gridstack GitHub | https://github.com/gridstack/gridstackjs | 源码、API、Changelog 与 issue |
| gridstack 官方 Vue 封装 | https://github.com/gridstack/gridstack.js/tree/master/vue | 内置 Vue 3 封装（gridstack/dist/vue）说明 |
| gridstack 示例 | https://gridstackjs.com/#examples | 拖拽/resize/响应式现成示例 |
| MDN：CSS Grid | https://developer.mozilla.org/zh-CN/docs/Web/CSS/CSS_grid_layout | 理解网格布局底层 CSS 原理 |

## 7. 项目内关联文档 <a id="related"></a>

| 文档 | 说明 |
| --- | --- |
| 《[项目规划说明](../../../规划/项目规划说明.md#stack-frontend)》2.2 节 | 前端技术栈（gridstack.js 条目） |
| 《[项目规划说明](../../../规划/项目规划说明.md#sel-frontend)》3.2 节 | 选型理由：框架无关、工作台与报表设计器统一布局 |
| 《[ECharts 技术介绍](ECharts技术介绍.md)》 | 工作台/报表图表卡渲染（gridstack 布局 + ECharts 内容） |
| 《[vue-flow 技术介绍](vue-flow技术介绍.md)》 | 大屏自由画布（与 gridstack 网格布局分工） |
| 《[vuedraggable 技术介绍](vuedraggable技术介绍.md)》 | 表单设计器列表排序（与 gridstack 网格布局分工） |
| 《[命名规范](../../../规范/命名规范.md)》 | layout_config、pref_key 等字段命名 |

---

> 本文档为 AI 生成 · 依《[文档生成规范](../../../规范/文档生成规范.md)》编写 · 生成日期：2026-08-19